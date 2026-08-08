import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'package:path/path.dart' as p;

// Port of 大拇哥實驗室 AudioExtractor — DeepFilterNet 降噪 only。
// 三階段流水線: ffmpeg 抽出(平行) → 批次 deepFilter(一次載入模型) → ffmpeg 編碼(平行)。
// 用於切出音軌時記憶體/GPU 最佳化：deepFilter 只跑勾選的軌、只載入一次模型。

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
}

class AudioExtractorConfig {
  String sourceDir, outputDir, format, bitrate, deepFilterPath;
  int lufsTarget, silenceThreshold, workers;
  Map<int, String> trackNames;
  Set<int> denoiseTracks;
  // deepFilter 裝置: auto(自動偵測，GPU 忙就 CPU) | cuda | cpu
  String deepFilterDevice;
  AudioExtractorConfig({
    this.sourceDir = '', this.outputDir = '', this.format = 'aac', this.bitrate = '384k',
    this.lufsTarget = -14, this.silenceThreshold = 10000, this.workers = 2,
    this.deepFilterPath = 'deepFilter', Map<int, String>? trackNames,
    Set<int>? denoiseTracks, this.deepFilterDevice = 'cuda',
  })  : trackNames = trackNames ?? {1: 'Mix', 2: 'Game', 3: 'Mic', 5: 'DC'},
        denoiseTracks = denoiseTracks ?? {3};
  Map<String, dynamic> toJson() => {
    'sourceDir': sourceDir, 'outputDir': outputDir, 'format': format, 'bitrate': bitrate,
    'lufsTarget': lufsTarget, 'silenceThreshold': silenceThreshold, 'workers': workers,
    'deepFilterPath': deepFilterPath,
    'trackNames': trackNames.map((k, v) => MapEntry('$k', v)),
    'denoiseTracks': denoiseTracks.toList(),
    'deepFilterDevice': deepFilterDevice,
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
    deepFilterDevice: j['deepFilterDevice'] as String? ?? 'cuda',
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

  

  /// 決定 deepFilter 的 device。auto：遊戲/其他程式佔用 VRAM > 50% 就改用 CPU。
  /// 注意：deepFilter CLI 沒有 --device 參數，強制 CPU 要用 CUDA_VISIBLE_DEVICES=''。
  static Future<String> _resolveDevice(AudioExtractorConfig cfg) async {
    if (cfg.deepFilterDevice == 'cuda') return 'cuda';
    if (cfg.deepFilterDevice == 'cpu') return 'cpu';
    try {
      final r = await Process.run('nvidia-smi',
          ['--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'])
          .timeout(const Duration(seconds: 10));
      if (r.exitCode == 0) {
        final line = (r.stdout as String).trim();
        final parts = line.split(',');
        if (parts.length >= 2) {
          final used = double.tryParse(parts[0].trim());
          final total = double.tryParse(parts[1].trim());
          if (used != null && total != null && total > 0) {
            if (used / total > 0.5) return 'cpu'; // 遊戲等程式佔著顯卡 → 不搶
          }
        }
      }
    } catch (_) {}
    return 'cuda';
  }

  /// 一次呼叫 deepFilter 處理多個 wav（模型只載入一次）。
  static Future<String?> _batchDeep(List<String> wavs, AudioExtractorConfig cfg,
      List<Process> active, void Function(String) onLog,
      {bool forceCpu = false, bool Function()? cancelCheck}) async {
    final device = forceCpu ? 'cpu' : await _resolveDevice(cfg);
    Map<String, String> env;
    if (device == 'cpu') {
      // 空字串會被系統丟掉 → 用不存在的 GPU 編號讓 torch 完全看不到顯卡
      env = {'CUDA_VISIBLE_DEVICES': '999999'};
    } else {
      env = <String, String>{};
    }
    // 壓掉 library 內部 warnings（torchaudio/git 偵測 等），log 才不會被淹沒
    env['PYTHONWARNINGS'] = 'ignore';
    onLog('deeplog> device=${device == 'cpu' ? 'cpu' : 'cuda'} (forceCpu=$forceCpu)');
    return _run([
      cfg.deepFilterPath, ...wavs,
      '--output-dir', Directory.systemTemp.path, '--no-suffix', '--log-level', 'info',
    ], active, env: env, cancelCheck: cancelCheck, onLine: (s) {
      final t = s.trim();
      final meaningful = t.contains('Running on device') || t.contains('Loading model') ||
          t.contains('Enhanced noisy audio file') || t.contains('Out of memory') ||
          t.contains('CUDA out') || t.contains('Traceback') || t.contains('Error:') || t.contains('error:');
      if (meaningful) onLog('deeplog> $t');
    });
  }

  /// 三階段流水線: 抽出(並行4) → 批次 deepFilter(一次) → 編碼(並行4)。
  static Future<void> runParallel({
    required List<({String src, int trackId, int sampleRate, String trackName, bool denoise})> jobs,
    required AudioExtractorConfig cfg,
    required void Function(String) onLog,
    required void Function() onProgress,
    required bool Function() canceled,
  }) async {
    if (jobs.isEmpty) return;
    final active = <Process>[];
    const pool = 4;
    final ext = switch (cfg.format) { 'wav' => '.wav', 'flac' => '.flac', _ => '.m4a' };

    void killAll() {
      for (final pr in active) {
        try { pr.kill(); } catch (_) {}
      }
    }

    // Phase 1: 抽出。一般軌直接輸出；Mic(降噪)軌先抽成暫存 wav。
    final q1 = List.of(jobs);
    final deno = <({String wav, String out})>[];
    await Future.wait(List.generate(pool, (_) async {
      while (q1.isNotEmpty) {
        if (canceled()) { killAll(); return; }
        final job = q1.removeAt(0);
        final stem = p.basenameWithoutExtension(job.src);
        final name = job.trackName.isNotEmpty ? '${stem}_${job.trackName}' : '${stem}_track${job.trackId}';
        final out = p.join(cfg.outputDir, '$name$ext');
        if (File(out).existsSync()) {
          onLog('SKIP ${p.basename(out)} (exists)');
          onProgress();
          continue;
        }
        String? err;
        if (job.denoise) {
          final wav = p.join(Directory.systemTemp.path,
              'df_${p.basenameWithoutExtension(job.src)}_t${job.trackId}_${job.src.hashCode.abs().toRadixString(16)}.wav');
          err = await _run(
            [ffmpegExe(), '-y', '-i', job.src, '-map', '0:${job.trackId}', '-vn', '-ar', '48000', '-c:a', 'pcm_s16le', wav],
            active,
          );
          if (err == null) deno.add((wav: wav, out: out));
        } else {
          err = await _extractPlain(job, out, cfg, active);
        }
        if (err != null) {
          onLog('FAIL $name$ext: $err');
        } else if (!job.denoise) {
          onLog('OK  ${p.basename(out)}');
        }
        // 進度：非降噪軌在此計一次；降噪軌在 Phase 2 完成時計一次（避免重複灌滿）
        if (!job.denoise) onProgress();
      }
    }));

    // Phase 2: 批次 DeepFilter — 一次呼叫處理全部 wav，模型只載入一次。
    if (deno.isNotEmpty && !canceled()) {
      final wavs0 = deno.map((e) => e.wav).toList();
      final device = await _resolveDevice(cfg);
      // 批大小 4：deepFilterNet 會把整批 wav 載入 RAM（1.5h 錄影≈2GB 浮點），
      // 8 條一批峰值可到 ~11GB；4 條約 5~6GB 比較安全。
      const chunk = 4;
      for (int i = 0; i < wavs0.length; i += chunk) {
        if (canceled()) break;
        final part = wavs0.skip(i).take(chunk).toList();
        onLog('🎤 Mic deepFilter ${i + 1}~${i + part.length}/${wavs0.length}（${device == 'cpu' ? 'CPU' : 'GPU'}）');
        var e2 = await _batchDeep(part, cfg, active, onLog,
            forceCpu: device == 'cpu', cancelCheck: canceled);
        if (e2 != null) {
          onLog('deepFilter 批次失敗: $e2');
          // 逐檔重試（同 device）；仍失敗就移除該檔
          for (final w in part) {
            if (canceled()) break;
            final env = device == 'cpu' ? {'CUDA_VISIBLE_DEVICES': '999999'} : <String, String>{};
            final e3 = await _run([cfg.deepFilterPath, w,
                  '--output-dir', Directory.systemTemp.path, '--no-suffix', '--log-level', 'info'],
                active, env: env, onLine: (s) => onLog('deeplog> $s'), cancelCheck: canceled);
            if (e3 != null) {
              onLog('FAIL ${p.basename(w)}: deepfilter: $e3');
              deno.removeWhere((e) => e.wav == w);
            }
            onProgress();
          }
        } else {
          // 整批成功：每條計一次進度
          for (int k = 0; k < part.length; k++) {
            if (canceled()) break;
            onProgress();
          }
        }
      }
    }

    // Phase 3: Deep wav → 目標格式（平行 ffmpeg），完成刪暫存。
    if (deno.isNotEmpty && !canceled()) {
      await Future.wait(List.generate(pool, (_) async {
        while (deno.isNotEmpty) {
          if (canceled()) { killAll(); return; }
          final t = deno.removeAt(0);
          final err = await _encodeWav(t.wav, t.out, cfg, active);
          try { File(t.wav).deleteSync(); } catch (_) {}
          onLog(err == null ? 'OK  ${p.basename(t.out)}' : 'FAIL ${p.basename(t.out)}: $err');
        }
      }));
    }
  }

  /// 批次 deepFilter 呼叫（可指定 device / log level；log 行即時轉送給 UI）。
  static Future<String?> _run(List<String> args, List<Process> active,
      {String? workDir, Map<String, String>? env, void Function(String line)? onLine,
      bool Function()? cancelCheck}) async {
    final fullEnv = env != null ? {...Platform.environment, ...env} : null;
    Process? proc;
    final sb = StringBuffer();
    for (int attempt = 0; attempt < 3; attempt++) {
      try {
        proc = await Process.start(args[0], args.sublist(1),
            workingDirectory: workDir, environment: fullEnv);
        break;
      } catch (e) {
        if (attempt == 2) return 'launch failed: $e';
        await Future<void>.delayed(const Duration(milliseconds: 800));
      }
    }
    if (proc == null) return 'launch failed';
    active.add(proc);
    // 非常重要：deepFilter 的進度行(Enhanced/%) 走 stdout，要排空否則 pipe
    // 塞滿後 process 卡死（CPU 0 但無限等待）。
    proc.stdout.drain<void>();
    proc.stderr.transform(const Utf8Decoder(allowMalformed: true)).listen((chunk) {
      sb.write(chunk);
      if (onLine != null) {
        final lines = chunk.split('\n');
        for (final l in lines) {
          if (l.trim().isNotEmpty) onLine(l.trim());
        }
      }
    });
    try {
      // 取消時即時殺掉子程序（先前 cancel 只能等階段結束才生效）
      int code = -1;
      for (int waitMs = 0; ; waitMs += 250) {
        if (cancelCheck != null && cancelCheck()) {
          try { proc.kill(); } catch (_) {}
          try { active.remove(proc); } catch (_) {}
          return 'cancelled';
        }
        if (waitMs >= 60000) break; // 檢查頻率下限：至少每 1 分鐘看一眼
        code = await proc.exitCode.timeout(const Duration(milliseconds: 250), onTimeout: () => -1);
        if (code != -1) break;
      }
      code = await proc.exitCode.timeout(const Duration(hours: 1));
      if (code == 0) return null;
      // 錯誤訊息的真正內容在 stderr 尾部
      var e = sb.toString().trim().replaceAll('\n', ' | ');
      if (e.length > 300) e = e.substring(e.length - 300);
      return e.isEmpty ? 'exit $code' : '(exit $code) $e';
    } on TimeoutException {
      try { proc.kill(); } catch (_) {}
      return 'timeout (killed)';
    } finally {
      active.remove(proc);
    }
  }

  /// 純 ffmpeg 抽出：直接轉目標格式 + loudnorm（非降噪軌，記憶體低）。
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

  /// deepFilter 後的 wav → 目標格式（AAC + loudnorm / FLAC / WAV）。
  static Future<String?> _encodeWav(String wav, String out, AudioExtractorConfig cfg,
      List<Process> active) async {
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
    return _run(args, active);
  }
}