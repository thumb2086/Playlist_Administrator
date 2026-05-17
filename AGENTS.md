# Playlist Administrator — Agent Guide

## Run
```bash
pip install -r requirements.txt
python main.py        # Tkinter GUI
python cli.py --help  # CLI (update, scrape, match, fetch-playlist)
```

## No tests, no linter, no typechecking
This repo has zero test files, no pytest setup, no formatter, and no type checker. Do not look for or expect any.

## Spotify: no API credentials needed
Scraping uses Spotify embed pages (`open.spotify.com/embed/...`), no API token required.

## Config system
Two-tier: `%LOCALAPPDATA%\Playlist Administrator\data\config.json` holds `base_path` pointer. The real working config lives at `{base_path}/config.json`. All other paths (`library_path`, `playlists_path`, `export_path`) are derived from `base_path` in `utils/config.py:derive_paths()`.

## Common CLI patterns
- `--config path/to/config.json` works on every subcommand
- `--force` ignores `last_updated` timestamps (forces a full scrape)
- `--progress` on `update` prints progress callbacks
- `cli.py` auto-bootstraps `.venv\Lib\site-packages` so it runs from a bundled Python too

## Internal playlists (underscore-prefixed, excluded from stats)
- `_Removed Songs.m3u8` — tracks removed from Spotify playlists
- `_Unsorted.m3u8` — local files not referenced by any playlist
- `_spotify_debug.txt` — raw scrape output used by `match` command

## M3U8 path style
Raw forward-slash paths, no URI encoding (v1.5.2+). Relevant for Echo Nightly and mobile players.

## FFmpeg
Optional for M4A→MP3 conversion. Config key: `ffmpeg_path` (default `bin/ffmpeg.exe`).

## Version & releases
- Source: `utils/version.py` (`__version__ = "1.6.0"`)
- CI release: push `v1.6.1` tag → workflow injects version, builds PyInstaller EXE + Inno Setup installer
- Build: `pyinstaller --onefile --windowed --name "PlaylistAdministrator" --add-data "core;core" --add-data "gui;gui" --add-data "utils;utils" --collect-all zhconv main.py`
- Also: `pyinstaller app.spec` (local `.spec` file alternative)
- Installer: `installer/PlaylistAdministrator.iss` (Inno Setup, expects `dist/PlaylistAdministrator.exe`)

## i18n
`zhconv` handles Traditional/Simplified Chinese normalization. Config key `language`: `zh-TW` or `en`.

## Python
CI uses 3.11. Minimum is 3.7+. Windows-only (Tkinter + Windows path assumptions).

## Debug mode
Set `"debug_mode": true` in config. Enables `utils/config.py` timing/debug_print helpers.
