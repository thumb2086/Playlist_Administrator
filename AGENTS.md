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

## Flutter (v2.0.0+)
The project is being migrated to Flutter/Dart. Source files in `lib/`.

### Setup
```bash
flutter pub get
flutter run       # development
flutter build windows  # release
```

### Structure
- `lib/models/` — Data classes
- `lib/services/` — Business logic (config, scraper, converter, metadata, win32)
- `lib/pipeline/` — PipelineOrchestrator + steps
- `lib/pages/` — UI pages
- `lib/widgets/` — Reusable widgets, theme

### Key dependencies
- `win32` — Windows API (Spotube automation)
- `http` + `html` — Spotify scraping
- `fl_chart` — Statistics charts
- `path_provider` — Data directory resolution

### Assets
- `assets/zhcdict.json` — Chinese converter dictionary (copied from Python zhconv)
- `assets/artist_aliases.json` — Artist name aliases

## Pipeline (v1.7.0+)
New orchestrated pipeline replaces the old monolithic `update_library_logic`.

### Architecture
- `core/pipeline.py` — `PipelineState`, `PipelineStep` (ABC), `PipelineOrchestrator`
- `core/steps/` — each step in its own file:
  - `step_convert.py` — M4A→MP3 conversion (fixed O(N²) bottleneck, batch processing, killable workers)
  - `step_scrape.py` — Spotify scraping via embed API
  - `step_prune.py` — Remove missing tracks from playlists
  - `step_unsorted.py` — Organize orphaned audio files
  - `step_metadata.py` — Optional metadata enrichment

### CLI usage
```bash
python cli.py pipeline              # Full pipeline
python cli.py pipeline --step 0     # Single step (0=convert, 1=scrape, ...)
python cli.py pipeline --from-step 1 # Resume from step 1
python cli.py pipeline --list-steps  # Show step list
python cli.py pipeline --force       # Force re-scrape
python cli.py pipeline --progress    # Show progress
```

### GUI
The "Update All" button now runs `PipelineOrchestrator` instead of `update_library_logic`.

### Cancel behaviour
- Each step checks `state.stop_event` between batches.
- Worker subprocess PIDs are tracked for fast kill on cancel.
- `state.pause_event` pauses between batch items (not mid-ffmpeg).

## Debug mode
Set `"debug_mode": true` in config. Enables `utils/config.py` timing/debug_print helpers.

## Spotube CLI automation (new in v1.7.0)
Four commands were added to automate downloading playlists via Spotube's GUI:

| Command | Description |
|---------|-------------|
| `spotube-download <name>` | Download one playlist by name (matched against `url_names`) |
| `spotube-download-all` | Download every playlist in `url_names` sequentially |
| `spotube-status` | Show Spotube window info, m4a file count, configured playlists |
| `spotube-move` | Move files from `Downloads/Spotube/` into `{library_path}/m4a/` |

### Architecture
- `core/spotube_controller.py` — `SpotubeController` class: window management (find, activate, click via `pyautogui`), full `download_playlist()` workflow
- `core/spotube_file_handler.py` — `move_spotube_downloads()`: copies newly downloaded M4A files to the library m4a folder

### Background operation
`SpotubeController._activate()` saves the current foreground window, brings Spotube to front, performs clicks, then `_restore_previous()` puts the original window back. The whole automation sequence takes ~5-10 seconds per playlist.

### Configuration
New config keys (all optional, with built-in defaults):
- `"spotube_exe_path"` — absolute path to `Spotube.exe` (auto-detected if empty)
- `"spotube_download_path"` — where Spotube saves downloads (default `~/Downloads/Spotube`)
- `"spotube_coords"` — dict of UI coordinate overrides for 1920×1080 maximized:
  ```json
  {"sidebar_search": [30, 230], "sidebar_library": [30, 280],
   "library_filter": [200, 100], "first_playlist_card": [100, 240],
   "three_dot_menu": [1300, 140], "download_all_offset": [-30, 30],
   "confirm_button": [960, 600]}
  ```
  Tune these if the defaults don't match your screen.

### Dependencies added
`pyautogui`, `Pillow`, `pygetwindow`, `pywin32` (see `requirements.txt`).
