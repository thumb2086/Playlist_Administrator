import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

export function appDataDir() {
  return path.join(
    process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'),
    'Playlist Administrator',
    'data',
  );
}

export function loadConfig() {
  // 1. Pointer file: LOCALAPPDATA\Playlist Administrator\data\config.json
  const pointerFile = path.join(appDataDir(), 'config.json');
  let basePath = '';
  if (fs.existsSync(pointerFile)) {
    try {
      const data = JSON.parse(fs.readFileSync(pointerFile, 'utf-8'));
      basePath = data.base_path || '';
    } catch {}
  }

  // 2. Main config: <base_path>\config.json
  const mainFile = basePath ? path.join(basePath, 'config.json') : '';
  const cfg = {};
  if (mainFile && fs.existsSync(mainFile)) {
    try {
      Object.assign(cfg, JSON.parse(fs.readFileSync(mainFile, 'utf-8')));
    } catch {}
  } else if (fs.existsSync(pointerFile)) {
    try {
      Object.assign(cfg, JSON.parse(fs.readFileSync(pointerFile, 'utf-8')));
    } catch {}
  }

  cfg.base_path = cfg.base_path || basePath;

  const config = {
    basePath: cfg.base_path || '',
    language: cfg.language || 'zh-TW',
    audioFormat: cfg.audio_format || 'mp3',
    maxThreads: cfg.max_threads || 4,
    debugMode: !!cfg.debug_mode,
    enableMetadataEnrichment: !!cfg.enable_metadata_enrichment,
    spotubeExactMatch: cfg.spotube_exact_match !== false,
    spotubeConvertMatchedOnly: !!cfg.spotube_convert_matched_only,
    ffmpegPath: cfg.ffmpeg_path || 'bin/ffmpeg.exe',
    spotubeExePath: cfg.spotube_exe_path || '',
    spotubeDownloadPath: cfg.spotube_download_path || '',
    spotubeFolderName: cfg.spotube_folder_name || 'spotube',
    lyricsFolderName: cfg.lyrics_folder_name || 'Lyrics',
    autoUpdateCheck: cfg.auto_update_check !== false,
    autoDownloadUpdate: !!cfg.auto_download_update,
    enableRetroactiveLyrics: !!cfg.enable_retroactive_lyrics,
    theme: cfg.theme || 'dark',
    skippedVersion: cfg.skipped_version || '',
    setupCompleted: !!cfg.setup_completed,
    groqApiKey: cfg.groq_api_key || '',
    groqConcurrency: cfg.groq_concurrency || 3,
    podcastSubscriptions: cfg.podcast_subscriptions || {},
    podcastHistory: cfg.podcast_history || {},
    urlNames: cfg.url_names || {},
    searchNames: cfg.search_names || {},
    spotubeCoords: cfg.spotube_coords || {},
    lastUpdated: cfg.last_updated || {},
    lyricsOffsets: cfg.lyrics_offsets || {},
  };

  if (config.basePath) derivePaths(config);
  return config;
}

export function saveConfig(config) {
  if (!config.basePath) return;
  const path_ = path.join(config.basePath, 'config.json');
  const lock = `${path_}.lock`;
  // File lock to prevent concurrent writes (wait up to ~10s)
  for (let i = 0; i < 100 && fs.existsSync(lock); i++) {
    sleepSync(100);
  }
  if (fs.existsSync(lock)) {
    try { fs.unlinkSync(lock); } catch {}
  }
  try {
    fs.writeFileSync(lock, '');
    const json = {};
    for (const [k, v] of Object.entries(config)) {
      json[k] = v;
    }
    json.spotify_urls = Object.keys(config.urlNames);
    fs.writeFileSync(path_, JSON.stringify(json, null, 2), 'utf-8');
  } finally {
    try { fs.unlinkSync(lock); } catch {}
  }
  // Update pointer file
  const dir = appDataDir();
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(
    path.join(dir, 'config.json'),
    JSON.stringify({ base_path: config.basePath, language: config.language }),
    'utf-8',
  );
}

function sleepSync(ms) {
  const sw = Date.now();
  while (Date.now() - sw < ms) { /* spin */ }
}

function derivePaths(config) {
  const base = path.normalize(config.basePath);
  const music = path.join(base, 'Music');
  config.libraryPath = fs.existsSync(music) ? music : base;
  config.playlistsPath = path.join(base, 'Playlists');
  config.exportPath = path.join(base, 'USB_Output');
  config.lyricsPath = path.join(config.libraryPath, config.lyricsFolderName);

  const m4a = path.join(config.libraryPath, 'm4a');
  if (!fs.existsSync(m4a) && fs.existsSync(path.join(base, 'm4a'))) {
    config.m4aPath = path.join(base, 'm4a');
  } else {
    config.m4aPath = m4a;
  }
  const mp3 = path.join(config.libraryPath, 'mp3');
  if (!fs.existsSync(mp3) && fs.existsSync(path.join(base, 'mp3'))) {
    config.mp3Path = path.join(base, 'mp3');
  } else {
    config.mp3Path = mp3;
  }

  if (config.spotubeDownloadPath && config.spotubeDownloadPath.trim()) {
    config.resolvedSpotubeDownloadPath = config.spotubeDownloadPath;
  } else {
    const folder = config.spotubeFolderName || 'spotube';
    config.resolvedSpotubeDownloadPath = path.join(os.homedir(), 'Downloads', folder);
  }
}
