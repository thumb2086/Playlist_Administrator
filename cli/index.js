#!/usr/bin/env node
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

// Thin launcher: the CLI engine lives in the Flutter app binary
// (lib/cli_main.dart), so GUI and CLI share one implementation.
// This script just locates the built exe / rag scripts and forwards args.

const HELP = `playlist-admin CLI

  Runs the same engine as the GUI app (shared Dart code). Requires a built
  release: flutter build windows --release

Usage:
  playlist-admin pipeline [--step N]     Run full pipeline (or from step N)
  playlist-admin podcast                 Run podcast pipeline
  playlist-admin status                  Show status
  playlist-admin spotube-download <name> Download one playlist
  playlist-admin spotube-download-all    Download all playlists
  playlist-admin spotube-move            Move M4A files
  playlist-admin spotube-cleanup         Remove metadata-renamed mp3 duplicates
  playlist-admin favorite list           List favorite songs
  playlist-admin favorite toggle <song>  Toggle favorite (我的最愛)
  playlist-admin rag build [--reset]     Build podcast RAG vector DB
  playlist-admin rag query "問題" [--topk N] [--show 節目] [--json]
`;

function projectRoot() {
  if (process.env.PA_ROOT && fs.existsSync(process.env.PA_ROOT)) {
    return process.env.PA_ROOT;
  }
  // Start from cwd and walk up to find the Flutter project (works whether
  // invoked locally or from a globally installed npm package).
  let dir = process.cwd();
  while (true) {
    if (fs.existsSync(path.join(dir, 'pubspec.yaml'))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) return null;
    dir = parent;
  }
}

function exePath(root) {
  const candidates = [
    path.join(root, 'build', 'windows', 'x64', 'runner', 'Release', 'playlist-admin.exe'),
    path.join(root, 'build', 'windows', 'x64', 'runner', 'Debug', 'playlist-admin.exe'),
    path.join(root, 'build', 'windows', 'x64', 'runner', 'Release', 'playlist_administrator.exe'),
  ];
  return candidates.find((c) => fs.existsSync(c)) || null;
}

function python() {
  return process.env.PYTHON || 'python';
}

function forward(exe, args) {
  // Deliver CLI args via PA_CLI_ARGS (JSON) — Flutter Dart exposes no
  // command-line args in release on this SDK (see lib/main.dart).
  // PA_ROOT lets the Python bridge find rag/ scripts when invoked from the CLI.
  const root = projectRoot();
  const child = spawn(exe, [], {
    stdio: 'inherit',
    windowsHide: false,
    env: {
      ...process.env,
      PA_CLI_ARGS: JSON.stringify(args),
      ...(root ? { PA_ROOT: root } : {}),
    },
  });
  child.on('exit', (code) => process.exit(code ?? 1));
  child.on('error', (e) => {
    console.error(`無法啟動 ${exe}: ${e.message}`);
    process.exit(1);
  });
}

function forwardPy(args) {
  // Python scripts take real argv.
  const child = spawn(python(), args, { stdio: 'inherit', windowsHide: false });
  child.on('exit', (code) => process.exit(code ?? 1));
  child.on('error', (e) => {
    console.error(`無法啟動 python: ${e.message}`);
    process.exit(1);
  });
}

function runRag(args) {
  const root = projectRoot();
  if (!root) {
    console.error('找不到專案根目錄（pubspec.yaml）。請在專案內執行，或設定 PA_ROOT');
    process.exit(1);
  }
  const sub = args[0];
  const script = path.join(root, 'rag', sub === 'build' ? 'build_db.py' : 'query.py');
  if (!fs.existsSync(script)) {
    console.error(`找不到 ${script}`);
    process.exit(1);
  }
  forwardPy([script, ...args.slice(1)]);
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.log(HELP);
    return;
  }
  if (args[0] === 'rag') {
    runRag(args.slice(1));
    return;
  }

  const root = projectRoot();
  if (!root) {
    console.error('找不到專案根目錄（pubspec.yaml）。請在專案內執行，或設定 PA_ROOT');
    process.exit(1);
  }
  const exe = exePath(root);
  if (!exe) {
    console.error(`找不到 build 好的 exe。
請先在專案內執行: flutter build windows --release
或設定 PA_ROOT=<專案根目錄>`);
    process.exit(1);
  }
  forward(exe, args);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
