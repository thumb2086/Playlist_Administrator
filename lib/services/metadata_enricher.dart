import 'dart:convert';
import 'dart:io';
import 'config_service.dart';
import 'metadata_reader.dart';

class MetadataEnricher {
  final void Function(String) log;
  final String libraryPath;

  MetadataEnricher({required this.log, required this.libraryPath});

  Future<void> enrichAll({void Function(int, int)? onProgress}) async {
    log('🔍 掃描缺少 metadata 的檔案…');
    final files = await _scanMissingMetadata();
    if (files.isEmpty) {
      log('✅ 所有檔案都有完整 metadata');
      return;
    }

    log('🎵 找到 ${files.length} 個檔案缺少 metadata，開始補充…');
    int success = 0;

    for (int i = 0; i < files.length; i++) {
      final path = files[i];
      try {
        final ok = await _enrichFile(path);
        if (ok) success++;
      } catch (e) {
        log('  ❌ ${path.split('\\').last}: $e');
      }
      if (onProgress != null) onProgress(i + 1, files.length);
      if (i % 10 == 9 || i == files.length - 1) {
        log('  進度: ${i + 1}/${files.length} (成功: $success)');
      }
    }
    log('🎉 Metadata 補充完成: $success/${files.length}');
  }

  Future<List<String>> _scanMissingMetadata() async {
    final missing = <String>[];
    final dir = Directory(libraryPath);
    if (!await dir.exists()) return missing;

    await for (final e in dir.list(recursive: true, followLinks: false)) {
      if (e is! File) continue;
      final low = e.path.toLowerCase();
      if (!low.endsWith('.mp3') && !low.endsWith('.m4a') && !low.endsWith('.flac')) continue;

      final meta = await MetadataReader.read(e.path);
      if (meta.title == null || meta.title!.isEmpty || meta.artist == null || meta.artist!.isEmpty) {
        missing.add(e.path);
      }
    }
    return missing;
  }

  Future<bool> _enrichFile(String filePath) async {
    final stem = File(filePath).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
    final meta = await MetadataReader.read(filePath);

    String? title = meta.title;
    String? artist = meta.artist;
    String? album;
    String? year;
    String? coverUrl;

    // 1. Try Spotify cache
    final cached = _loadSpotifyCache(stem);
    if (cached != null) {
      title ??= cached['title'] as String?;
      artist ??= cached['artist'] as String?;
      album ??= cached['album'] as String?;
      final rd = cached['release_date'] as String?;
      if (rd != null && rd.length >= 4) year = rd.substring(0, 4);
      coverUrl ??= cached['cover_url'] as String?;
    }

    // 2. If still no title/artist, try to extract from filename
    final fileName = File(filePath).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
    if ((title == null || title.isEmpty) && fileName.contains(' - ')) {
      final parts = fileName.split(' - ');
      if (parts.length >= 2) {
        artist = parts[0].trim();
        title = parts.sublist(1).join(' - ').trim();
      }
    }

    if (title == null || title.isEmpty) {
      title = fileName;
    }

    // Apply metadata via ffmpeg
    return _applyMetadata(filePath, title, artist, album, year, coverUrl);
  }

  Map<String, dynamic>? _loadSpotifyCache(String stem) {
    try {
      final base = ConfigService.instance.config.basePath;
      if (base.isEmpty) return null;
      final cacheDir = Directory('$base\\spotify_cache');
      if (!cacheDir.existsSync()) return null;

      // Try exact match
      final exactFile = File('$base\\spotify_cache\\$stem.json');
      if (exactFile.existsSync()) {
        return jsonDecode(exactFile.readAsStringSync()) as Map<String, dynamic>;
      }

      // Try fuzzy match by iterating all cache files
      for (final f in cacheDir.listSync()) {
        if (f is File && f.path.endsWith('.json')) {
          try {
            final data = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
            final cacheTitle = (data['title'] as String? ?? '').toLowerCase().replaceAll(' ', '');
            final stemLower = stem.toLowerCase().replaceAll(' ', '');
            if (cacheTitle.contains(stemLower) || stemLower.contains(cacheTitle)) {
              return data;
            }
          } catch (_) {}
        }
      }
    } catch (_) {}
    return null;
  }

  Future<bool> _applyMetadata(
    String filePath,
    String? title,
    String? artist,
    String? album,
    String? year,
    String? coverUrl,
  ) async {
    try {
      final ext = filePath.toLowerCase().split('.').last;
      final tmpPath = '${filePath}_tmp.$ext';

      final cmd = <String>['ffmpeg', '-y', '-i', filePath, '-c', 'copy'];
      if (title != null && title.isNotEmpty) cmd.addAll(['-metadata', 'title=$title']);
      if (artist != null && artist.isNotEmpty) cmd.addAll(['-metadata', 'artist=$artist']);
      if (album != null && album.isNotEmpty) cmd.addAll(['-metadata', 'album=$album']);
      if (year != null && year.isNotEmpty) cmd.addAll(['-metadata', 'date=$year']);
      cmd.add(tmpPath);

      final result = await Process.run(cmd[0], cmd.sublist(1), runInShell: true);

      if (result.exitCode == 0) {
        await File(filePath).delete();
        await File(tmpPath).rename(filePath);
        log('  ✅ 已更新 metadata: ${File(filePath).uri.pathSegments.last}');
        return true;
      } else {
        if (await File(tmpPath).exists()) await File(tmpPath).delete();
        log('  ⚠️ 寫入 metadata 失敗: ${File(filePath).uri.pathSegments.last}');
        return false;
      }
    } catch (e) {
      log('  ⚠️ Metadata 寫入錯誤: $e');
      return false;
    }
  }
}
