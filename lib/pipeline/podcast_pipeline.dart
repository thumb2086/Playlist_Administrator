import 'dart:convert';
import 'dart:io';
import '../models/config_model.dart';
import '../models/podcast_episode.dart';
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

  Future<void> run() async {
    final config = ConfigService.instance.config;
    final subs = config.podcastSubscriptions;
    if (subs.isEmpty) {
      onLog('沒有訂閱任何 Podcast');
      return;
    }

    await GroqService.instance.loadFromEnv();
    // Also load from config if env didn't provide
    if (GroqService.instance.apiKey == null || GroqService.instance.apiKey!.isEmpty) {
      final cfgKey = ConfigService.instance.config.groqApiKey;
      if (cfgKey.isNotEmpty) GroqService.instance.setApiKey(cfgKey);
    }
    final hasGroq = GroqService.instance.apiKey != null &&
        GroqService.instance.apiKey!.isNotEmpty;

    onLog('Podcast 訂閱數: ${subs.length}');
    int stepIndex = 0;
    final subEntries = subs.entries.toList();

    for (int si = 0; si < subEntries.length; si++) {
      if (state.isCancelled) break;
      await state.waitIfPaused();

      final sub = subEntries[si];
      onLog('\n--- [${si + 1}/${subEntries.length}] ${sub.key} ---');

      try {
        await _processPodcast(sub.key, sub.value, hasGroq, stepIndex);
      } catch (e) {
        onLog('  ❌ ${sub.key} 失敗: $e');
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
    onLog('  Feed: ${result.title} (${episodes.length} 集)');

    // Build task list
    final tasks = <_PodTask>[];
    for (int i = 0; i < episodes.length; i++) {
      if (state.isCancelled) break;
      final ep = episodes[i];
      final key = '$podcastName|${ep.title}';
      if (!cache.containsKey(key) || (cache[key]!['srt'] != true && cache[key]!['txt'] != true)) {
        tasks.add(_PodTask(index: i, episode: ep, key: key));
      }
    }

    if (tasks.isEmpty) {
      onLog('  無新集數 (${cache.length} 集已處理過)');
      return;
    }
    onLog('  需處理: ${tasks.length} 集 (×4 並行)');
    final total = tasks.length;

    for (int i = 0; i < total; i += 4) {
      if (state.isCancelled) break;
      await state.waitIfPaused();
      if (state.isCancelled) break;

      final batch = tasks.skip(i).take(4).toList();
      await Future.wait(batch.map((t) => _processOne(t, podcastName, rssUrl, podDir, ext, cache, onLog)));

      final done = (i + batch.length).clamp(0, total);
      onProgress(done * 100 ~/ total, 100, stepIndex);
      _saveCache(cache);
      onLog('  進度: $done/$total');
    }

    // Post-processing: Groq for episodes without SRT (parallel with concurrency cap)
    if (hasGroq) {
      final needGroq = tasks.where((t) {
        final n = PodcastService.normalizeFileName(t.episode.title);
        return !File('$podDir\\$n.srt').existsSync() && !File('$podDir\\$n.txt').existsSync();
      }).toList();
      if (needGroq.isNotEmpty) {
        final c = ConfigService.instance.config.groqConcurrency;
        final concurrency = c < 1 ? 1 : (c > 8 ? 8 : c);
        onLog('  🎤 Groq 逐字稿: ${needGroq.length} 集 (×$concurrency 並行)');
        for (int i = 0; i < needGroq.length; i += concurrency) {
          if (state.isCancelled) break;
          await state.waitIfPaused();
          final batch = needGroq.skip(i).take(concurrency).toList();
          await Future.wait(batch.map((t) async {
            if (state.isCancelled) return;
            final name = PodcastService.normalizeFileName(t.episode.title);
            final audioPath = '$podDir\\$name.$ext';
            final txtPath = '$podDir\\$name.txt';
            if (!await File(audioPath).exists()) return;
            onLog('    🎤 $name');
            try {
              final text = await GroqService.instance.transcribeFile(
                filePath: audioPath, model: 'whisper-large-v3-turbo', language: 'zh',
              );
              await File(txtPath).writeAsString(text, flush: true);
              cache[t.key] = {'srt': false, 'txt': true, 'status': 'ok'};
              onLog('      ✅ (${text.length} 字)');
            } catch (e) {
              onLog('      ❌ $e');
              cache[t.key] = {'srt': false, 'txt': false, 'status': 'error'};
            }
          }));
          final done = (i + batch.length).clamp(0, needGroq.length) as int;
          _saveCache(cache);
          onLog('  🎤 進度: $done/${needGroq.length}');
        }
      }
    }

    final srtCount = cache.values.where((v) => v['srt'] == true).length;
    final txtCount = cache.values.where((v) => v['txt'] == true).length;
    final errCount = cache.values.where((v) => v['status'] == 'error').length;
    onLog('  $podcastName 完成: 總處理 ${cache.length} 集 (SRT $srtCount, 逐字稿 $txtCount, 錯誤 $errCount)');
  }

  Future<void> _srtToTxt(String srtPath, String txtPath) async {
    if (!await File(srtPath).exists()) return;
    try {
      final content = await File(srtPath).readAsString(encoding: utf8);
      final lines = content.split('\n');
      final textLines = <String>[];
      String last = '';
      for (final line in lines) {
        final t = line.trim();
        if (t.isEmpty) continue;
        if (RegExp(r'^\d+$').hasMatch(t)) continue;
        if (t.contains('-->')) continue;
        final clean = t.replaceAll(RegExp(r'<[^>]+>'), '');
        if (clean.isEmpty || clean == last) continue;
        textLines.add(clean);
        last = clean;
      }
      await File(txtPath).writeAsString(textLines.join('\n'), flush: true);
    } catch (_) {}
  }

  Future<void> _processOne(
    _PodTask t, String podcastName, String rssUrl, String podDir, String ext,
    Map<String, Map<String, dynamic>> cache, void Function(String) onLog,
  ) async {
    final name = PodcastService.normalizeFileName(t.episode.title);
    final audioPath = '$podDir\\$name.$ext';
    final srtPath = '$podDir\\$name.srt';
    final txtPath = '$podDir\\$name.txt';

    onLog('  [${t.index}] ⬇️ $name');
    if (!await File(audioPath).exists()) {
      try {
        await PodcastService.instance.downloadEpisode(rssUrl, t.index, (pct) {},
          podcastName: podcastName,
        );
      } catch (e) {
        onLog('    ❌ 下載失敗');
        cache[t.key] = {'srt': false, 'txt': false, 'status': 'error'};
        return;
      }
    }

    onLog('    🔍 $name');
    if (!await File(srtPath).exists()) {
      if (await File(txtPath).exists()) {
        cache[t.key] = {'srt': false, 'txt': true, 'status': 'ok'};
        return;
      }
      await PodcastService.instance.downloadSubtitles(t.episode.title, podcastName,
        onLog: (msg) => onLog('      $msg'),
      );
      if (await File(srtPath).exists()) {
        await _srtToTxt(srtPath, txtPath);
      }
    }

    cache[t.key] = {
      'srt': await File(srtPath).exists(),
      'txt': await File(txtPath).exists(),
      'status': 'ok',
    };
  }
}

class _PodTask {
  final int index;
  final PodcastEpisode episode;
  final String key;
  _PodTask({required this.index, required this.episode, required this.key});
}
