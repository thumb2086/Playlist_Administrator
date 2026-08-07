#!/usr/bin/env node
import { loadConfig } from './lib/config.js';
import { PipelineOrchestrator } from './lib/pipeline.js';
import { PodcastPipeline } from './lib/podcast.js';
import { SpotubeController } from './lib/spotube.js';
import { cleanupMp3 } from './lib/cleanup.js';

const HELP = `Playlist Administrator CLI (Node)

Usage:
  playlist-admin pipeline                   Run full pipeline
  playlist-admin pipeline --step N          Run single step
  playlist-admin spotube-download <name>    Download one playlist
  playlist-admin spotube-download-all       Download all playlists
  playlist-admin spotube-move               Move M4A files
  playlist-admin spotube-cleanup            Remove metadata-renamed mp3 duplicates
  playlist-admin podcast                    Run podcast pipeline
  playlist-admin status                     Show status
`;

function getFlag(args, flag) {
  const idx = args.indexOf(flag);
  if (idx >= 0 && idx + 1 < args.length) {
    return parseInt(args[idx + 1], 10) || 0;
  }
  return 0;
}

const onProgress = () => {};
const isCancelled = () => false;

async function main() {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.log(HELP);
    return;
  }

  const config = loadConfig();
  const cmd = args[0];

  switch (cmd) {
    case 'pipeline': {
      const fromStep = getFlag(args, '--step');
      const orch = new PipelineOrchestrator({ config, onLog: (m) => console.log(m), onProgress, isCancelled });
      await orch.run({ fromStep });
      break;
    }

    case 'spotube-download': {
      if (args.length < 2) {
        console.log('Usage: playlist-admin spotube-download <playlist_name>');
        return;
      }
      const ctrl = new SpotubeController({
        libraryPath: config.libraryPath,
        coords: config.spotubeCoords,
      });
      if (!(await ctrl.isRunning())) {
        console.log('Spotube is not running');
        return;
      }
      await ctrl.downloadPlaylist(args[1]);
      break;
    }

    case 'spotube-download-all': {
      const ctrl = new SpotubeController({
        libraryPath: config.libraryPath,
        coords: config.spotubeCoords,
      });
      if (!(await ctrl.isRunning())) {
        console.log('Spotube is not running');
        return;
      }
      const names = Object.values(config.urlNames);
      for (const name of names) {
        console.log(`Downloading: ${name}`);
        await ctrl.downloadPlaylist(name);
      }
      break;
    }

    case 'spotube-move': {
      const ctrl = new SpotubeController({ libraryPath: config.libraryPath });
      const moved = await ctrl.moveDownloads(config.resolvedSpotubeDownloadPath);
      console.log(`Moved ${moved} files`);
      break;
    }

    case 'spotube-cleanup': {
      await cleanupMp3(config.libraryPath);
      break;
    }

    case 'podcast': {
      const pipeline = new PodcastPipeline({ config, onLog: (m) => console.log(m), isCancelled });
      await pipeline.run();
      break;
    }

    case 'status': {
      console.log(`Library: ${config.libraryPath}`);
      console.log(`Playlists: ${Object.keys(config.urlNames).length}`);
      console.log(`Downloaded: ${Object.keys(config.lastUpdated || {}).length}`);
      break;
    }

    default:
      console.log(`Unknown command: ${cmd}\n`);
      console.log(HELP);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
