import 'dart:async';
import 'dart:convert';
import 'dart:io';
import '../models/podcast_episode.dart';
import '../models/pipeline_step.dart';
import '../services/config_service.dart';
import '../services/podcast_service.dart';
import '../services/groq_service.dart';
import '../version.dart';

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

    final _stamp = DateTime.now().toString().substring(0, 19);
    final _ver = appVersion.startsWith('v') ? appVersion : 'v$appVersion';
    onLog('$_stamp  Playlist Administrator $_ver');

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
      final ts = DateTime.now().toString().substring(0, 19);
      onLog('\n$ts --- [${si + 1}/${subEntries.length}] ${sub.key} ---');

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

    // Build task list — check disk synchronously so episodes that already
    // have srt/txt are resolved instantly (no network, no batch waiting).
    // Only episodes truly missing files enter the parallel batch.
    final tasks = <_PodTask>[];
    int alreadyHave = 0;
    for (int i = 0; i < episodes.length; i++) {
      if (state.isCancelled) break;
      final ep = episodes[i];
      final key = '$podcastName|${ep.title}';
      final name = PodcastService.normalizeFileName(ep.title);
      final srtPath = _findSrt(podDir, name);
      final txtPath = '$podDir\\$name.txt';
      final hasSrt = srtPath != null;
      final hasTxt = File(txtPath).existsSync();
      if (hasSrt || hasTxt) {
        // Backfill missing txt right here (fast, local).
        if (hasSrt && !hasTxt) {
          await _srtToTxt(srtPath!, txtPath);
        }
        cache[key] = {
          'srt': hasSrt,
          'txt': hasTxt || await File(txtPath).existsSync(),
          'yt_status': hasSrt ? 'found' : (cache[key]?['yt_status'] ?? ''),
          'status': 'ok',
        };
        alreadyHave++;
        continue;
      }
      if (!cache.containsKey(key) || (cache[key]!['srt'] != true && cache[key]!['txt'] != true)) {
        tasks.add(_PodTask(index: i, episode: ep, key: key));
      }
    }
    _saveCache(cache);

    if (tasks.isEmpty) {
      onLog('  無新集數 (${alreadyHave} 集已處理過)');
      return;
    }
    onLog('  需處理: ${tasks.length} 集 (×4 並行)');
    final total = tasks.length;
    final groqQueue = <_PodTask>[];
    int groqActive = 0;
    final groqLimit = ConfigService.instance.config.groqConcurrency.clamp(1, 8);

    Future<void> _tryGroq() async {
      while (groqActive < groqLimit && groqQueue.isNotEmpty && !state.isCancelled) {
        final t = groqQueue.removeAt(0);
        groqActive++;
        // fire and forget: continue processing queue while this runs
        unawaited(_runGroq(t, podcastName, podDir, ext, cache, onLog, state).then((_) {
          groqActive--;
          _saveCache(cache);
          _tryGroq(); // kick next
        }));
      }
    }

    for (int i = 0; i < total; i += 4) {
      if (state.isCancelled) break;
      await state.waitIfPaused();
      if (state.isCancelled) break;

      final batch = tasks.skip(i).take(4).toList();
      await Future.wait(batch.asMap().entries.map((e) async {
        final needGroq = await _processOne(e.value, podcastName, rssUrl, podDir, ext, cache, onLog);
        // Save immediately after each episode so progress is never lost.
        _saveCache(cache);
        if (needGroq && hasGroq) {
          groqQueue.add(e.value);
          _tryGroq();
        }
      }));

      final done = (i + batch.length).clamp(0, total);
      onProgress(done * 100 ~/ total, 100, stepIndex);
      onLog('  進度: $done/$total');
    }

    // Wait for remaining Groq
    while (groqActive > 0 && !state.isCancelled) {
      await Future.delayed(const Duration(seconds: 1));
    }

    final srtCount = cache.values.where((v) => v['srt'] == true).length;
    final txtCount = cache.values.where((v) => v['txt'] == true).length;
    final errCount = cache.values.where((v) => v['status'] == 'error').length;
    onLog('  $podcastName 完成: 總處理 ${cache.length} 集 (SRT $srtCount, 逐字稿 $txtCount, 錯誤 $errCount)');
  }

  /// Resolve the actual SRT file for an episode. yt-dlp may save
  /// subtitles as `name.srt` or with a language suffix such as
  /// `name.zh-TW.srt` / `name.zh-Hans.srt`. Returns null when none exists.
  String? _findSrt(String podDir, String name) {
    final plain = '$podDir\\$name.srt';
    if (File(plain).existsSync()) return plain;
    final dir = Directory(podDir);
    if (!dir.existsSync()) return null;
    try {
      final prefix = '$name.';
      for (final f in dir.listSync()) {
        final fn = f.uri.pathSegments.last;
        if (fn.startsWith(prefix) && fn.toLowerCase().endsWith('.srt')) {
          return f.path;
        }
      }
    } catch (_) {}
    return null;
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

  Future<bool> _processOne(
    _PodTask t, String podcastName, String rssUrl, String podDir, String ext,
    Map<String, Map<String, dynamic>> cache, void Function(String) onLog,
  ) async {
    final name = PodcastService.normalizeFileName(t.episode.title);
    final audioPath = '$podDir\\$name.$ext';
    final srtPath = _findSrt(podDir, name);
    final txtPath = '$podDir\\$name.txt';

    // Download audio if missing
    if (!await File(audioPath).exists()) {
      onLog('  [${t.index}] ⬇️ $name');
      try {
        await PodcastService.instance.downloadEpisode(rssUrl, t.index, (pct) {},
          podcastName: podcastName,
        );
      } catch (e) {
        onLog('    ❌ 下載失敗');
        cache[t.key] = {'srt': false, 'txt': false, 'yt_status': '', 'status': 'error'};
        return false;
      }
    }

    // Skip if already have result
    if (srtPath != null || await File(txtPath).exists()) {
      // SRT exists but TXT missing (e.g. subtitles grabbed by external tool):
      // convert now so the transcript is available.
      if (srtPath != null && !await File(txtPath).exists()) {
        await _srtToTxt(srtPath, txtPath);
        cache[t.key] = {'srt': true, 'txt': await File(txtPath).exists(), 'yt_status': 'found', 'status': 'ok'};
      }
      return false;
    }

    // YT search (skip if previously failed)
    final prevYt = cache[t.key]?['yt_status'] as String?;
    if (prevYt == 'not_found') {
      if (srtPath != null || await File(txtPath).exists()) {
        if (srtPath != null) await _srtToTxt(srtPath, txtPath);
        cache[t.key] = {'srt': srtPath != null, 'txt': await File(txtPath).exists(), 'yt_status': 'found', 'status': 'ok'};
        return false;
      }
      onLog('    ⏭️ $name (YT 上次已搜過)');
      cache[t.key] = {'srt': false, 'txt': false, 'yt_status': 'not_found', 'status': 'no_sub'};
      return true; // need Groq
    }

    onLog('    🔍 $name');
    // Stagger only real YT searches (0~1.2s) to avoid rate limit,
    // never delay episodes that skip instantly.
    await Future.delayed(Duration(milliseconds: (t.index % 4) * 300));
    final subResult = await PodcastService.instance.downloadSubtitles(t.episode.title, podcastName,
      onLog: (msg) => onLog('      $msg'),
    );
    final srtAfter = _findSrt(podDir, name);
    if (subResult == PodcastSubtitleResult.found && srtAfter != null) {
      await _srtToTxt(srtAfter, txtPath);
      cache[t.key] = {'srt': true, 'txt': true, 'yt_status': 'found', 'status': 'ok'};
      return false; // SRT found, no Groq needed
    }
    if (subResult == PodcastSubtitleResult.notFound) {
      cache[t.key] = {'srt': false, 'txt': false, 'yt_status': 'not_found', 'status': 'no_sub'};
    } else {
      // Transient failure (network / rate limit): do NOT burn not_found
      // into the cache, so YouTube is retried on a later run.
      cache[t.key] = {'srt': false, 'txt': false, 'yt_status': '', 'status': 'no_sub'};
    }
    return true; // need Groq
  }

  Future<void> _runGroq(
    _PodTask t, String podcastName, String podDir, String ext,
    Map<String, Map<String, dynamic>> cache, void Function(String) onLog,
    PipelineState state,
  ) async {
    if (state.isCancelled) return;
    final name = PodcastService.normalizeFileName(t.episode.title);
    final audioPath = '$podDir\\$name.$ext';
    final srtPath = _findSrt(podDir, name);
    final txtPath = '$podDir\\$name.txt';
    if (!await File(audioPath).exists()) return;
    if (srtPath != null || await File(txtPath).exists()) return;
    onLog('    🎤 $name');
    try {
      final text = await GroqService.instance.transcribeFile(
        filePath: audioPath, model: GroqService.instance.defaultModel, language: 'zh',
      );
      await File(txtPath).writeAsString(text, flush: true);
      cache[t.key] = {'srt': false, 'txt': true, 'yt_status': 'not_found', 'status': 'ok'};
      onLog('      ✅ (${text.length} 字)');
    } catch (e) {
      onLog('      ❌ $e');
      // Record failure so the episode is retried on next run instead of
      // being treated as done. Keep yt_status='' so YouTube (free) is
      // retried before spending Groq credits again.
      cache[t.key] = {'srt': false, 'txt': false, 'yt_status': '', 'status': 'error'};
    }
  }
}

class _PodTask {
  final int index;
  final PodcastEpisode episode;
  final String key;
  _PodTask({required this.index, required this.episode, required this.key});
}
