import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'config_service.dart';

/// Local streaming server: resolves a song query via yt-dlp (through the
/// Python bridge) and serves the audio bytes over http://127.0.0.1:PORT/stream.
/// Optional caching to cache/stream/ (Spotube-style cacheMusic).
class StreamServer {
  static StreamServer? _instance;
  static StreamServer get instance => _instance ??= StreamServer._();
  StreamServer._();

  HttpServer? _server;
  int _port = 0;
  bool _started = false;

  /// LAN 成員用來連串流伺服器的基底網址（由外部（JamService）注入）。
  String publicBase = 'http://127.0.0.1:0';

  int get port => _port;

  /// query -> resolved URL cache (in-memory, per session)
  final Map<String, String> _resolved = {};

  /// Currently running stream-download process (kill on new request).
  Process? _activeProc;

  /// query -> cached file path (persisted across restarts via index)
  final Map<String, String> _cacheIndex = {};

  bool get isRunning => _started;

  String get baseUrl => 'http://127.0.0.1:$_port';

  static String get _bridgePath =>
      '${ConfigService.instance.config.toolsPath}\\flutter_download_bridge.py';

  static String get _cacheDir =>
      ConfigService.instance.config.streamCachePath;

  static String get _indexPath => '$_cacheDir\\stream_index.json';

  Future<void> start() async {
    if (_started) return;
    _loadIndex();
    // Clean orphaned temp files from previous sessions.
    try {
      final dir = Directory(_cacheDir);
      if (dir.existsSync()) {
        for (final f in dir.listSync().whereType<File>()) {
          if (f.uri.pathSegments.last.startsWith('stream_')) {
            f.deleteSync();
          }
        }
      }
    } catch (_) {}
    _server = await HttpServer.bind(InternetAddress.anyIPv4, 0);
    _port = _server!.port;
    _server!.listen(_handle);
    _started = true;
  }

  Future<void> stop() async {
    _started = false;
    await _server?.close(force: true);
    _server = null;
  }

  void _loadIndex() {
    try {
      final f = File(_indexPath);
      if (!f.existsSync()) return;
      final data = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
      for (final e in data.entries) {
        final p = e.value as String;
        if (File(p).existsSync()) _cacheIndex[e.key] = p;
      }
    } catch (_) {}
  }

  void _saveIndex() {
    try {
      final f = File(_indexPath);
      f.createSync(recursive: true);
      f.writeAsStringSync(jsonEncode(_cacheIndex));
    } catch (_) {}
  }

  /// Look up a cached stream for [query]; null if not cached.
  String? cachedPathFor(String query) => _cacheIndex[query];

  /// Kill any active streaming process.
  void stopActive() {
    _activeProc?.kill();
    _activeProc = null;
  }

  /// Search cache\stream\ for a file matching the query name.
  String? findCached(String query) {
    final dir = Directory(_cacheDir);
    if (!dir.existsSync()) return null;
    final lower = query.toLowerCase();
    final prefix = lower.substring(0, lower.length.clamp(0, 20));
    for (final f in dir.listSync().whereType<File>()) {
      if (f.path.endsWith('.mp3') && f.lengthSync() > 65536) {
        final name = f.path.split(Platform.pathSeparator).last.toLowerCase();
        if (name.contains(prefix)) {
          return f.path;
        }
      }
    }
    return null;
  }

  Future<void> _handle(HttpRequest request) async {
    final path = request.uri.pathSegments;
    if (path.isNotEmpty && path[0] == 'stream' && path.length >= 2) {
      final query = path[1];
      try {
        // 1. Cached file first — serve instantly.
        final cached = _cacheIndex[query];
        if (cached != null && File(cached).existsSync()) {
          await _serveFile(request, File(cached));
          return;
        }
        // 2. No cache — resolve + transcode on-the-fly (true streaming).
        await _serveTranscoded(request, '', query);
      } catch (e) {
        try {
          request.response.statusCode = HttpStatus.internalServerError;
          await request.response.close();
        } catch (_) {}
      }
      return;
    }
    request.response.statusCode = HttpStatus.notFound;
    await request.response.close();
  }

  Future<String> _resolve(String query) async {
    final cached = _resolved[query];
    if (cached != null) return cached;
    try {
      final proc = await Process.start(
        'python',
        [_bridgePath, 'stream-resolve', query],
        runInShell: true,
        workingDirectory: ConfigService.instance.config.basePath,
        environment: {'PYTHONIOENCODING': 'utf-8'},
      );
      final out = await proc.stdout.transform(utf8.decoder).join();
      final code = await proc.exitCode;
      if (code != 0) {
        print('[StreamServer] stream-resolve failed (exit $code) for: $query');
        return '';
      }
      for (final line in out.split('\n')) {
        if (line.trim().isNotEmpty) {
          try {
            final data = jsonDecode(line.trim()) as Map<String, dynamic>;
            if (data['type'] == 'error') {
              print('[StreamServer] stream-resolve error: ${data['message']}');
              return '';
            }
            if (data['type'] == 'complete' && data['url'] != null) {
              _resolved[query] = data['url'] as String;
              return data['url'] as String;
            }
          } catch (_) {}
        }
      }
      print('[StreamServer] stream-resolve: no valid URL for: $query');
    } catch (e) {
      print('[StreamServer] stream-resolve exception: $e');
    }
    return '';
  }

  /// Public resolve used by SearchPage to prepare a stream URL.
  Future<String> resolveForTest(String query) => _resolve(query);

  /// Resolve a query → yt-dlp download+transcode to mp3 → return local path.
  Future<String> resolveToFile(String query, {String? isrc}) async {
    final cacheDir = Directory(_cacheDir);
    await cacheDir.create(recursive: true);

    final safeName = query.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_').replaceAll(RegExp(r'\s+'), ' ').trim();
    final prefix = safeName.substring(0, safeName.length.clamp(0, 20)).toLowerCase();
    for (final f in cacheDir.listSync().whereType<File>()) {
      final name = f.path.split(Platform.pathSeparator).last.toLowerCase();
      if (name.contains(prefix) && f.path.endsWith('.mp3') && f.lengthSync() > 65536) {
        return f.path;
      }
    }

    final outBase = '${cacheDir.path}\\dl_${safeName.hashCode.toRadixString(16)}';
    // Kill any previous streaming process to avoid resource leaks.
    _activeProc?.kill();
    _activeProc = null;
    try {
      final proc = await Process.start(
        'python',
        [_bridgePath, 'stream-download', query, outBase] + (isrc != null ? [isrc] : []),
        runInShell: true,
        workingDirectory: ConfigService.instance.config.basePath,
        environment: {'PYTHONIOENCODING': 'utf-8'},
      );
      _activeProc = proc;
      // Timeout: kill if stuck for 90 seconds (yt-dlp can take 45-60s).
      final outFuture = proc.stdout.transform(utf8.decoder).join();
      final exited = proc.exitCode.timeout(
        const Duration(seconds: 90),
        onTimeout: () { proc.kill(); return -1; },
      );
      final out = await outFuture;
      final code = await exited;
      _activeProc = null;
      if (code != 0 && code != -1) {
        print('[StreamServer] stream-download failed (exit $code) for: $query');
        return '';
      }
      for (final line in out.split('\n')) {
        if (line.trim().isNotEmpty) {
          try {
            final data = jsonDecode(line.trim()) as Map<String, dynamic>;
            if (data['type'] == 'error') {
              print('[StreamServer] stream-download error: ${data['message']}');
              continue;
            }
            if (data['type'] == 'complete' && data['path'] != null) {
              final srcPath = data['path'] as String;
              final finalPath = '${cacheDir.path}\\$safeName.mp3';
              if (srcPath != finalPath) {
                await File(srcPath).rename(finalPath);
              }
              _cacheIndex[query] = finalPath;
              _saveIndex();
              return finalPath;
            }
          } catch (_) {}
        }
      }
      return '';
    } catch (_) {
      _activeProc?.kill();
      _activeProc = null;
      return '';
    }
  }

  /// True streaming: resolve URL → ffmpeg reads URL directly → pipe mp3 to
  /// HTTP response + write to cache simultaneously. Starts playing ASAP.
  Future<void> _serveTranscoded(
      HttpRequest request, String url, String query) async {
    // Resolve URL if not provided.
    if (url.isEmpty) {
      url = await _resolve(query);
      if (url.isEmpty) {
        request.response.statusCode = HttpStatus.notFound;
        await request.response.close();
        return;
      }
    }

    final ffmpeg = ConfigService.instance.config.ffmpegPath.isNotEmpty
        ? ConfigService.instance.config.ffmpegPath
        : 'ffmpeg';

    // ffmpeg reads remote URL directly — starts transcoding immediately.
    final args = [
      '-user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
      '-i', url,
      '-vn', '-c:a', 'libmp3lame', '-q:a', '0', '-f', 'mp3', 'pipe:1',
    ];
    final ff = await Process.start(ffmpeg, args, runInShell: true);

    // Cache: tee into file while streaming.
    final cacheEnabled = ConfigService.instance.config.streamCacheEnabled;
    IOSink? cacheSink;
    File? cacheFile;
    if (cacheEnabled) {
      try {
        final dir = Directory(_cacheDir);
        await dir.create(recursive: true);
        final safeName = query.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_').replaceAll(RegExp(r'\s+'), ' ').trim();
        cacheFile = File('$_cacheDir\\$safeName.mp3');
        cacheSink = cacheFile.openWrite();
      } catch (_) {}
    }

    request.response.headers.contentType = ContentType('audio', 'mpeg');
    request.response.headers.set('Cache-Control', 'no-store');

    // Pipe ffmpeg stdout → HTTP response + optional cache.
    await request.response.addStream(ff.stdout.transform(
        StreamTransformer.fromHandlers(
            handleData: (data, sink) {
              cacheSink?.add(data);
              sink.add(data);
            },
            handleError: (e, st, sink) {},
            handleDone: (sink) => sink.close())));
    await request.response.close();
    await cacheSink?.close();

    // Update cache index.
    if (cacheEnabled && cacheFile != null && cacheFile.existsSync() && cacheFile.lengthSync() > 65536) {
      _cacheIndex[query] = cacheFile.path;
      _saveIndex();
      _enforceCacheLimit();
    }
  }

  Future<void> _serveFile(HttpRequest request, File file) async {
    request.response.headers.contentType = ContentType('audio', 'mpeg');
    await request.response.addStream(file.openRead());
    await request.response.close();
  }

  /// Cache size cap: 2GB default; evicts oldest entries.
  Future<void> _enforceCacheLimit() async {
    final maxBytes = ConfigService.instance.config.streamCacheMaxMb * 1024 * 1024;
    final files = <File>[];
    var total = 0;
    for (final e in _cacheIndex.entries) {
      final f = File(e.value);
      if (!f.existsSync()) continue;
      total += await f.length();
      files.add(f);
    }
    if (total <= maxBytes) return;
    files.sort((a, b) => a.lastModifiedSync().compareTo(b.lastModifiedSync()));
    for (final f in files) {
      if (total <= maxBytes) break;
      final len = await f.length();
      try {
        await f.delete();
      } catch (_) {}
      total -= len;
      _cacheIndex.removeWhere((k, v) => v == f.path);
    }
    _saveIndex();
  }
}