import 'dart:convert';
import 'dart:io';
import 'config_service.dart';

class LufsService {
  static final LufsService _instance = LufsService._();
  static LufsService get instance => _instance;
  LufsService._();

  String get _cacheDir => ConfigService.instance.config.basePath;
  String _cacheFile(String fmt) => '$_cacheDir\\${fmt}_lufs_cache.json';

  Map<String, double> _load(String fmt) {
    try {
      final f = File(_cacheFile(fmt));
      if (!f.existsSync()) return {};
      final json = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
      return json.map((k, v) => MapEntry(k, (v as num).toDouble()));
    } catch (_) { return {}; }
  }

  void _save(String fmt, Map<String, double> cache) {
    try {
      File(_cacheFile(fmt)).writeAsStringSync(
        jsonEncode(cache), flush: true);
    } catch (_) {}
  }

  int cachedCount(String fmt) => _load(fmt).length;

  String? _ffmpegPath;

  Future<String> _resolveFfmpeg() async {
    if (_ffmpegPath != null) return _ffmpegPath!;
    final cfg = ConfigService.instance.config.ffmpegPath;
    if (cfg.isNotEmpty && File(cfg).existsSync()) {
      _ffmpegPath = cfg; return cfg;
    }
    // Search PATH for ffmpeg.exe
    final pathEnv = Platform.environment['PATH'] ?? '';
    for (final dir in pathEnv.split(';')) {
      if (dir.trim().isEmpty) continue;
      try {
        final candidate = '${dir.trim()}\\ffmpeg.exe';
        if (File(candidate).existsSync()) {
          _ffmpegPath = candidate; return candidate;
        }
      } catch (_) {}
    }
    _ffmpegPath = 'ffmpeg';
    return 'ffmpeg';
  }

  /// Measure LUFS for all uncached files of given format.
  /// Calls [onProgress] with (done, total) after each batch.
  Future<void> measureFormat(String fmt, {
    required void Function(String log) onLog,
    void Function(int done, int total)? onProgress,
    int concurrency = 8,
  }) async {
    final lib = ConfigService.instance.config.libraryPath;
    if (lib.isEmpty) { onLog('Library path not configured'); return; }

    final cache = _load(fmt);
    final allFiles = <String>[];
    final libDir = Directory(lib);
    if (!await libDir.exists()) { onLog('Library not found: $lib'); return; }

    await for (final e in libDir.list(recursive: true, followLinks: false)) {
      if (e is File && e.path.toLowerCase().endsWith('.$fmt')) {
        allFiles.add(e.path);
      }
    }

    final toMeasure = allFiles.where((f) => !cache.containsKey(f)).toList();
    if (toMeasure.isEmpty) {
      onLog('[$fmt] 所有 ${allFiles.length} 個檔案已快取');
      return;
    }
    onLog('[$fmt] ${allFiles.length} 個檔案，${cache.length} 已快取，需測量 ${toMeasure.length}');

    int done = 0;
    int total = toMeasure.length;
    int lastSave = 0;

    // Process in batches
    for (int i = 0; i < total; i += concurrency) {
      final batch = toMeasure.skip(i).take(concurrency).toList();
      final futures = <Future<void>>[];
      for (final path in batch) {
        futures.add(_measureOne(path, cache, (v) { cache[path] = v; }));
      }
      await Future.wait(futures);
      done += batch.length;
      onProgress?.call(done, total);

      // Save every 25 files
      if (done - lastSave >= 25) {
        _save(fmt, cache);
        lastSave = done;
      }
    }

    _save(fmt, cache);
    onLog('[$fmt] 測量完成，共 ${cache.length} 個檔案');
  }

  Future<void> _measureOne(String path, Map<String, double> cache, void Function(double) onResult) async {
    final ffmpeg = await _resolveFfmpeg();
    try {
      final proc = await Process.start(ffmpeg, [
        '-t', '30', '-i', path,
        '-af', 'loudnorm=print_format=json',
        '-f', 'null', '-', '-hide_banner', '-y',
      ]);
      // Drain both stdout and stderr to prevent deadlock
      final stderr = await proc.stderr.transform(utf8.decoder).join();
      proc.stdout.drain();
      final exit = await proc.exitCode;
      if (exit != 0) { onResult(-14.0); return; }

      final jsonStart = stderr.lastIndexOf('{');
      if (jsonStart >= 0) {
        try {
          final data = jsonDecode(stderr.substring(jsonStart)) as Map<String, dynamic>;
          final inputI = data['input_i'];
          if (inputI != null) {
            onResult((inputI as num).toDouble());
            return;
          }
        } catch (_) {}
      }
      onResult(-14.0);
    } catch (_) {
      onResult(-14.0);
    }
  }

  /// Normalize MP3s deviating from -14 LUFS by more than [tolerance].
  Future<void> normalizeMp3({
    required void Function(String log) onLog,
    void Function(int done, int total)? onProgress,
    double tolerance = 2.0,
  }) async {
    final lib = ConfigService.instance.config.libraryPath;
    if (lib.isEmpty) { onLog('Library path not configured'); return; }

    final cache = _load('mp3');
    if (cache.isEmpty) { onLog('MP3 LUFS 快取為空，跳過 normalize'); return; }

    final target = -14.0;
    final toNormalize = <String, double>{};
    for (final e in cache.entries) {
      if ((e.value - target).abs() > tolerance) {
        toNormalize[e.key] = e.value;
      }
    }

    if (toNormalize.isEmpty) {
      onLog('所有 MP3 已在 ${target}±$tolerance LUFS 範圍內');
      return;
    }

    onLog('Normalize ${toNormalize.length} 個偏離 ${target} 的 MP3...');
    final ffmpeg = await _resolveFfmpeg();
    int done = 0;
    int total = toNormalize.length;

    for (final e in toNormalize.entries) {
      final absPath = e.key;
      if (!await File(absPath).exists()) continue;

      final base = absPath.substring(0, absPath.lastIndexOf('.'));
      final tmp = '${base}_tmp.mp3';

      try {
        final proc = await Process.start(ffmpeg, [
          '-y', '-i', absPath,
          '-af', 'loudnorm=I=$target:TP=-1:LRA=7',
          '-c:a', 'libmp3lame', '-q:a', '2', tmp,
        ]);
        proc.stdout.drain();
        await proc.stderr.drain();
        final code = await proc.exitCode;

        if (code == 0 && await File(tmp).exists()) {
          await File(tmp).rename(absPath);
          cache[absPath] = target;
          onLog('  ✅ ${absPath.split('\\').last}  (${e.value.toStringAsFixed(1)} → $target)');
        } else {
          onLog('  ❌ ${absPath.split('\\').last} normalize 失敗');
        }
      } catch (ex) {
        onLog('  ⚠️ ${absPath.split('\\').last}: $ex');
      }

      done++;
      onProgress?.call(done, total);
      if (done % 10 == 0) _save('mp3', cache);
    }

    _save('mp3', cache);
    onLog('Normalize 完成，已處理 $done 個檔案');
  }
}
