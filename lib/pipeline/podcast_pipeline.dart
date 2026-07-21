import 'dart:convert';
import 'dart:io';
import '../models/config_model.dart';
import '../models/pipeline_step.dart';
import '../services/config_service.dart';
import '../services/podcast_service.dart';
import '../services/groq_service.dart';

class PodcastPipeline {
  final void Function(String) onLog;
  final void Function(int current, int total, int stepIndex) onProgress;
  final PipelineState state;

  PodcastPipeline({
    required this.onLog,
    required this.onProgress,
    PipelineState? state,
  }) : state = state ?? PipelineState();

  String get _cachePath =>
      '${ConfigService.instance.config.basePath}\\podcast_processed_cache.json';

  /// Load processed-episode cache.
  /// Key: `podcast_name|episode_title`
  /// Value: `{"srt":bool, "txt":bool, "status":"ok"|"no_srt"|"error"}`
  Map<String, Map<String, dynamic>> _loadCache() {
    try {
      final f = File(_cachePath);
      if (!f.existsSync()) return {};
      final json = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
      return json.map((k, v) => MapEntry(k, (v as Map<String, dynamic>)));
    } catch (_) {
      return {};
    }
  }

  void _saveCache(Map<String, Map<String, dynamic>> cache) {
    try {
      File(_cachePath).writeAsStringSync(jsonEncode(cache), flush: true);
    } catch (_) {}
  }

  /// Run the full podcast pipeline for all subscribed podcasts.
  Future<void> run() async {
    final config = ConfigService.instance.config;
    final subs = config.podcastSubscriptions;
    if (subs.isEmpty) {
      onLog('沒有訂閱任何 Podcast');
      return;
    }

    await GroqService.instance.loadFromEnv();
    final hasGroq = GroqService.instance.apiKey != null &&
        GroqService.instance.apiKey!.isNotEmpty;

    onLog('Podcast 訂閱數: ${subs.length}');
    int stepIndex = 0;
    final subEntries = subs.entries.toList();

    for (int si = 0; si < subEntries.length; si++) {
      if (state.isCancelled) break;
      await state.waitIfPaused();

      final sub = subEntries[si];
      final podcastName = sub.key;
      final rssUrl = sub.value;
      onLog('\n--- [${si + 1}/${subEntries.length}] $podcastName ---');

      try {
        await _processPodcast(podcastName, rssUrl, hasGroq, stepIndex);
      } catch (e) {
        onLog('  ❌ $podcastName 失敗: $e');
      }
      stepIndex++;
    }

    if (state.isCancelled) {
      onLog('Podcast Pipeline 已取消');
    } else {
      onLog('Podcast Pipeline 完成');
    }
  }

  Future<void> _processPodcast(
      String podcastName, String rssUrl, bool hasGroq, int stepIndex) async {
    final cache = _loadCache();
    final podDir = PodcastService.instance.podcastDir(podcastName);
    final ext = 'mp3';

    onLog('  讀取 RSS Feed...');
    final result = await PodcastService.instance.fetchEpisodes(rssUrl);
    final episodes = result.episodes;
    final feedTitle = result.title;
    onLog('  Feed: $feedTitle (${episodes.length} 集)');

    // Filter to new episodes not yet processed
    final newEps = <int>[];
    for (int i = 0; i < episodes.length; i++) {
      final ep = episodes[i];
      final key = '$podcastName|${ep.title}';
      if (!cache.containsKey(key)) {
        newEps.add(i);
      }
    }

    if (newEps.isEmpty) {
      onLog('  無新集數 (${cache.length} 集已處理過)');
      return;
    }

    onLog('  新集數: ${newEps.length} 集');
    int done = 0;
    int total = newEps.length;

    for (int i = 0; i < newEps.length; i++) {
      if (state.isCancelled) break;
      await state.waitIfPaused();

      final idx = newEps[i];
      final ep = episodes[idx];
      final key = '$podcastName|${ep.title}';
      final safeName = PodcastService.normalizeFileName(ep.title);
      final audioPath = '$podDir\\$safeName.$ext';
      final srtPath = audioPath.replaceAll('.$ext', '.srt');
      final txtPath = audioPath.replaceAll('.$ext', '.txt');

      final status = <String, dynamic>{
        'srt': false,
        'txt': false,
        'status': 'ok',
      };

      // --- Step 1: Download audio if not exists ---
      if (!await File(audioPath).exists()) {
        onLog('  [${i + 1}/$total] ⬇️ $safeName');
        try {
          await PodcastService.instance.downloadEpisode(
            rssUrl, idx,
            (pct) {
              final global = (done + pct) / total * 100;
              onProgress(global.toInt(), 100, stepIndex);
            },
            podcastName: podcastName,
          );
        } catch (e) {
          onLog('    ❌ 下載失敗: $e');
          status['status'] = 'error';
          cache[key] = status;
          _saveCache(cache);
          done++;
          onProgress(done * 100 ~/ total, 100, stepIndex);
          continue;
        }
      } else {
        onLog('  [${i + 1}/$total] ⏭️ $safeName (已存在)');
      }

      // --- Step 2: Try SRT download (skip if already exists) ---
      if (await File(srtPath).exists()) {
        status['srt'] = true;
        onLog('    ✅ 已有 SRT');
      } else {
        onLog('    🔍 搜尋 YouTube 字幕...');
        try {
          await PodcastService.instance.downloadSubtitles(
            ep.title, podcastName,
            onLog: (msg) {
              if (msg.startsWith('  ✅')) status['srt'] = true;
              onLog('    $msg');
            },
          );
        } catch (e) {
          onLog('    ⚠️ 字幕搜尋異常: $e');
        }
      }

      // --- Step 3: Transcribe with Groq if no SRT ---
      if (!status['srt'] as bool && hasGroq) {
        if (await File(txtPath).exists()) {
          status['txt'] = true;
          onLog('    ✅ 已有逐字稿');
        } else if (await File(audioPath).exists()) {
          onLog('    🎤 Groq 逐字稿處理中...');
          try {
            final text = await GroqService.instance.transcribeFile(
              filePath: audioPath,
              model: GroqService.instance.defaultModel,
              language: 'zh',
              onChunk: (chunk, pct) {
                final global = (done + (i < total - 1 ? pct / total : 0)) / total * 100;
                onProgress(global.toInt(), 100, stepIndex);
              },
            );
            await File(txtPath).writeAsString(text, flush: true);
            status['txt'] = true;
            onLog('    ✅ 逐字稿完成 (${text.length} 字)');
          } catch (e) {
            onLog('    ❌ 轉錄失敗: $e');
            status['status'] = 'error';
          }
        }
      } else if (!status['srt'] as bool && !hasGroq) {
        onLog('    ⚠️ 無 SRT 且未設定 Groq API Key，跳過轉錄');
      }

      cache[key] = status;
      _saveCache(cache);
      done++;
      onProgress(done * 100 ~/ total, 100, stepIndex);
    }

    // Summary
    final srtCount = cache.values.where((v) => v['srt'] == true).length;
    final txtCount = cache.values.where((v) => v['txt'] == true).length;
    final errCount = cache.values.where((v) => v['status'] == 'error').length;
    onLog('  $podcastName 完成: 總處理 ${cache.length} 集 (SRT $srtCount, 逐字稿 $txtCount, 錯誤 $errCount)');
  }
}
