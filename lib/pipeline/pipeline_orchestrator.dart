import 'dart:convert';
import 'dart:io';
import '../models/pipeline_step.dart';
import '../models/config_model.dart';
import '../services/library_index.dart';
import '../services/audio_converter.dart';
import '../services/spotify_scraper.dart';
import '../services/metadata_reader.dart';
import '../services/metadata_enricher.dart';
import '../services/snapshot_manager.dart';
import '../services/file_renamer.dart';
import '../services/playlist_parser.dart';
import '../services/lufs_service.dart';
import '../services/rag_service.dart';
import '../services/youtube_service.dart';

class PipelineOrchestrator {
  final AppConfig config;
  final void Function(String) onLog;
  final void Function(int current, int total, int stepIndex) onProgress;
  final PipelineState state;

  PipelineOrchestrator({
    required this.config,
    required this.onLog,
    required this.onProgress,
    PipelineState? state,
  }) : state = state ?? PipelineState();

  Future<void> run({int fromStep = 0, int? toStep}) async {
    final steps = <(String, double, Future<void> Function(void Function(double)))>[
      ('Scrape Spotify playlists', 25.0, _stepScrape),
      ('Download missing tracks', 30.0, _stepDownload),
      ('Prune missing tracks', 15.0, _stepPrune),
      ('Organize unsorted songs', 10.0, _stepUnsorted),
      ('Enrich metadata', 10.0, _stepMetadata),
      ('Measure LUFS', 10.0, _stepMeasureLufs),
    ];
    if (config.podcastRagInMusic) {
      steps.add(('Podcast RAG index', 10.0, _stepRag));
    }

    final end = toStep ?? steps.length;
    int doneWeight = 0;
    for (int i = 0; i < fromStep && i < steps.length; i++) {
      doneWeight += steps[i].$2.toInt();
    }

    for (int i = fromStep; i < end; i++) {
      if (state.isCancelled) break;
      await state.waitIfPaused();
      if (state.isCancelled) break;

      onLog('--- Step ${i + 1}/${steps.length}: ${steps[i].$1} ---');
      onProgress(0, 100, i);

      try {
        await steps[i].$3((pct) {
          final global = doneWeight + (pct / 100.0 * steps[i].$2);
          onProgress(global.toInt(), 100, i);
        });
      } catch (e) {
        onLog('  ❌ ${steps[i].$1} 失敗: $e');
        if (!state.isCancelled) {
          state.cancel();
        }
      }
      doneWeight += steps[i].$2.toInt();
    }

    if (state.isCancelled) {
      onLog('Pipeline 已取消');
    } else {
      onLog('Pipeline 完成');
    }
  }

  /// Standalone RAG index rebuild (index position varies when the RAG step is
  /// toggled in the music pipeline, so run it directly).
  Future<void> runRagOnly() async {
    onLog('--- Podcast RAG index ---');
    _stepRag((_) {});
  }

  Future<void> _stepDownload(void Function(double) progress) async {
    final musicDir = Directory(config.musicPath);
    await musicDir.create(recursive: true);

    // Load snapshot_cache.json (built by Step 1 via SnapshotManager).
    final snapFile = File('${config.basePath}\\snapshot_cache.json');
    if (!await snapFile.exists()) {
      onLog('找不到 snapshot_cache.json，跳過下載');
      progress(100); return;
    }
    final snap = jsonDecode(await snapFile.readAsString()) as Map<String, dynamic>;
    final playlists = snap['playlists'] as Map<String, dynamic>? ?? {};

    // Collect all unique songs from playlists.
    final allSongs = <String>{};
    for (final pl in playlists.values) {
      final tracks = (pl as Map<String, dynamic>)['tracks'] as List<dynamic>? ?? [];
      for (final t in tracks) {
        allSongs.add(t as String);
      }
    }
    if (allSongs.isEmpty) {
      onLog('無歌曲需下載');
      progress(100); return;
    }
    onLog('播放清單共 ${allSongs.length} 首歌曲');

    // Check which already exist in musicPath.
    final existing = <String>{};
    if (await musicDir.exists()) {
      await for (final f in musicDir.list()) {
        if (f is File) {
          final stem = File(f.path).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
          existing.add(stem.toLowerCase());
        }
      }
    }
    final missing = allSongs.where((s) => !existing.contains(s.toLowerCase())).toList();
    onLog('已有 ${existing.length} 首，需下載 ${missing.length} 首');

    if (missing.isEmpty) {
      onLog('所有歌曲已下載');
      progress(100); return;
    }

    // Download missing songs using native YoutubeService + ffmpeg.
    int done = 0;
    int ok = 0;
    int fail = 0;
    final total = missing.length;
        final ffmpeg = config.resolvedFfmpegPath;
    final yt = YoutubeService.instance;

    for (final song in missing) {
      if (state.isCancelled) return;
      await state.waitIfPaused();
      if (state.isCancelled) return;

      final safeName = song.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_');
      final outPath = '${musicDir.path}\\$safeName.mp3';

      onLog('  [$done/$total] $song');

      try {
        final result = await yt.resolveStream(song).timeout(
          const Duration(seconds: 45),
          onTimeout: () { onLog('  ⏰ 搜尋超時: $song'); return null; },
        );
        if (result == null) {
          onLog('  ❌ 找不到: $song');
          fail++;
          done++;
          progress((done / total * 100).toDouble());
          continue;
        }
        final tmpPath = '${musicDir.path}\\dl_${safeName.hashCode.toRadixString(16)}.mp3';
        final proc = await Process.start(
          ffmpeg,
          ['-y', '-i', result.audioUrl, '-vn', '-acodec', 'libmp3lame', '-q:a', '0', '-ac', '2', tmpPath],
          runInShell: true,
        );
        final code = await proc.exitCode.timeout(
          const Duration(seconds: 120),
          onTimeout: () { proc.kill(); return -1; },
        );
        if (code == 0 && File(tmpPath).existsSync()) {
          if (File(outPath).existsSync()) await File(outPath).delete();
          await File(tmpPath).rename(outPath);
          ok++;
        } else {
          fail++;
        }
      } catch (e) {
        onLog('  ❌ 異常: $song → $e');
        fail++;
      }
      done++;
      progress((done / total * 100).toDouble());
    }

    onLog('下載完成: $ok 成功, $fail 失敗 (共 $total 首)');
    progress(100);
  }

  String _findBridge() {
    final exeDir = Directory(File(Platform.resolvedExecutable).parent.path);
    Directory? d = exeDir;
    while (d != null) {
      final candidate = '${d.path}\\tools\\flutter_download_bridge.py';
      if (File(candidate).existsSync()) return candidate;
      d = d.parent.path == d.path ? null : d.parent;
    }
    return '';
  }

  Future<void> _stepScrape(void Function(double) progress) async {
    final urls = config.urlNames.keys.toList();
    if (urls.isEmpty) {
      onLog('沒有 Spotify URL');
      progress(100); return;
    }
    await Directory(config.playlistsPath).create(recursive: true);

    final scraper = SpotifyScraper(log: onLog, playlistsPath: config.playlistsPath, libraryPath: config.libraryPath);
    final plResults = await scraper.scrapeAll(urls);

    // Snapshot: save ALL track names from scraper (not just resolved ones from m3u8).
    int totalRemoved = 0;
    for (final entry in plResults.entries) {
      final plName = entry.key;
      final allTracks = entry.value;
      final removed = SnapshotManager.processPlaylist(plName, allTracks);
      if (removed > 0) {
        onLog('  📋 $plName: 偵測到 $removed 首已移除歌曲');
        totalRemoved += removed;
      }
    }
    if (totalRemoved > 0) {
      onLog('  📋 共 $totalRemoved 首已移除歌曲被記錄');
    }
    progress(100);
  }

  Future<void> _stepPrune(void Function(double) progress) async {
    final plDir = Directory(config.playlistsPath);
    if (!await plDir.exists()) {
      onLog('播放清單資料夾不存在');
      progress(100); return;
    }

    final files = <String>[];
    await for (final e in plDir.list()) {
      if (e is File) {
        final low = e.path.toLowerCase();
        if (low.endsWith('.m3u8') || low.endsWith('.m3u')) {
          files.add(e.path);
        }
      }
    }

    totalRemoved = 0;
    int totalFiles = files.length;

    for (int i = 0; i < files.length; i++) {
      if (state.isCancelled) return;
      await state.waitIfPaused();

      final f = files[i];
      final baseName = File(f).uri.pathSegments.last;
      if (PlaylistParser.isInternalPlaylist(baseName)) {
        onLog('  跳過內部歌單: $baseName');
        progress((i + 1) / totalFiles * 100);
        continue;
      }

      try {
        final content = await File(f).readAsLines();
        final newLines = <String>[];
        int removed = 0;

        final isM3u = content.any((l) => l.contains('#EXTM3U'));

        int j = 0;
        while (j < content.length) {
          final line = content[j];
          if (line.isEmpty) { j++; continue; }

          if (isM3u && line.startsWith('#EXTINF:')) {
            int k = j + 1;
            while (k < content.length && (content[k].trim().isEmpty || content[k].startsWith('#'))) {
              k++;
            }
            if (k < content.length) {
              final pathLine = content[k].trim();
              if (_trackFileExists(pathLine)) {
                newLines.add(line);
                newLines.add(content[k]);
              } else {
                removed++;
              }
              j = k + 1;
            } else {
              newLines.add(line);
              j++;
            }
            continue;
          }

          if (line.startsWith('#') || line.trim().isEmpty) {
            newLines.add(line);
          } else {
            if (_trackFileExists(line.trim())) {
              newLines.add(line);
            } else {
              removed++;
            }
          }
          j++;
        }

        if (removed > 0) {
          await File(f).writeAsString('${newLines.join('\n')}\n');
          totalRemoved += removed;
          onLog('  $baseName: 移除 $removed 首');
        }
      } catch (e) {
        onLog('  ⚠️ 無法處理 $baseName: $e');
      }
      progress((i + 1) / totalFiles * 100);
    }
    onLog('Prune 完成，共移除 $totalRemoved 首');
  }

  int totalRemoved = 0;

  bool _trackFileExists(String entry) {
    String decodePath(String s) {
      try { return Uri.decodeComponent(s); } catch (_) { return s; }
    }
    entry = decodePath(entry);
    if (!entry.contains('.') && !entry.contains('\\')) return true;
    // Resolve relative to playlists dir first
    final relToPl = '${config.playlistsPath}\\$entry';
    if (File(relToPl).existsSync()) return true;
    // Try as absolute or CWD-relative
    if (File(entry).existsSync()) return true;
    // Try basePath/libraryPath with just the filename
    for (final base in [config.basePath, config.libraryPath, config.playlistsPath]) {
      final resolved = '$base\\${File(entry).uri.pathSegments.last}';
      if (File(resolved).existsSync()) return true;
    }
    return false;
  }

  Future<void> _stepUnsorted(void Function(double) progress) async {
    final plDir = Directory(config.playlistsPath);
    if (!await plDir.exists()) { progress(100); return; }

    final allPlaylistSongs = <String>{};
    await for (final e in plDir.list()) {
      if (e is File) {
        final low = e.path.toLowerCase();
        if (!(low.endsWith('.m3u8') || low.endsWith('.m3u'))) continue;
        if (PlaylistParser.isInternalPlaylist(File(e.path).uri.pathSegments.last)) continue;
        try {
          final names = PlaylistParser.parseTrackNames(e.path);
          for (final n in names) {
            allPlaylistSongs.add(n.replaceAll(RegExp(r'\.\w+$'), '').toLowerCase());
          }
        } catch (_) {}
      }
    }

    final unsortedFiles = <String>[];
    final libDir = Directory(config.libraryPath);
    if (await libDir.exists()) {
      await for (final e in libDir.list(recursive: true, followLinks: false)) {
        if (e is File) {
          final low = e.path.toLowerCase();
          if (!(low.endsWith('.mp3') || low.endsWith('.m4a') || low.endsWith('.flac'))) continue;
          final stem = e.uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '').toLowerCase();
          if (!allPlaylistSongs.contains(stem)) unsortedFiles.add(e.path);
        }
      }
    }

    final unsortedPath = '${config.playlistsPath}\\_Unsorted.m3u8';
    final existingStems = <String>{};
    if (await File(unsortedPath).exists()) {
      try {
        final existing = PlaylistParser.parseTrackEntries(unsortedPath);
        for (final e in existing) {
          existingStems.add(File(e).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '').toLowerCase());
        }
      } catch (_) {}
    }

    final newUnsorted = unsortedFiles.where((f) {
      final stem = File(f).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
      return !existingStems.contains(stem.toLowerCase());
    }).toList();

    if (newUnsorted.isEmpty) {
      onLog('未分類歌曲共 ${unsortedFiles.length} 首，無新增');
      progress(100); return;
    }

    final sb = StringBuffer();
    if (existingStems.isEmpty) sb.write('#EXTM3U\n');
    for (final filePath in newUnsorted) {
      final absFilePath = File(filePath).absolute.path;
      final absPlPath = Directory(unsortedPath).parent.absolute.path;
      String relPath;
      try {
        relPath = _relativePath(absFilePath, absPlPath);
      } catch (_) {
        relPath = absFilePath;
      }
      // Raw relative path only — Echo Nightly does NOT decode %XX escapes.
      final nameNoExt = File(filePath).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
      sb.writeln('#EXTINF:-1,$nameNoExt');
      sb.writeln(relPath);
    }

    await File(unsortedPath).writeAsString(sb.toString(),
        mode: existingStems.isEmpty ? FileMode.write : FileMode.append);
    onLog('已為 ${newUnsorted.length} 首新未分類歌曲更新清單 (共 ${unsortedFiles.length} 首)');
    progress(100);
  }

  String _relativePath(String absPath, String relativeTo) {
    final absParts = absPath.replaceAll('\\', '/').split('/');
    final relParts = relativeTo.replaceAll('\\', '/').split('/');
    if (absParts.first.toLowerCase() != relParts.first.toLowerCase()) {
      // 跨磁碟：回傳絕對路徑，避免產生 ../../D:/ 這種無效相對路徑
      return absPath.replaceAll('\\', '/');
    }
    int common = 0;
    while (common < absParts.length && common < relParts.length &&
        absParts[common].toLowerCase() == relParts[common].toLowerCase()) {
      common++;
    }
    final up = List.filled(relParts.length - common, '..');
    final down = absParts.sublist(common);
    return [...up, ...down].join('/');
  }

  Future<void> _stepMetadata(void Function(double) progress) async {
    if (!config.enableMetadataEnrichment) {
      onLog('Metadata enrichment 未啟用，跳過');
      progress(100);
      return;
    }
    onLog('Metadata enrichment 已啟用，開始掃描…');
    final enricher = MetadataEnricher(
      log: onLog,
      libraryPath: config.libraryPath,
    );
    await enricher.enrichAll(onProgress: (current, total) {
      progress(total > 0 ? current / total * 100 : 0);
    });

    onLog('根據 metadata 重新命名檔案…');
    final renamer = FileRenamer(
      log: onLog,
      libraryPath: config.libraryPath,
    );
    final result = await renamer.batchRename();
    final renamed = result['renamed'] as int;
    if (renamed > 0) {
      onLog('重新命名完成: $renamed 個檔案');
    } else {
      onLog('無需重新命名');
    }
    progress(100);
  }

  Future<void> _stepMeasureLufs(void Function(double) progress) async {
    try {
      final svc = LufsService.instance;
      await svc.measureAndNormalizePlaylistMp3s(
        onLog: onLog,
        onProgress: (done, total) {
          progress(total > 0 ? done / total * 100 : 0);
        },
        concurrency: 8,
        tolerance: 2.0,
        isCancelled: () => state.isCancelled,
      );
    } catch (e) {
      onLog('LUFS 異常: $e');
    }
    progress(100);
  }

  /// Update the podcast RAG vector index (incremental, non-fatal).
  Future<void> _stepRag(void Function(double) progress) async {
    if (state.isCancelled) return;
    onLog('檢查 Podcast 逐字稿並更新 RAG 向量庫…');
    try {
      await RagService.instance.build((line) {
        if (state.isCancelled) return;
        onLog('  $line');
        // build_db.py 進度行格式: [12/219] 42.5% | ...
        final m = RegExp(r'\[(\d+)/(\d+)\]\s+[\d.]+%').firstMatch(line);
        if (m != null) {
          final done = int.tryParse(m.group(1)!) ?? 0;
          final total = int.tryParse(m.group(2)!) ?? 0;
          if (total > 0) progress(done / total * 100);
        }
      });
      onLog('✅ RAG 索引已更新');
    } catch (e) {
      onLog('  ⚠️ RAG 索引更新失敗（需要 Ollama + chromadb）: $e');
    }
    progress(100);
  }
}

class _ConvertTask {
  final String src;
  final String dest;
  final String stem;
  final TrackMetadata meta;
  _ConvertTask(this.src, this.dest, this.stem, this.meta);
}
