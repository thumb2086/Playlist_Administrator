import 'dart:io';
import '../models/pipeline_step.dart';
import '../models/config_model.dart';
import '../services/library_index.dart';
import '../services/audio_converter.dart';
import '../services/spotify_scraper.dart';
import '../services/metadata_reader.dart';
import '../services/metadata_enricher.dart';
import '../services/snapshot_manager.dart';

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

  Future<void> run({int fromStep = 0}) async {
    final steps = [
      ('Convert M4A → MP3', 35.0),
      ('Scrape Spotify playlists', 30.0),
      ('Prune missing tracks', 15.0),
      ('Organize unsorted songs', 10.0),
      ('Enrich metadata', 10.0),
    ];

    int doneWeight = 0;

    for (int i = fromStep; i < steps.length; i++) {
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
    }
  }

  Future<void> _stepConvert(void Function(double) progress) async {
    final m4aDir = Directory(config.m4aPath);
    final mp3Dir = Directory(config.mp3Path);
    if (!await m4aDir.exists()) {
      onLog('M4A 資料夾不存在: ${config.m4aPath}');
      return;
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
        return;
      }
      onLog('在音樂庫根目錄找到 ${libM4a.length} 個 M4A 檔案');
      m4aFiles.addAll(libM4a);
    } else {
      onLog('找到 ${m4aFiles.length} 個 M4A 檔案');
    }

    final index = LibraryIndex();
    await index.build(config.libraryPath, onLog);

    final tasks = <_ConvertTask>[];
    int skipped = 0;

    for (final m4a in m4aFiles) {
      await state.waitIfPaused();
      if (state.isCancelled) return;

      final existing = index.findMp3ForM4a(m4a, useMtime: true);
      if (existing != null) {
        skipped++;
        continue;
      }

      final stem = File(m4a).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
      final meta = await MetadataReader.read(m4a);
      final mp3Name = (meta.title != null && meta.title!.isNotEmpty)
          ? '${meta.title}${meta.artist != null ? ' - ${meta.artist}' : ''}.mp3'
              .replaceAll(RegExp(r'[<>:"/\\|?*]'), '_')
          : '$stem.mp3';
      final dest = '${config.mp3Path}\\$mp3Name';

      tasks.add(_ConvertTask(m4a, dest, stem));
    }

    onLog('待轉檔: ${tasks.length}, 跳過: $skipped');
    if (tasks.isEmpty) return;

    const batchSize = 50;
    int converted = 0;
    for (int i = 0; i < tasks.length; i += batchSize) {
      if (state.isCancelled) return;
      await state.waitIfPaused();

      final batch = tasks.skip(i).take(batchSize).toList();
      final futures = <Future<bool>>[];
      for (final t in batch) {
        futures.add(AudioConverter.convert(
          inputPath: t.src,
          outputPath: t.dest,
          ffmpegPath: config.ffmpegPath.isNotEmpty ? config.ffmpegPath : 'ffmpeg',
        ));
      }
      final results = await Future.wait(futures);
      converted += results.where((r) => r).length;

      final pct = (i + batch.length) / tasks.length * 100;
      progress(pct);
      onLog('  進度: ${i + batch.length}/${tasks.length}');
    }

    onLog('轉檔完成: $converted 個');
  }

  Future<void> _stepScrape(void Function(double) progress) async {
    final urls = config.urlNames.keys.toList();
    if (urls.isEmpty) {
      onLog('沒有 Spotify URL');
      return;
    }
    await Directory(config.playlistsPath).create(recursive: true);

    final scraper = SpotifyScraper(log: onLog, playlistsPath: config.playlistsPath);
    final plNames = await scraper.scrapeAll(urls);

    // Snapshot: detect removed songs per playlist
    int totalRemoved = 0;
    for (final plName in plNames) {
      final plFile = File('${config.playlistsPath}\\$plName.m3u8');
      if (!await plFile.exists()) continue;
      try {
        final lines = await plFile.readAsLines();
        final tracks = lines
            .where((l) => l.startsWith('#EXTINF:'))
            .map((l) {
              final idx = l.indexOf(',');
              return idx > 0 ? l.substring(idx + 1).trim() : '';
            })
            .where((t) => t.isNotEmpty)
            .toList();
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
      return;
    }

    final files = <String>[];
    await for (final e in plDir.list()) {
      if (e is File && e.path.toLowerCase().endsWith('.m3u8')) {
        files.add(e.path);
      }
    }

    int totalRemoved = 0;
    int totalFiles = files.length;

    for (int i = 0; i < files.length; i++) {
      if (state.isCancelled) return;
      await state.waitIfPaused();

      final f = files[i];
      try {
        final content = await File(f).readAsLines();
        final newLines = <String>[];
        int removed = 0;

        for (final line in content) {
          if (line.startsWith('#') || line.trim().isEmpty) {
            newLines.add(line);
          } else {
            String resolved = line;
            if (!File(line).existsSync()) {
              resolved = '${config.libraryPath}\\${File(line).uri.pathSegments.last}';
            }
            if (await File(resolved).exists()) {
              newLines.add(line);
            } else {
              removed++;
            }
          }
        }

        if (removed > 0) {
          await File(f).writeAsString('${newLines.join('\n')}\n');
          totalRemoved += removed;
          onLog('  ${File(f).uri.pathSegments.last}: 移除 $removed 首');
        }
      } catch (e) {
        onLog('  ⚠️ 無法處理 ${File(f).uri.pathSegments.last}: $e');
      }
      progress((i + 1) / totalFiles * 100);
    }
    onLog('Prune 完成，共移除 $totalRemoved 首');
  }

  Future<void> _stepUnsorted(void Function(double) progress) async {
    final plDir = Directory(config.playlistsPath);
    if (!await plDir.exists()) return;

    final playlists = <String>[];
    await for (final e in plDir.list()) {
      if (e is File && e.path.toLowerCase().endsWith('.m3u8')) {
        playlists.add(e.path);
      }
    }

    final allPlaylistSongs = <String>{};
    for (final pl in playlists) {
      try {
        final lines = await File(pl).readAsLines();
        for (final line in lines) {
          if (!line.startsWith('#') && line.trim().isNotEmpty) {
            allPlaylistSongs.add(File(line).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), ''));
          }
        }
      } catch (_) {}
    }

    final unsorted = <String>[];
    final libDir = Directory(config.libraryPath);
    if (await libDir.exists()) {
      final index = LibraryIndex();
      await index.build(config.libraryPath, (_) {});

      await for (final e in libDir.list(recursive: true, followLinks: false)) {
        if (e is File) {
          final low = e.path.toLowerCase();
          if (low.endsWith('.mp3') || low.endsWith('.m4a') || low.endsWith('.flac')) {
            final stem = e.uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
            if (!index.isSongInPlaylists(stem, allPlaylistSongs.toList())) {
              unsorted.add(stem);
            }
          }
        }
      }
    }

    if (unsorted.isNotEmpty) {
      final existing = <String>{};
      if (await File('${config.playlistsPath}\\Unsorted.m3u8').exists()) {
        try {
          final lines = await File('${config.playlistsPath}\\Unsorted.m3u8').readAsLines();
          for (final line in lines) {
            if (!line.startsWith('#') && line.trim().isNotEmpty) {
              existing.add(File(line).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), ''));
            }
          }
        } catch (_) {}
      }
      final newUnsorted = unsorted.where((s) => !existing.contains(s)).toList();

      if (newUnsorted.isNotEmpty) {
        final sb = StringBuffer();
        if (existing.isEmpty) sb.write('#EXTM3U\n');
        for (final s in newUnsorted) {
          sb.writeln('#EXTINF:-1,$s');
          sb.writeln(s);
        }
        await File('${config.playlistsPath}\\Unsorted.m3u8')
            .writeAsString(sb.toString(), mode: existing.isEmpty ? FileMode.write : FileMode.append);
        onLog('已為 ${newUnsorted.length} 首新未分類歌曲更新清單 (共 ${unsorted.length} 首)');
      } else {
        onLog('未分類歌曲共 ${unsorted.length} 首，無新增');
      }
    } else {
      onLog('沒有未分類歌曲');
    }
    progress(100);
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
    progress(100);
  }
}

class _ConvertTask {
  final String src;
  final String dest;
  final String stem;
  _ConvertTask(this.src, this.dest, this.stem);
}
