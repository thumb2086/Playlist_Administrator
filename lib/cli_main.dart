import 'services/config_service.dart';
import 'services/spotube_controller.dart';
import 'pipeline/pipeline_orchestrator.dart';
import 'models/pipeline_step.dart';

void main(List<String> args) async {
  await ConfigService.instance.load();
  final cfg = ConfigService.instance.config;

  if (args.isEmpty) {
    print('''Playlist Administrator CLI
Usage:
  dart cli_main.dart pipeline                   Run full pipeline
  dart cli_main.dart pipeline --step N          Run single step
  dart cli_main.dart spotube-download <name>    Download one playlist
  dart cli_main.dart spotube-download-all       Download all playlists
  dart cli_main.dart spotube-move               Move M4A files
  dart cli_main.dart status                     Show status
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

    case 'status':
      print('''Library: ${cfg.libraryPath}
Playlists: ${cfg.urlNames.length}
Downloaded: ${cfg.lastUpdated.length}''');
      break;
  }
}

int _getFlag(List<String> args, String flag) {
  final idx = args.indexOf(flag);
  if (idx >= 0 && idx + 1 < args.length) {
    return int.tryParse(args[idx + 1]) ?? 0;
  }
  return 0;
}
