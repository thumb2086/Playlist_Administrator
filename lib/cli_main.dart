import 'dart:io';
import 'models/config_model.dart';
import 'services/config_service.dart';
import 'services/favorites_service.dart';
import 'services/spotube_controller.dart';
import 'pipeline/pipeline_orchestrator.dart';
import 'pipeline/podcast_pipeline.dart';
import 'models/pipeline_step.dart';

// Shared CLI engine — used by the Flutter app binary itself (main.dart
// dispatches CLI args here) and by `playlist-admin` (npm wrapper spawning
// the built exe). One engine, two surfaces.
Future<void> runCli(List<String> args) async {
  await ConfigService.instance.load();
  final cfg = ConfigService.instance.config;

  if (args.isEmpty) {
    print('''playlist-admin CLI
Usage:
  dart cli_main.dart pipeline                   Run full pipeline
  dart cli_main.dart pipeline --step N          Run single step
  dart cli_main.dart spotube-download <name>    Download one playlist
  dart cli_main.dart spotube-download-all       Download all playlists
  dart cli_main.dart spotube-move               Move M4A files
     dart cli_main.dart spotube-cleanup            Remove metadata-renamed mp3 duplicates
   dart cli_main.dart status                     Show status
  dart cli_main.dart favorite list              List favorite songs
  dart cli_main.dart favorite toggle <song>     Toggle favorite (我的最愛) by filename or path
''');
    return;
  }

  final cmd = args[0];

  switch (cmd) {
    case 'pipeline':
      final fromStep = _getFlag(args, '--step');
      final state = PipelineState();
      final orch = PipelineOrchestrator(
        config: cfg,
        onLog: (msg) => print(msg),
        onProgress: (c, t, s) {},
        state: state,
      );
      await orch.run(fromStep: fromStep);
      break;

    case 'spotube-download':
      if (args.length < 2) {
        print('Usage: dart cli_main.dart spotube-download <playlist_name>');
        return;
      }
      final ctrl = SpotubeController(
        libraryPath: cfg.libraryPath,
        coords: cfg.spotubeCoords,
      );
      if (!ctrl.isRunning()) {
        print('Spotube is not running');
        return;
      }
      await ctrl.downloadPlaylist(args[1]);
      break;

    case 'spotube-download-all':
      final ctrl = SpotubeController(
        libraryPath: cfg.libraryPath,
        coords: cfg.spotubeCoords,
      );
      if (!ctrl.isRunning()) {
        print('Spotube is not running');
        return;
      }
      for (final name in cfg.urlNames.values) {
        print('Downloading: $name');
        await ctrl.downloadPlaylist(name);
      }
      break;

    case 'spotube-move':
      final ctrl = SpotubeController(
        libraryPath: cfg.libraryPath,
        coords: cfg.spotubeCoords,
      );
      final moved = await ctrl.moveDownloads();
      print('Moved $moved files');
      break;

    case 'spotube-cleanup':
      await _cleanupMp3(cfg.libraryPath);
      break;

    case 'podcast':
      final state = PipelineState();
      final pipeline = PodcastPipeline(
        onLog: (msg) => print(msg),
        onProgress: (c, t, s) {},
        state: state,
      );
      await pipeline.run();
      break;

    case 'status':
      print('''Library: ${cfg.libraryPath}
Playlists: ${cfg.urlNames.length}
Downloaded: ${cfg.lastUpdated.length}''');
      break;

    case 'favorite':
      await _favoriteCmd(args.sublist(1), cfg);
      break;
  }
}

Future<void> _favoriteCmd(List<String> args, AppConfig cfg) async {
  if (args.isEmpty || args[0] == 'list') {
    final favs = await FavoritesService.load();
    if (favs.isEmpty) {
      print('我的最愛 (Favorites): (空)');
      return;
    }
    print('我的最愛 (Favorites): ${favs.length} 首');
    final sorted = favs.toList()..sort();
    for (final f in sorted) {
      final name = File(f).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
      print('  ★ $name');
    }
    return;
  }

  final action = args[0];
  if (args.length < 2) {
    print('Usage: dart cli_main.dart favorite toggle <song>');
    return;
  }
  final song = await _resolveSong(cfg, args[1]);
  if (song == null) {
    print('找不到歌曲: ${args[1]}');
    return;
  }
  if (action == 'toggle') {
    final nowFav = await FavoritesService.toggle(song);
    print('${nowFav ? '★ 已加入' : '☆ 已移除'}我的最愛: ${File(song).uri.pathSegments.last}');
  } else if (action == 'add') {
    final favs = await FavoritesService.load();
    final key = FavoritesService.normalize(File(song).absolute.path);
    if (!favs.contains(key)) await FavoritesService.toggle(song);
    print('★ 已加入我的最愛: ${File(song).uri.pathSegments.last}');
  } else if (action == 'remove') {
    final favs = await FavoritesService.load();
    final key = FavoritesService.normalize(File(song).absolute.path);
    if (favs.contains(key)) await FavoritesService.toggle(song);
    print('☆ 已移除我的最愛: ${File(song).uri.pathSegments.last}');
  } else {
    print('未知操作: $action');
  }
}

Future<String?> _resolveSong(AppConfig cfg, String query) async {
  final q = query.trim();
  final direct = File(q);
  if (direct.existsSync()) return direct.absolute.path;
  if (File('$q.mp3').existsSync()) return File('$q.mp3').absolute.path;
  final lib = cfg.libraryPath;
  final lower = q.toLowerCase();
  await for (final e in Directory(lib).list(recursive: true, followLinks: false)) {
    if (e is File) {
      final low = e.path.toLowerCase();
      if (!(low.endsWith('.mp3') || low.endsWith('.m4a') || low.endsWith('.flac'))) continue;
      final stem = File(e.path).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
      if (stem.toLowerCase() == lower || File(e.path).uri.pathSegments.last.toLowerCase() == lower) {
        return e.path;
      }
    }
  }
  return null;
}

void main(List<String> args) async {
  try {
    await runCli(args);
    exit(0);
  } catch (e) {
    print('CLI fail: $e');
    exit(1);
  }
}

Future<void> _cleanupMp3(String libPath) async {
  final m4aDir = Directory('$libPath\\m4a');
  final mp3Dir = Directory('$libPath\\mp3');
  if (!await m4aDir.exists() || !await mp3Dir.exists()) {
    print('錯誤：找不到 mp3 或 m4a 目錄');
    return;
  }

  // Collect m4a stems
  final m4aStems = <String>{};
  await for (final f in m4aDir.list()) {
    if (f is File && f.path.toLowerCase().endsWith('.m4a')) {
      m4aStems.add(f.uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '').toLowerCase());
    }
  }
  print('M4A 檔案數: ${m4aStems.length}');

  // Find mp3 files whose stem doesn't match any m4a
  final orphans = <FileSystemEntity>[];
  await for (final f in mp3Dir.list()) {
    if (f is File && f.path.toLowerCase().endsWith('.mp3')) {
      final stem = f.uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '').toLowerCase();
      if (!m4aStems.contains(stem)) {
        orphans.add(f);
      }
    }
  }

  if (orphans.isEmpty) {
    print('✅ 沒有發現孤兒 MP3');
    return;
  }

  print('\n⚠️  找到 ${orphans.length} 個 metadata 更名版的孤兒 MP3：\n');
  int totalSize = 0;
  for (final f in orphans) {
    final stat = await f.stat();
    totalSize += stat.size;
    print('  ${f.uri.pathSegments.last}  (${(stat.size / 1024 / 1024).toStringAsFixed(1)} MB)');
  }
  print('\n  總計: ${(totalSize / 1024 / 1024).toStringAsFixed(1)} MB\n');

  stdout.write('是否刪除？(y/N): ');
  final input = (stdin.readLineSync() ?? '').trim().toLowerCase();
  if (input == 'y') {
    int deleted = 0;
    for (final f in orphans) {
      await (f as File).delete();
      deleted++;
    }
    print('✅ 已刪除 $deleted 個檔案');
  } else {
    print('跳過刪除');
  }
}

int _getFlag(List<String> args, String flag) {
  final idx = args.indexOf(flag);
  if (idx >= 0 && idx + 1 < args.length) {
    return int.tryParse(args[idx + 1]) ?? 0;
  }
  return 0;
}
