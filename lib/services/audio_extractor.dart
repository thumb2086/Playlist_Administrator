import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'package:path/path.dart' as p;

// Port of 大拇哥實驗室 AudioExtractor — DeepFilterNet 降噪 only。
// 三階段流水線: ffmpeg 抽出(平行) → 批次 deepFilter(一次載入模型) → ffmpeg 編碼(平行)。
// 取消支援全流程（含分割/拼接/編碼），段名含來源 hash 防碰撞。

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

  /// 用 taskkill 連同子進程樹一起殺（deepFilter 的 python spawn 子進程會孤兒）。
  static Future<void> _killTree(int pid) async {
    try {
      final p = Process.start('taskkill', ['/PID', '$pid', '/T', '/F'],
          runInShell: false).timeout(const Duration(seconds: 10));
      final proc = await p;
      await proc.exitCode.timeout(const Duration(seconds: 10), onTimeout: () => -1);
    } catch (_) {}
    try { Process.killPid(pid); } catch (_) {}
  }

  /// 決定 deepFilter device。auto 只在能讀到 nvidia-smi 且 VRAM<50% 時用 GPU；
  /// 偵測失敗一律回 CPU（避免誤用 GPU 直接 OOM）。
  static Future<String> _resolveDevice(AudioExtractorConfig cfg) async {
    if (cfg.deepFilterDevice == 'cuda') return 'cuda';
    if (cfg.deepFilterDevice == 'cpu') return 'cpu';
    try {
      final r = await Process.run('nvidia-smi',
          ['--query-gpu=memory.used,memory.total', '--format=csv,noheader,nounits'])
          .timeout(const Duration(seconds: 10));
      if (r.exitCode != 0) return 'cpu';
      final line = (r.stdout as String).trim();
      final parts = line.split(',');
      if (parts.length >= 2) {
        final used = double.tryParse(parts[0].trim());
        final total = double.tryParse(parts[1].trim());
        if (used != null && total != null && total > 0) {
          return used / total > 0.5 ? 'cpu' : 'cuda';
        }
      }
      return 'cpu';
    } catch (_) {
      return 'cpu';
    }
  }

  /// PyTorch CUDA OOM / cuDNN 錯誤偵測（傳完整 stderr，避免截斷漏判）
  static bool _isGpuOom(String err) {
    final e = err.toLowerCase();
    return e.contains('out of memory') ||
        e.contains('cuda out') ||
        e.contains('reserved by pytorch') ||
        e.contains('cudnn_status') ||
        e.contains('cublas');
  }

/// 定位 deepfilter_daemon.py：橋接暫存目錄（release）→ cwd/tools（dev）
  static String? _daemonScript() {
    final cands = <String>[
      // BridgeService 解壓到 %TEMP%\playlist_admin_tools
      p.join(Directory.systemTemp.path, 'playlist_admin_tools', 'deepfilter_daemon.py'),
      // dev / CLI：專案內
      p.join(Directory.current.path, 'tools', 'deepfilter_daemon.py'),
      p.join(Directory.current.path, 'deepfilter_daemon.py'),
      // 用戶指定專案根
      if (Platform.environment['PA_ROOT'] != null)
        p.join(Platform.environment['PA_ROOT']!, 'tools', 'deepfilter_daemon.py'),
    ];
    for (final c in cands) {
      if (File(c).existsSync()) return c;
    }
    return null;
  }

  /// 超過 15 分鐘的 wav 切成 10 分鐘段。長檔直送會讓 DeepFilterNet 的特徵
  /// buffer 爆 VRAM（單一分配可達 8GB）— 切段後每批峰值小很多。
  static Future<List<String>> _maybeSplit(String wav, List<Process> active,
      bool Function()? cancelCheck) async {
    try {
      final r = await Process.run(ffprobeExe(), [
        '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', wav,
      ]).timeout(const Duration(seconds: 20));
      final dur = double.tryParse((r.stdout as String).trim()) ?? 0;
      if (dur <= 900) return [wav];
      final base = p.basenameWithoutExtension(wav);
      final segCount = (dur / 600).ceil();
      final pat = p.join(Directory.systemTemp.path, '${base}_seg_%03d.wav');
      // 先清掉先前殘留的同名段
      for (int i = 0; i < 100; i++) {
        final f = File(p.join(Directory.systemTemp.path, '${base}_seg_${i.toString().padLeft(3, '0')}.wav'));
        try { if (f.existsSync()) f.deleteSync(); } catch (_) {}
      }
      final e = await _run([
        ffmpegExe(), '-y', '-i', wav, '-f', 'segment', '-segment_time', '600',
        '-c', 'copy', pat,
      ], active, cancelCheck: cancelCheck);
      if (e != null) {
        for (int i = 0; i < segCount; i++) {
          try {
            File(p.join(Directory.systemTemp.path, '${base}_seg_${i.toString().padLeft(3, '0')}.wav')).deleteSync();
          } catch (_) {}
        }
        return [wav];
      }
      final segs = <String>[];
      for (int i = 0; i < segCount; i++) {
        final f = p.join(Directory.systemTemp.path, '${base}_seg_${i.toString().padLeft(3, '0')}.wav');
        if (File(f).existsSync()) segs.add(f);
      }
      return segs.isEmpty ? [wav] : segs;
    } catch (_) {
      return [wav];
    }
  }

  /// deep 處理後的段拼回原 wav（ffmpeg concat，成功/失敗都清段檔）。
  static Future<String?> _concatSegs(List<String> segs, String destWav,
      List<Process> active, bool Function()? cancelCheck) async {
    try {
      final listPath = p.join(Directory.systemTemp.path, 'concat_${DateTime.now().microsecondsSinceEpoch}.txt');
      // concat demuxer 用單引號包路徑；路徑內含單引號先剔除（Windows 檔名允許但罕見）
      File(listPath).writeAsStringSync(
          segs.map((s) => "file '${s.replaceAll("'", '')}'").join('\n'));
      final e = await _run([ffmpegExe(), '-y', '-f', 'concat', '-safe', '0', '-i', listPath, '-c', 'copy', destWav],
          active, cancelCheck: cancelCheck);
      File(listPath).deleteSync();
      for (final s in segs) {
        try { File(s).deleteSync(); } catch (_) {}
      }
      return e;
    } catch (e) {
      return 'concat: $e';
    }
  }

  /// 一次呼叫 deepFilter 處理多個 wav（模型只載入一次）。
  static Future<String?> _batchDeep(List<String> wavs, AudioExtractorConfig cfg,
      List<Process> active, void Function(String) onLog,
      {bool forceCpu = false, bool Function()? cancelCheck}) async {
    final device = forceCpu ? 'cpu' : await _resolveDevice(cfg);
    final env = <String, String>{'PYTHONWARNINGS': 'ignore'};
    if (device == 'cpu') {
      // 空字串會被系統丟掉 → 用不存在的 GPU 編號讓 torch 完全看不到顯卡
      env['CUDA_VISIBLE_DEVICES'] = '999999';
    }
    onLog('deeplog> device=${device == 'cpu' ? 'cpu' : 'cuda'} (forceCpu=$forceCpu)');
    return _run([
      cfg.deepFilterPath, ...wavs,
      '--output-dir', Directory.systemTemp.path, '--no-suffix', '--log-level', 'info',
    ], active, env: env, cancelCheck: cancelCheck, onLine: (s) {
      final t = s.trim();
      // 只轉播階段/裝置/關鍵錯誤行；堆疊明細與 warnings 不進 log
      if (t.contains('Running on device') || t.contains('Loading model') ||
          t.contains('Enhanced noisy audio file') ||
          t.contains('Traceback') || t.contains('RuntimeError') || t.contains('Error:') ||
          t.contains('CUDA out') || t.contains('Out of memory')) {
        onLog('deeplog> $t');
      }
    });
  }

  /// 三階段流水線: 抽出(並行4) → 批次 deepFilter(分段/一次載入) → 編碼(並行4)。
  /// 取消全流程生效；progress 每條輸出恰計一次。
  static Future<void> runParallel({
    required List<({String src, int trackId, int sampleRate, String trackName, bool denoise})> jobs,
    required AudioExtractorConfig cfg,
    required void Function(String) onLog,
    required void Function() onProgress,
    required bool Function() canceled,
  }) async {
    if (jobs.isEmpty) return;
    final active = <Process>[];
    const pool = 2;
    final fmt = switch (cfg.format) { 'm4a' => 'aac', 'wav' => 'wav', 'flac' => 'flac', _ => 'aac' };
    final ext = switch (fmt) { 'wav' => '.wav', 'flac' => '.flac', _ => '.m4a' };

    // 開跑前清掉陳腐的暫存 wav（>1 小時，可能來自先前被殺掉的執行）
    try {
      final now = DateTime.now();
      for (final f in Directory.systemTemp.listSync().whereType<File>()) {
        if (f.path.contains('df_') && f.path.endsWith('.wav') &&
            now.difference(f.lastModifiedSync()).inMinutes > 60) {
          try { f.deleteSync(); } catch (_) {}
        }
      }
    } catch (_) {}

    void killAll() {
      for (final pr in active) {
        try { _killTree(pr.pid); } catch (_) {}
      }
    }

    // Phase 1: 抽出。一般軌直接輸出；降噪軌抽成暫存 wav。
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
          if (!job.denoise) onProgress();
          continue;
        }
        String? err;
        if (job.denoise) {
          final wav = p.join(Directory.systemTemp.path,
              'df_${p.basenameWithoutExtension(job.src)}_t${job.trackId}_${(job.src.hashCode & 0x7fffffff).toRadixString(16)}.wav');
          err = await _run(
            [ffmpegExe(), '-y', '-i', job.src, '-map', '0:${job.trackId}', '-vn', '-ar', '48000', '-c:a', 'pcm_s16le', wav],
            active, cancelCheck: canceled,
          );
          if (err == null) deno.add((wav: wav, out: out));
        } else {
          err = await _extractPlain(job, out, cfg, active, canceled);
        }
        if (err != null) {
          onLog('FAIL $name$ext: $err');
          if (job.denoise) onProgress(); // 抽出失敗也算該條完成，避免進度卡死
        } else if (!job.denoise) {
          onLog('OK  ${p.basename(out)}');
          onProgress();
        }
      }
    }));

    // Phase 2: 批次 DeepFilter（長檔先切段，逐原檔處理）
    if (deno.isNotEmpty && !canceled()) {
      final wavs0 = List.of(deno.map((e) => e.wav));
      var useCuda = await _resolveDevice(cfg) == 'cuda';
      // 常駐 daemon：整個 run 只載入一次模型（根治 VRAM 逐批累積）
      Process? daemon;
      final pending = <int, Completer<Map<String, dynamic>>>{};
      bool daemonAlive = false;
      bool daemonCpu = !useCuda;
      int nextId = 1;

      Future<Map<String, dynamic>> daemonAsk(String wav) async {
        final id = nextId++;
        final c = Completer<Map<String, dynamic>>();
        pending[id] = c;
        final s = daemon?.stdin;
        if (s == null || !daemonAlive) {
          if (!c.isCompleted) c.complete({'id': id, 'ok': false, 'err': 'daemon dead'});
        } else {
          try {
            s.writeln(jsonEncode({'cmd': 'enhance', 'id': id, 'path': wav}));
            await s.flush();
          } catch (_) { /* exit-handler 會完成本請求 */ }
        }
        return c.future.timeout(const Duration(minutes: 10),
            onTimeout: () => {'id': id, 'ok': false, 'err': 'daemon timeout'});
      }

      Future<bool> ensureDaemon() async {
        if (daemonAlive) return true;
        // 清理殘留進程（ready 逾時/已死未報），避免雙啟動孤兒吃爆 VRAM
        if (daemon != null) {
          try { await _killTree(daemon!.pid); } catch (_) {}
          daemon = null;
        }
        final script = _daemonScript();
        if (script == null) {
          onLog('  ⚠️ 找不到 deepfilter_daemon.py');
          return false;
        }
        final env = <String, String>{
          ...Platform.environment,
          'PYTHONWARNINGS': 'ignore',
          if (daemonCpu) 'CUDA_VISIBLE_DEVICES': '999999',
        };
        try {
          daemon = await Process.start('python', [script], runInShell: false, environment: env);
          final dPid = daemon!.pid;
          Process.start('powershell', [
            '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
            '-Command', "(Get-Process -Id $dPid).PriorityClass='BelowNormal'",
          ], runInShell: false).ignore();
        } catch (e) {
          onLog('  ⚠️ daemon 啟動失敗: $e');
          return false;
        }
        pending.clear();
        final ready = Completer<bool>();
        daemon!.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
          final t = line.trim();
          if (t.isEmpty) return;
          try {
            final j = jsonDecode(t) as Map<String, dynamic>;
            if (j.containsKey('ready')) {
              onLog('daemon> ready ${j['device']}');
              if (!ready.isCompleted) ready.complete(true);
            } else {
              final id = (j['id'] as num?)?.toInt();
              if (id != null && pending.containsKey(id)) {
                pending.remove(id)!.complete(j);
              }
            }
          } catch (_) {}
        });
        daemon!.stderr.drain<void>();
        daemon!.exitCode.then((_) {
          daemonAlive = false;
          for (final c in pending.values) {
            if (!c.isCompleted) c.complete({'id': -1, 'ok': false, 'err': 'daemon exited'});
          }
          pending.clear();
        });
        daemonAlive = true;
        try {
          await ready.future.timeout(const Duration(seconds: 40));
          return true;
        } catch (_) {
          daemonAlive = false;
          if (daemon != null) {
            try { await _killTree(daemon!.pid); } catch (_) {}
            daemon = null;
          }
          return false;
        }
      }

      int done = 0;
      for (final origWav in wavs0) {
        if (canceled()) break;
        done++;
        final segs = await _maybeSplit(origWav, active, canceled);
        final segLabel = segs.length > 1 ? '（${segs.length} 段）' : '';
        onLog('🎤 Mic deepFilter $done/${wavs0.length}$segLabel（${useCuda ? 'GPU' : 'CPU'}）');
        var allOk = !canceled();
        for (final w in segs) {
          if (canceled()) break;
          if (!await ensureDaemon()) {
            allOk = false;
            break;
          }
          // 取消時 1 秒輪詢，避免卡在 10 分鐘 timeout
          final f = daemonAsk(w).then<Map<String, dynamic>?>((v) => v);
          Map<String, dynamic> r = const {};
          bool got = false;
          while (!canceled()) {
            final x = await f.timeout(const Duration(seconds: 1), onTimeout: () => null);
            if (x != null) { r = x; got = true; break; }
          }
          if (!got) break; // canceled：外層收尾會殺 daemon
          if (r['ok'] == true) continue;
          // daemon 異常死亡（GPU OOM 等）→ 改用 CPU 重啟再試一次
          final died = !daemonAlive;
          if (died && daemon != null) {
            onLog('  🔄 daemon 異常（可能 GPU OOM），改 CPU 重啟');
            daemonCpu = true;
            useCuda = false;
            if (await ensureDaemon()) {
              final r2 = await daemonAsk(w);
              if (r2['ok'] == true) continue;
            }
          }
          onLog('  ⚠️ 降噪失敗（跳過此檔）: ${(r['err'] as String?) ?? 'unknown'}');
          allOk = false;
        }
        if (allOk && segs.length > 1) {
          final ce = await _concatSegs(segs, origWav, active, canceled);
          if (ce != null) {
            onLog('  ⚠️ 拼接失敗: $ce');
            allOk = false;
          }
        }
        if (!allOk) {
          try { File(origWav).deleteSync(); } catch (_) {}
          deno.removeWhere((e) => e.wav == origWav);
        }
        onProgress();
      }
      // 收尾：關閉 daemon
      if (daemonAlive && daemon != null) {
        try {
          daemon?.stdin.writeln(jsonEncode({'cmd': 'quit'}));
          await daemon!.exitCode.timeout(const Duration(seconds: 5), onTimeout: () => -1);
        } catch (_) {}
        try { await _killTree(daemon!.pid); } catch (_) {}
      }
    }

    // Phase 3: Deep wav → 目標格式（平行 ffmpeg），完成刪暫存。
    if (deno.isNotEmpty && !canceled()) {
      await Future.wait(List.generate(pool, (_) async {
        while (deno.isNotEmpty) {
          if (canceled()) { killAll(); return; }
          final t = deno.removeAt(0);
          final err = await _encodeWav(t.wav, t.out, cfg, active, canceled);
          // 等 process 真正結束再刪檔（避免 ffmpeg 還在寫）
          try { File(t.wav).deleteSync(); } catch (_) {}
          if (err != null) {
            onLog('FAIL ${p.basename(t.out)}: $err');
          } else {
            onLog('OK  ${p.basename(t.out)}');
          }
        }
      }));
    }

    // 取消/異常時，把尚未編碼的降噪 wav 清掉，避免殘骸
    if (canceled()) {
      for (final e in deno) {
        try { File(e.wav).deleteSync(); } catch (_) {}
      }
      try {
        for (final f in Directory.systemTemp.listSync().whereType<File>()) {
          if (f.path.contains('_seg_') && f.path.endsWith('.wav')) {
            try { f.deleteSync(); } catch (_) {}
          }
        }
      } catch (_) {}
    }
  }

  static Future<String?> _run(List<String> args, List<Process> active,
      {String? workDir, Map<String, String>? env, void Function(String line)? onLine,
      bool Function()? cancelCheck}) async {
    final fullEnv = env != null ? {...Platform.environment, ...env} : null;
    Process? proc;
    final sb = StringBuffer();
    var sbLen = 0;
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
    // 子進程設為 BelowNormal：讓「播放影片/遊戲」等前景程式優先，避免卡頓
    try {
      Process.start('powershell', [
        '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
        '-Command', "(Get-Process -Id ${proc.pid}).PriorityClass='BelowNormal'"
      ], runInShell: false).ignore();
    } catch (_) {}
    // 排空 stdout（deepFilter 進度行走 stdout，不排會 pipe 塞滿死鎖）
    proc.stdout.drain<void>();
    proc.stderr.transform(const Utf8Decoder(allowMalformed: true)).listen((chunk) {
      if (sbLen < 8000) {
        sb.write(chunk);
        sbLen += chunk.length;
        if (sbLen > 8000) sb.write('\n...[截斷]...');
      }
      if (onLine != null) {
        for (final l in chunk.split('\n')) {
          if (l.trim().isNotEmpty) onLine(l.trim());
        }
      }
    });
    try {
      // 持續檢查取消（250ms），取消立即整棵殺掉
      int code;
      while (true) {
        if (cancelCheck != null && cancelCheck()) {
          await _killTree(proc.pid);
          try { active.remove(proc); } catch (_) {}
          return 'cancelled';
        }
        code = await proc.exitCode.timeout(const Duration(milliseconds: 250), onTimeout: () => -1);
        if (code != -1) break;
      }
      if (code == 0) return null;
      var e = sb.toString().trim().replaceAll('\n', ' | ');
      if (e.length > 600) e = e.substring(e.length - 600);
      return e.isEmpty ? 'exit $code' : '(exit $code) $e';
    } on TimeoutException {
      await _killTree(proc.pid);
      return 'timeout (killed)';
    } finally {
      try { active.remove(proc); } catch (_) {}
    }
  }

  /// 純 ffmpeg 抽出：直接轉目標格式 + loudnorm（非降噪軌，記憶體低）。
  static Future<String?> _extractPlain(
      ({String src, int trackId, int sampleRate, String trackName, bool denoise}) job,
      String out, AudioExtractorConfig cfg, List<Process> active,
      bool Function()? cancelCheck) async {
    final fmt = cfg.format == 'm4a' ? 'aac' : cfg.format;
    final args = [ffmpegExe(), '-y', '-i', job.src, '-map', '0:${job.trackId}', '-vn'];
    if (fmt == 'aac') {
      args.addAll(['-c:a', 'aac', '-b:a', cfg.bitrate]);
      if (job.sampleRate > 0) args.addAll(['-ar', '${job.sampleRate}']);
      args.addAll(['-af', 'loudnorm=I=${cfg.lufsTarget}:LRA=1:TP=-1']);
    } else if (fmt == 'flac') {
      args.addAll(['-c:a', 'flac']);
    } else {
      args.addAll(['-c:a', 'pcm_s16le']);
    }
    args.add(out);
    return _run(args, active, cancelCheck: cancelCheck);
  }

  /// deepFilter 後的 wav → 目標格式（AAC + loudnorm / FLAC / WAV）。
  static Future<String?> _encodeWav(String wav, String out, AudioExtractorConfig cfg,
      List<Process> active, bool Function()? cancelCheck) async {
    final fmt = cfg.format == 'm4a' ? 'aac' : cfg.format;
    final args = [ffmpegExe(), '-y', '-i', wav, '-vn'];
    if (fmt == 'aac') {
      args.addAll(['-c:a', 'aac', '-b:a', cfg.bitrate, '-ar', '48000']);
      args.addAll(['-af', 'loudnorm=I=${cfg.lufsTarget}:LRA=1:TP=-1']);
    } else if (fmt == 'flac') {
      args.addAll(['-c:a', 'flac']);
    } else {
      args.addAll(['-c:a', 'pcm_s16le']);
    }
    args.add(out);
    return _run(args, active, cancelCheck: cancelCheck);
  }
}
