import 'dart:convert';
import 'dart:io';
import 'config_service.dart';

class SubtitleService {
  static final SubtitleService _instance = SubtitleService._();
  static SubtitleService get instance => _instance;
  SubtitleService._();

  String? _ytdlpPath;

  Future<String> _resolveYtdlp() async {
    if (_ytdlpPath != null) return _ytdlpPath!;
    // Search PATH
    final pathEnv = Platform.environment['PATH'] ?? '';
    for (final dir in pathEnv.split(';')) {
      if (dir.trim().isEmpty) continue;
      try {
        for (final name in ['yt-dlp.exe', 'yt-dlp']) {
          final candidate = '${dir.trim()}\\$name';
          if (File(candidate).existsSync()) {
            _ytdlpPath = candidate;
            return candidate;
          }
        }
      } catch (_) {}
    }
    _ytdlpPath = 'yt-dlp';
    return 'yt-dlp';
  }

  /// Resolve a playlist entry path (same logic as LufsService).
  String? _resolvePlaylistPath(String entry, String playlistsPath, String basePath, String libraryPath) {
    if (entry.isEmpty) return null;
    if (!entry.contains('.') && !entry.contains('\\') && !entry.contains('/')) return null;

    final resolved = '${playlistsPath}\\$entry';
    if (File(resolved).existsSync()) return resolved;
    if (File(entry).existsSync()) return entry;

    final fname = File(entry).uri.pathSegments.last;
    for (final base in [basePath, libraryPath, playlistsPath]) {
      final candidate = '$base\\$fname';
      if (File(candidate).existsSync()) return candidate;
    }
    return null;
  }

  /// Collect all MP3 file paths from non-internal playlists.
  Future<Set<String>> getPlaylistMp3Files(String playlistsPath, String basePath, String libraryPath) async {
    final plDir = Directory(playlistsPath);
    if (!await plDir.exists()) return {};

    final mp3Files = <String>{};
    await for (final e in plDir.list()) {
      if (e is! File) continue;
      final low = e.path.toLowerCase();
      if (!low.endsWith('.m3u8') && !low.endsWith('.m3u')) continue;
      if (_isInternalPlaylist(e.path)) continue;

      try {
        final content = await e.readAsString(encoding: utf8);
        for (final line in content.split('\n')) {
          final trimmed = line.trim();
          if (trimmed.isEmpty || trimmed.startsWith('#')) continue;
          if (!trimmed.contains('.mp3') && !trimmed.contains('.m4a') && !trimmed.contains('.flac')) continue;
          final resolved = _resolvePlaylistPath(trimmed, playlistsPath, basePath, libraryPath);
          if (resolved != null && resolved.toLowerCase().endsWith('.mp3')) {
            mp3Files.add(resolved);
          }
        }
      } catch (_) {}
    }
    return mp3Files;
  }

  static bool _isInternalPlaylist(String path) {
    final name = File(path).uri.pathSegments.last.toLowerCase();
    if (name.contains('_removed songs') || name.contains('_unsorted') || name.contains('single tracks')) return true;
    return false;
  }

  /// Download Traditional Chinese SRT subtitles for all playlisted MP3s.
  /// Skips files that already have an .srt file alongside them.
  Future<void> downloadSrtForPlaylistMp3s({
    required void Function(String log) onLog,
    void Function(int done, int total)? onProgress,
    int concurrency = 4,
  }) async {
    final config = ConfigService.instance.config;
    final lib = config.libraryPath;
    final plPath = config.playlistsPath;
    final base = config.basePath;

    if (lib.isEmpty || plPath.isEmpty) {
      onLog('Library or Playlists path not configured');
      return;
    }

    onLog('掃描歌單中的 MP3 檔案…');
    final playlistFiles = await getPlaylistMp3Files(plPath, base, lib);
    if (playlistFiles.isEmpty) {
      onLog('歌單中沒有 MP3 檔案');
      return;
    }

    // Filter to files that don't have SRT yet
    final needSrt = <String>[];
    int skip = 0;
    for (final path in playlistFiles) {
      final srtPath = path.substring(0, path.lastIndexOf('.')) + '.srt';
      if (await File(srtPath).exists()) {
        skip++;
      } else {
        needSrt.add(path);
      }
    }

    if (needSrt.isEmpty) {
      onLog('所有歌單 MP3 已有 SRT 字幕 ($skip 檔)');
      return;
    }

    onLog('需下載 SRT: ${needSrt.length} 檔 ($skip 檔已存在)');
    final ytdlp = await _resolveYtdlp();
    int done = 0;
    int total = needSrt.length;
    int lastLog = 0;

    // Process with limited concurrency to avoid YouTube rate limiting
    for (int i = 0; i < total; i += concurrency) {
      final batch = needSrt.skip(i).take(concurrency).toList();
      final futures = <Future<void>>[];
      for (final path in batch) {
        futures.add(_downloadOne(path, ytdlp, onLog));
      }
      await Future.wait(futures);
      done += batch.length;
      onProgress?.call(done, total);

      if (done - lastLog >= 5 || done == total) {
        onLog('  SRT 進度: $done/$total');
        lastLog = done;
      }

      // Small delay between batches to avoid 429
      if (i + concurrency < total) {
        await Future.delayed(const Duration(milliseconds: 500));
      }
    }

    onLog('SRT 下載完成: $done 個字幕');
  }

  Future<void> _downloadOne(String mp3Path, String ytdlp, void Function(String) onLog) async {
    final name = mp3Path.split('\\').last;
    final srtPath = mp3Path.substring(0, mp3Path.lastIndexOf('.')) + '.srt';
    final basePath = srtPath.substring(0, srtPath.lastIndexOf('.'));
    final dir = Directory(srtPath).parent.path;

    // Get search query from filename (remove extension)
    final query = name.replaceAll(RegExp(r'\.\w+$'), '');

    try {
      // yt-dlp: search YouTube, download auto-subs, save as SRT
      final result = await Process.run(ytdlp, [
        'ytsearch:$query',
        '--skip-download',
        '--write-auto-subs',
        '--sub-lang', 'zh-Hant',
        '--sub-format', 'srt',
        '--convert-subs', 'srt',
        '--output', '$basePath.%(ext)s',
        '--quiet', '--no-warnings',
        '--windows-filenames',
        '--retries', '2',
        '--sleep-requests', '1.0',
      ], runInShell: true, workingDirectory: dir);

      if (result.exitCode != 0) {
        final err = (result.stderr as String?)?.toLowerCase() ?? '';
        if (err.contains('no subtitles') || err.contains('requested format not available')) {
          onLog('  ⚠️ $name: 無可用字幕');
        } else if (err.contains('429') || err.contains('rate limit')) {
          onLog('  🐢 $name: YouTube 限流');
        } else if (err.contains('video unavailable') || err.contains('no video')) {
          onLog('  ❓ $name: 找不到影片');
        } else {
          onLog('  ❌ $name: $err'.substring(0, 80).replaceAll('\n', ' '));
        }
        return;
      }

      // Find the actual SRT file (yt-dlp may add language suffix like .zh-Hant.srt)
      var foundSrt = srtPath;
      if (!await File(foundSrt).exists()) {
        final candidates = <String>[];
        try {
          await for (final f in Directory(dir).list()) {
            if (f is File) {
              final fname = f.path.split('\\').last;
              if (fname.startsWith(name.replaceAll(RegExp(r'\.\w+$'), '')) && fname.endsWith('.srt')) {
                candidates.add(f.path);
              }
            }
          }
        } catch (_) {}

        if (candidates.isNotEmpty) {
          foundSrt = candidates.first;
          if (foundSrt != srtPath) {
            await File(foundSrt).rename(srtPath);
          }
          // Clean up any other leftover files (like .zh-Hant.srt.vtt)
          for (final c in candidates) {
            if (c != srtPath && c != foundSrt) {
              try { await File(c).delete(); } catch (_) {}
            }
          }
          onLog('  ✅ $name: 字幕已下載');
        } else {
          onLog('  ⚠️ $name: 下載後找不到 SRT 檔');
        }
      } else {
        onLog('  ✅ $name: 字幕已下載');
      }
    } catch (ex) {
      onLog('  ⚠️ $name: $ex');
    }
  }
}
