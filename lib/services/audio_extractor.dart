import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'package:path/path.dart' as p;

// Port of 大拇哥實驗室 AudioExtractor — DeepFilterNet 降噪 only (RNNoise/afftdn removed).

class AudioTrack {
  final int index;
  final String codec;
  final int channels;
  final int sampleRate;
  final int bitRate;
  const AudioTrack({required this.index, required this.codec, required this.channels, required this.sampleRate, required this.bitRate});
  factory AudioTrack.fromJson(Map<String, dynamic> j) => AudioTrack(
    index: j['index'] as int, codec: j['codec_name'] as String? ?? '?',
    channels: int.tryParse(j['channels']?.toString() ?? '') ?? 0,
    sampleRate: int.tryParse(j['sample_rate']?.toString() ?? '') ?? 0,
    bitRate: int.tryParse(j['bit_rate']?.toString() ?? '') ?? 0,
  );
  String get chLabel => '$channels ch';
  String get srLabel => sampleRate == 0 ? '?' : '${(sampleRate / 1000).toStringAsFixed(0)}kHz';
  String get brLabel => bitRate == 0 ? '?' : '${(bitRate / 1000).toStringAsFixed(0)}k';
  String get detail => 't$index: $codec $chLabel $srLabel ${bitRate > 0 && bitRate < 10000 ? '⚠silence' : brLabel}';
}

class VideoFile {
  final String path;
  final String name;
  final int size;
  final double duration;
  final List<AudioTrack> tracks;
  final DateTime mtime;
  VideoFile({required this.path, required this.name, required this.size, required this.duration, required this.tracks, required this.mtime});
  int get trackCount => tracks.length;
  String get sizeLabel {
    final b = size;
    if (b < 1024) return '${b}B';
    if (b < 1048576) return '${(b / 1024).toStringAsFixed(1)}KB';
    if (b < 1073741824) return '${(b / 1048576).toStringAsFixed(1)}MB';
    return '${(b / 1073741824).toStringAsFixed(1)}GB';
  }
  String get durLabel {
    final t = duration.toInt();
    final h = t ~/ 3600;
    final m = (t % 3600) ~/ 60;
    final s = t % 60;
    return h > 0 ? '${h}h${m.toString().padLeft(2, '0')}m' : '${m}m${s.toString().padLeft(2, '0')}s';
  }
  Map<String, dynamic> toJson() => {
    'path': path, 'name': name, 'size': size, 'duration': duration, 'mtime': mtime.toIso8601String(),
    'tracks': tracks.map((t) => {'index': t.index, 'codec_name': t.codec, 'channels': t.channels, 'sample_rate': t.sampleRate, 'bit_rate': t.bitRate}).toList(),
  };
  factory VideoFile.fromJson(Map<String, dynamic> j) => VideoFile(
    path: j['path'] as String, name: j['name'] as String, size: j['size'] as int,
    duration: (j['duration'] as num).toDouble(),
    tracks: (j['tracks'] as List).map((t) => AudioTrack.fromJson(t as Map<String, dynamic>)).toList(),
    mtime: DateTime.tryParse(j['mtime'] as String? ?? '') ?? DateTime(2000),
  );
  int durationSeconds() {
    final t = duration.toInt();
    return t < 0 ? 0 : t;
  }
}

class AudioExtractorConfig {
  String sourceDir, outputDir, format, bitrate, deepFilterPath;
  int lufsTarget, silenceThreshold, workers;
  Map<int, String> trackNames;
  // 只有勾選的軌（預設 Mic=3）才會跑 DeepFilterNet；其他軌純 ffmpeg 抽出。
  Set<int> denoiseTracks;
  AudioExtractorConfig({
    this.sourceDir = '', this.outputDir = '', this.format = 'aac', this.bitrate = '384k',
    this.lufsTarget = -14, this.silenceThreshold = 10000, this.workers = 2,
    this.deepFilterPath = 'deepFilter', Map<int, String>? trackNames,
    Set<int>? denoiseTracks,
  }) : trackNames = trackNames ?? {1: 'Mix', 2: 'Game', 3: 'Mic', 5: 'DC'},
       denoiseTracks = denoiseTracks ?? {3};
  Map<String, dynamic> toJson() => {
    'sourceDir': sourceDir, 'outputDir': outputDir, 'format': format, 'bitrate': bitrate,
    'lufsTarget': lufsTarget, 'silenceThreshold': silenceThreshold, 'workers': workers,
    'deepFilterPath': deepFilterPath,
    'trackNames': trackNames.map((k, v) => MapEntry('$k', v)),
    'denoiseTracks': denoiseTracks.toList(),
  };
  factory AudioExtractorConfig.fromJson(Map<String, dynamic> j) => AudioExtractorConfig(
    sourceDir: j['sourceDir'] as String? ?? '',
    outputDir: j['outputDir'] as String? ?? '',
    format: j['format'] as String? ?? 'aac',
    bitrate: j['bitrate'] as String? ?? '384k',
    lufsTarget: j['lufsTarget'] as int? ?? -14,
    silenceThreshold: j['silenceThreshold'] as int? ?? 10000,
    workers: (j['workers'] as num?)?.toInt() ?? 2,
    deepFilterPath: j['deepFilterPath'] as String? ?? 'deepFilter',
    trackNames: (j['trackNames'] as Map<String, dynamic>? ?? {}).map((k, v) => MapEntry(int.parse(k), v as String)),
    denoiseTracks: ((j['denoiseTracks'] as List<dynamic>?) ?? [3]).map((e) => (e as num).toInt()).toSet(),
  );
}

class AudioExtractorStore {
  static String get _dir => '${Platform.environment['LOCALAPPDATA'] ?? Platform.environment['TEMP'] ?? '.'}\\AudioExtractor';
  static String get configFile => '$_dir\\config.json';
  static String get activeFile => '$_dir\\active.txt';
  static String cacheFile(String dir) => '$_dir\\cache_${_safe(dir)}.json';
  static String _safe(String s) => s.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_');

  static String profileFile(String name) =>
      name.isEmpty || name == 'default' ? configFile : '$_dir\\config_${_safe(name)}.json';

  static String activeProfile() {
    try {
      final s = File(activeFile).readAsStringSync().trim();
      if (s.isNotEmpty) return s;
    } catch (_) {}
    return 'default';
  }
  static void setActiveProfile(String name) {
    Directory(_dir).createSync(recursive: true);
    File(activeFile).writeAsStringSync(name);
  }
  static List<String> listProfiles() {
    final d = Directory(_dir);
    if (!d.existsSync()) return const ['default'];
    final names = <String>[];
    for (final f in d.listSync()) {
      if (f is File && f.path.contains('config_') && f.path.endsWith('.json')) {
        final base = f.path.split(Platform.pathSeparator).last;
        names.add(base.substring('config_'.length, base.length - '.json'.length));
      }
    }
    names.sort();
    return ['default', ...names];
  }

  static AudioExtractorConfig loadConfig([String name = 'default']) {
    try {
      return AudioExtractorConfig.fromJson(
          jsonDecode(File(profileFile(name)).readAsStringSync()) as Map<String, dynamic>);
    } catch (_) {
      return AudioExtractorConfig();
    }
  }
  static void saveConfig(AudioExtractorConfig c, [String name = 'default']) {
    Directory(_dir).createSync(recursive: true);
    File(profileFile(name)).writeAsStringSync(jsonEncode(c.toJson()));
  }

  static List<VideoFile>? loadCache(String dir) {
    try {
      final f = File(cacheFile(dir));
      if (!f.existsSync()) return null;
      final data = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
      final cached = (data['files'] as List).map((e) => VideoFile.fromJson(e as Map<String, dynamic>)).toList();
      final mtimes = (data['mtimes'] as List<dynamic>).map((e) => DateTime.tryParse(e as String) ?? DateTime(2000)).toList();
      for (int i = 0; i < cached.length && i < mtimes.length; i++) {
        final cur = File(cached[i].path);
        if (!cur.existsSync() || cur.lastModifiedSync().millisecondsSinceEpoch != mtimes[i].millisecondsSinceEpoch) return null;
      }
      return cached;
    } catch (_) {
      return null;
    }
  }
  static void saveCache(String dir, List<VideoFile> files) {
    try {
      Directory(_dir).createSync(recursive: true);
      File(cacheFile(dir)).writeAsStringSync(jsonEncode({
        'files': files.map((f) => f.toJson()).toList(),
        'mtimes': files.map((f) => f.mtime.toIso8601String()).toList(),
      }));
    } catch (_) {}
  }
}

class AudioExtractorEngine {
  // deepFilter 每個 process 會載入一個 Python + 神經網路模型，記憶體成本極高。
  // 一律最多 1 個同時在跑（ffmpeg 抽出/編碼階段照樣平行）。
  static int _dfRunning = 0;
  static final List<Completer<void>> _dfWaiters = [];

  static Future<void> _acquireDfSlot() async {
    while (_dfRunning >= 1) {
      final c = Completer<void>();
      _dfWaiters.add(c);
      await c.future;
    }
    _dfRunning++;
  }

  static void _releaseDfSlot() {
    _dfRunning--;
    if (_dfWaiters.isNotEmpty) _dfWaiters.removeAt(0).complete();
  }

  static String? _ffmpegCache, _ffprobeCache;
  static String ffmpegExe() => _ffmpegCache ??= _findExe('ffmpeg');
  static String ffprobeExe() => _ffprobeCache ??= _findExe('ffprobe');
  static String _findExe(String name) {
    final pathEnv = Platform.environment['PATH'] ?? '';
    for (final d in pathEnv.split(';')) {
      final dir = d.trim();
      if (dir.isEmpty) continue;
      final f = File('$dir\\$name.exe');
      if (f.existsSync()) return f.path;
    }
    return name;
  }

  static Future<VideoFile?> probe(String path) async {
    try {
      final r = await Process.run(ffprobeExe(), [
        '-v', 'quiet', '-print_format', 'json',
        '-show_entries', 'stream=index,codec_type,codec_name,channels,sample_rate,bit_rate:format=duration,size', path,
      ]).timeout(const Duration(seconds: 30));
      if (r.exitCode != 0) return null;
      final data = jsonDecode(r.stdout as String) as Map<String, dynamic>;
      final fmt = data['format'] as Map<String, dynamic>? ?? {};
      final streams = data['streams'] as List<dynamic>? ?? [];
      return VideoFile(
        path: path, name: p.basename(path),
        size: int.tryParse(fmt['size']?.toString() ?? '') ?? 0,
        duration: double.tryParse(fmt['duration']?.toString() ?? '') ?? 0,
        mtime: File(path).lastModifiedSync(),
        tracks: streams.where((s) => (s as Map<String, dynamic>)['codec_type'] == 'audio')
            .map((s) => AudioTrack.fromJson(s as Map<String, dynamic>)).toList(),
      );
    } catch (_) {
      return null;
    }
  }

  static Future<void> runParallel({
    required List<({String src, int trackId, int sampleRate, String trackName, bool denoise})> jobs,
    required AudioExtractorConfig cfg,
    required void Function(String) onLog,
    required void Function() onProgress,
    required bool Function() canceled,
  }) async {
    if (jobs.isEmpty) return;
    // ffmpeg 抽出/編碼可平行，但 worker 太多仍會堆高記憶體；deepFilter 階段
    // 另有訊號燈保證同時只跑 1 個（模型載入是主要 RAM 殺手）。
    final workers = math.max(1, math.min(2, math.min(cfg.workers, jobs.length)));
    final q = List.of(jobs);
    final active = <Process>[];
    await Future.wait(List.generate(workers, (_) async {
      while (q.isNotEmpty) {
        if (canceled()) {
          for (final p in active) {
            try { p.kill(); } catch (_) {}
          }
          return;
        }
        final job = q.removeAt(0);
        final d = Directory(cfg.outputDir);
        if (!await d.exists()) await d.create(recursive: true);
        final ext = switch (cfg.format) { 'wav' => '.wav', 'flac' => '.flac', _ => '.m4a' };
        final stem = p.basenameWithoutExtension(job.src);
        final name = job.trackName.isNotEmpty ? '${stem}_${job.trackName}' : '${stem}_track${job.trackId}';
        final out = p.join(cfg.outputDir, '$name$ext');
        if (await File(out).exists()) {
          onLog('SKIP ${p.basename(out)} (exists)');
          onProgress();
          continue;
        }
        try {
          final err = job.denoise
              ? await _extractDf(job, out, cfg, active)
              : await _extractPlain(job, out, cfg, active);
          onLog(err == null ? 'OK  ${p.basename(out)}' : 'FAIL ${p.basename(out)}: $err');
        } catch (e) {
          onLog('FAIL ${p.basename(out)}: $e');
        }
        onProgress();
      }
    }));
  }

  static Future<String?> _run(List<String> args, List<Process> active, {String? workDir}) async {
    Process? proc;
    final sb = StringBuffer();
    for (int attempt = 0; attempt < 3; attempt++) {
      try {
        proc = await Process.start(args[0], args.sublist(1), workingDirectory: workDir);
        break;
      } catch (e) {
        if (attempt == 2) return 'launch failed: $e';
        await Future<void>.delayed(const Duration(milliseconds: 800));
      }
    }
    if (proc == null) return 'launch failed';
    active.add(proc);
    proc.stderr.transform(const Utf8Decoder(allowMalformed: true)).listen(sb.write);
    try {
      final code = await proc.exitCode.timeout(const Duration(hours: 1));
      if (code == 0) return null;
      var e = sb.toString().trim();
      if (e.length > 200) e = e.substring(0, 200);
      return e.isEmpty ? 'exit $code' : e.replaceAll('\n', ' ');
    } on TimeoutException {
      try { proc.kill(); } catch (_) {}
      return 'timeout (killed)';
    } finally {
      active.remove(proc);
    }
  }

  /// 純 ffmpeg 抽出：直接轉目標格式 + loudnorm（非降噪軌用，記憶體低）。
  static Future<String?> _extractPlain(
      ({String src, int trackId, int sampleRate, String trackName, bool denoise}) job,
      String out, AudioExtractorConfig cfg, List<Process> active) async {
    final args = [ffmpegExe(), '-y', '-i', job.src, '-map', '0:${job.trackId}', '-vn'];
    if (cfg.format == 'aac') {
      args.addAll(['-c:a', 'aac', '-b:a', cfg.bitrate]);
      if (job.sampleRate > 0) args.addAll(['-ar', '${job.sampleRate}']);
      args.addAll(['-af', 'loudnorm=I=${cfg.lufsTarget}:LRA=1:TP=-1']);
    } else if (cfg.format == 'flac') {
      args.addAll(['-c:a', 'flac']);
    } else {
      args.addAll(['-c:a', 'pcm_s16le']);
    }
    args.add(out);
    return _run(args, active);
  }

  /// ffmpeg 抽出 wav → DeepFilterNet 降噪 → ffmpeg 轉目標格式 + loudnorm。
  static Future<String?> _extractDf(
      ({String src, int trackId, int sampleRate, String trackName, bool denoise}) job,
      String out, AudioExtractorConfig cfg, List<Process> active) async {
    final tmpDir = Directory.systemTemp;
    final wav = p.join(tmpDir.path, 'df_${p.basenameWithoutExtension(job.src)}_track${job.trackId}.wav');
    try {
      var err = await _run([ffmpegExe(), '-y', '-i', job.src, '-map', '0:${job.trackId}', '-vn', '-ar', '48000', '-c:a', 'pcm_s16le', wav], active);
      if (err != null) return 'extract: $err';
      // deepFilter 是最吃記憶體的階段 — 序列化執行避免 RAM 爆掉。
      await _acquireDfSlot();
      try {
        err = await _run([cfg.deepFilterPath, wav, '--output-dir', tmpDir.path, '--no-suffix', '--log-level', 'none'], active);
      } finally {
        _releaseDfSlot();
      }
      if (err != null) return 'deepfilter: $err';
      final args = [ffmpegExe(), '-y', '-i', wav, '-vn'];
      if (cfg.format == 'aac') {
        args.addAll(['-c:a', 'aac', '-b:a', cfg.bitrate, '-ar', '48000']);
        args.addAll(['-af', 'loudnorm=I=${cfg.lufsTarget}:LRA=1:TP=-1']);
      } else if (cfg.format == 'flac') {
        args.addAll(['-c:a', 'flac']);
      } else {
        args.addAll(['-c:a', 'pcm_s16le']);
      }
      args.add(out);
      err = await _run(args, active);
      if (err != null) return 'encode: $err';
      return null;
    } finally {
      try { File(wav).deleteSync(); } catch (_) {}
    }
  }
}