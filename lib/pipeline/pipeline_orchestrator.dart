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
    final steps = [
      ('Convert M4A → MP3', 25.0),
      ('Scrape Spotify playlists', 20.0),
      ('Prune missing tracks', 15.0),
      ('Organize unsorted songs', 10.0),
      ('Enrich metadata', 10.0),
      ('Measure LUFS', 10.0),
      ('Podcast RAG index', 10.0),
    ];

    final end = toStep ?? steps.length;
    int doneWeight = 0;

    for (int i = fromStep; i < end; i++) {
      if (state.isCancelled) break;
      await state.waitIfPaused();
      if (state.isCancelled) break;

      onLog('--- Step ${i + 1}/${steps.length}: ${steps[i].$1} ---');
      onProgress(0, 100, i);

      try {
        await _runStep(i, (pct) {
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

  Future<void> _runStep(int index, void Function(double) progress) async {
    switch (index) {
      case 0: await _stepConvert(progress); break;
      case 1: await _stepScrape(progress); break;
      case 2: await _stepPrune(progress); break;
      case 3: await _stepUnsorted(progress); break;
      case 4: await _stepMetadata(progress); break;
      case 5: await _stepMeasureLufs(progress); break;
      case 6: await _stepRag(progress); break;
    }
  }

  Future<void> _stepConvert(void Function(double) progress) async {
    final m4aDir = Directory(config.m4aPath);
    final mp3Dir = Directory(config.mp3Path);
    if (!await m4aDir.exists()) {
      onLog('M4A 資料夾不存在: ${config.m4aPath}');
      progress(100); return;
    }
    await mp3Dir.create(recursive: true);

    final m4aFiles = <String>[];
    await for (final e in m4aDir.list(recursive: true, followLinks: false)) {
      if (e is File && e.path.toLowerCase().endsWith('.m4a')) {
        m4aFiles.add(e.path);
      }
    }
    if (m4aFiles.isEmpty) {
      // Fallback: scan library root for M4A
      final libM4a = <String>[];
      final libDir = Directory(config.libraryPath);
      if (await libDir.exists()) {
        await for (final e in libDir.list(recursive: true, followLinks: false)) {
          if (e is File && e.path.toLowerCase().endsWith('.m4a')) {
            libM4a.add(e.path);
          }
        }
      }
      if (libM4a.isEmpty) {
        onLog('找不到任何 M4A 檔案');
        progress(100); return;
      }
      onLog('在音樂庫根目錄找到 ${libM4a.length} 個 M4A 檔案');
      m4aFiles.addAll(libM4a);
    } else {
      onLog('找到 ${m4aFiles.length} 個 M4A 檔案');
    }

    final index = LibraryIndex();
    await index.build(config.libraryPath, onLog, basePath: config.basePath);

    final tasks = <_ConvertTask>[];
    int skipped = 0;

    final totalM4a = m4aFiles.length;
    int scanned = 0;
    for (final m4a in m4aFiles) {
      await state.waitIfPaused();
      if (state.isCancelled) return;

      // 1. Filename-based matching (fast, no ffprobe)
      final existing = await index.findMp3ForM4a(m4a, useMtime: true);
      if (existing != null) {
        skipped++;
        scanned++;
        if (scanned % 200 == 0 || scanned == totalM4a) {
          onLog('  比對: $scanned/$totalM4a (待轉檔 ${tasks.length}，跳過 $skipped)');
        }
        continue;
      }

      // 2. Only read metadata for files that actually need conversion
      final meta = await MetadataReader.read(m4a);

      // 3. Metadata-based matching (tries to find MP3 by title/artist)
      final metaMatch = await index.findMp3ForM4a(m4a, useMtime: true, cachedMeta: meta);
      if (metaMatch != null) {
        skipped++;
        scanned++;
        if (scanned % 200 == 0 || scanned == totalM4a) {
          onLog('  比對: $scanned/$totalM4a (待轉檔 ${tasks.length}，跳過 $skipped)');
        }
        continue;
      }

      final stem = File(m4a).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
      final mp3Name = '$stem.mp3';
      final dest = '${config.mp3Path}\\$mp3Name';

      // 4. Direct disk check: the in-memory index may be stale (built before
      // this run converted files), so trust the filesystem over the index.
      // Zero-byte files are failed leftovers — never skip those.
      final destFile = File(dest);
      if (await destFile.exists() &&
          (await destFile.length()) > 0 &&
          destFile.lastModifiedSync().compareTo(File(m4a).lastModifiedSync()) >= 0) {
        skipped++;
        scanned++;
        if (scanned % 200 == 0 || scanned == totalM4a) {
          onLog('  比對: $scanned/$totalM4a (待轉檔 ${tasks.length}，跳過 $skipped)');
        }
        continue;
      }

      tasks.add(_ConvertTask(m4a, dest, stem, meta));

      scanned++;
      if (scanned % 200 == 0 || scanned == totalM4a) {
        onLog('  比對: $scanned/$totalM4a (待轉檔 ${tasks.length}，跳過 $skipped)');
      }
    }

    onLog('待轉檔: ${tasks.length}, 跳過: $skipped');
    if (tasks.isEmpty) { progress(100); return; }

    // Worker pool: keep N conversions running at all times.
    // Each ffmpeg uses -threads 0 (auto, multi-threaded), so cap concurrency
    // at physical cores to avoid oversubscription.
    final physicalCores = (Platform.numberOfProcessors ~/ 2).clamp(2, 16);
    final concurrency = physicalCores;
    int converted = 0;
    int done = 0;
    var next = 0;

    Future<void> worker() async {
      while (true) {
        if (state.isCancelled) return;
        await state.waitIfPaused();
        if (state.isCancelled) return;

        final idx = next++;
        if (idx >= tasks.length) return;

        final t = tasks[idx];
        final fname = File(t.src).uri.pathSegments.last;
        final (ok, lufs) = await AudioConverter.convert(
          inputPath: t.src,
          outputPath: t.dest,
          ffmpegPath: config.ffmpegPath.isNotEmpty ? config.ffmpegPath : 'ffmpeg',
          meta: t.meta,
          isCancelled: () => state.isCancelled,
        );
        if (state.isCancelled) return;
        done++;
        if (ok) {
          converted++;
          // loudnorm measured the whole file during conversion — cache it directly,
          // no second full-file scan. Fast path only; never blocks the worker.
          LufsService.instance.cacheConversionLufsFast(t.src, t.dest, lufs);
        }
        onLog('  [$done/${tasks.length}] ${ok ? '✅' : '❌'} $fname');
        progress(done / tasks.length * 100);
      }
    }

    await Future.wait(List.generate(concurrency, (_) => worker()));

    onLog('轉檔完成: $converted 個');
  }

  Future<void> _stepScrape(void Function(double) progress) async {
    final urls = config.urlNames.keys.toList();
    if (urls.isEmpty) {
      onLog('沒有 Spotify URL');
      progress(100); return;
    }
    await Directory(config.playlistsPath).create(recursive: true);

    final scraper = SpotifyScraper(log: onLog, playlistsPath: config.playlistsPath, libraryPath: config.libraryPath);
    final plNames = await scraper.scrapeAll(urls);

    // Snapshot: detect removed songs per playlist
    int totalRemoved = 0;
    for (final plName in plNames) {
      final plFile = File('${config.playlistsPath}\\$plName.m3u8');
      if (!await plFile.exists()) continue;
      try {
        final tracks = PlaylistParser.parseTrackNames(plFile.path);
        if (tracks.isEmpty) continue;
        final removed = SnapshotManager.processPlaylist(plName, tracks);
        if (removed > 0) {
          onLog('  📋 $plName: 偵測到 $removed 首已移除歌曲');
          totalRemoved += removed;
        }
      } catch (e) {
        onLog('  ⚠️ 無法處理 $plName 快照: $e');
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
      // Echo Nightly compatible: URI-encode the relative path
      final encPath = Uri.encodeComponent(relPath).replaceAll('%2F', '/');
      final nameNoExt = File(filePath).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
      sb.writeln('#EXTINF:-1,$nameNoExt');
      sb.writeln(encPath);
    }

    await File(unsortedPath).writeAsString(sb.toString(),
        mode: existingStems.isEmpty ? FileMode.write : FileMode.append);
    onLog('已為 ${newUnsorted.length} 首新未分類歌曲更新清單 (共 ${unsortedFiles.length} 首)');
    progress(100);
  }

  String _relativePath(String absPath, String relativeTo) {
    final absParts = absPath.replaceAll('\\', '/').split('/');
    final relParts = relativeTo.replaceAll('\\', '/').split('/');
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
