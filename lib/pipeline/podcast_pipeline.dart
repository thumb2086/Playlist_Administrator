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

    // Build task list: episodes that need processing
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
    onLog('  需處理: ${tasks.length} 集');

    onLog('  需處理: ${tasks.length} 集 (×4 並行)');
    final total = tasks.length;
    const concurrency = 4;

    for (int i = 0; i < total; i += concurrency) {
      if (state.isCancelled) break;
      await state.waitIfPaused();
      if (state.isCancelled) break;

      final batch = tasks.skip(i).take(concurrency).toList();

      final futures = <Future<void>>[];
      for (int j = 0; j < batch.length; j++) {
        futures.add(_processOneEpisode(
          batch[j], podcastName, rssUrl, podDir, ext, cache,
        ));
      }
      await Future.wait(futures);

      final done = (i + batch.length).clamp(0, total);
      onProgress(done * 100 ~/ total, 100, stepIndex);
      _saveCache(cache);
      onLog('  進度: $done/$total');
    }

    // Groq post-processing: transcribe episodes without SRT (one at a time)
    if (hasGroq) {
      final needGroq = <_PodTask>[];
      for (final t in tasks) {
        final name = PodcastService.normalizeFileName(t.episode.title);
        if (!await File('$podDir\\$name.srt').exists() && !await File('$podDir\\$name.txt').exists()) {
          needGroq.add(t);
        }
      }
      if (needGroq.isNotEmpty) {
        onLog('  🎤 Groq 逐字稿: ${needGroq.length} 集 (×1 不阻塞)');
        for (int i = 0; i < needGroq.length; i++) {
          if (state.isCancelled) break;
          final t = needGroq[i];
          final name = PodcastService.normalizeFileName(t.episode.title);
          final audioPath = '$podDir\\$name.$ext';
          final txtPath = '$podDir\\$name.txt';
          if (!await File(audioPath).exists()) continue;
          onLog('    [${i + 1}/${needGroq.length}] 🎤 $name');
          try {
            final text = await GroqService.instance.transcribeFile(
              filePath: audioPath,
              model: GroqService.instance.defaultModel,
              language: 'zh',
            );
            await File(txtPath).writeAsString(text, flush: true);
            cache[t.key] = {'srt': false, 'txt': true, 'status': 'ok'};
            _saveCache(cache);
            onLog('      ✅ (${text.length} 字)');
          } catch (e) {
            onLog('      ❌ $e');
          }
        }
      } else {
        onLog('  ⏭️ Groq 無需處理');
      }
    }
  }

  Future<void> _runBatch(List<_PodTask> tasks, int concurrency, Future<void> Function(_PodTask, int index, int total) fn) async {
    final total = tasks.length;
    for (int i = 0; i < total; i += concurrency) {
      if (state.isCancelled) break;
      await state.waitIfPaused();
      if (state.isCancelled) break;
      final batch = tasks.skip(i).take(concurrency).toList();
      final futures = <Future<void>>[];
      for (int j = 0; j < batch.length; j++) {
        futures.add(fn(batch[j], i + j, total));
      }
      await Future.wait(futures);
      if (i + concurrency < total) {
        await Future.delayed(const Duration(milliseconds: 300));
      }
    }
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

  Future<void> _processOneEpisode(
    _PodTask t, String podcastName, String rssUrl, String podDir, String ext,
    Map<String, Map<String, dynamic>> cache,
  ) async {
    final name = PodcastService.normalizeFileName(t.episode.title);
    final audioPath = '$podDir\\$name.$ext';
    final srtPath = '$podDir\\$name.srt';
    final txtPath = '$podDir\\$name.txt';

    if (!await File(audioPath).exists()) {
      try {
        await PodcastService.instance.downloadEpisode(rssUrl, t.index, (pct) {},
          podcastName: podcastName,
        );
      } catch (e) {
        cache[t.key] = {'srt': false, 'txt': false, 'status': 'error'};
        return;
      }
    }

    if (!await File(srtPath).exists()) {
      await PodcastService.instance.downloadSubtitles(t.episode.title, podcastName,
        onLog: (msg) => onLog('    $msg'),
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
