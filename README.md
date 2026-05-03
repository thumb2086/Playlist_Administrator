# Playlist Administrator

![Version](https://img.shields.io/badge/version-1.6.0-blue)

Library maintenance for local music libraries: build/update Spotify playlists, manage exports, and organize music. Default workflow does not download audio.

## What It Does

- Build and refresh `.m3u8` playlists from Spotify playlist/album/artist/track URLs via the embed page (no authentication required).
- Remove missing entries from playlists.
- Move unsorted tracks to `_Unsorted` when needed.
- Export selected playlists to USB/SD in Copy or Mirror mode.
- Tkinter desktop UI with a built-in player and lyrics (`.lrc`).
- Command-line interface for automation.

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the desktop UI:
   ```bash
   python main.py
   ```
3. Set your Base Folder (library root). It should contain:
   - `Music/` - Your audio files (MP3, FLAC, etc.)
   - `Playlists/` - Playlist files (.m3u8)
4. Add Spotify URLs, then click Start/Update.

## CLI Usage

### `update`
Run the full update flow: scrape Spotify URLs, rebuild playlist files, and prune missing tracks.

```bash
python cli.py update
python cli.py update --config path/to/config.json
python cli.py update --force          # Ignore last_updated cache
python cli.py update --progress       # Print progress callbacks
```

### `scrape`
Scrape Spotify and rebuild playlist files without a full library update.

```bash
python cli.py scrape
python cli.py scrape --url "https://open.spotify.com/playlist/..."
python cli.py scrape --url "https://open.spotify.com/playlist/..." --url "https://open.spotify.com/album/..."
python cli.py scrape --force          # Ignore last_updated cache for selected URLs
```

### `fetch-playlist`
Fetch playlist tracks via the embed page and optionally save them to a debug file.

```bash
python cli.py fetch-playlist "https://open.spotify.com/playlist/..."
python cli.py fetch-playlist "https://open.spotify.com/playlist/..." --show-tracks
python cli.py fetch-playlist "https://open.spotify.com/playlist/..." --output tracks.txt
```

### `match`
Test local track matching: reads a track list from `_spotify_debug.txt` (or a specified file) and searches your library for each track.

```bash
python cli.py match
python cli.py match --file "My Playlist Tracks.txt"
python cli.py match --prefer-mp3      # Default: search MP3 files first (default: true)
python cli.py match --no-prefer-mp3  # Search all audio formats equally
python cli.py match --verbose         # Print every matched path
python cli.py match --fail-on-missing # Exit with code 1 when any track is missing
```

## Config Override

All commands accept `--config path/to/config.json` to override the default config location. When a config path is provided:

- `base_path` defaults to the directory containing the config file.
- The config is loaded from the specified file and used for all operations.

```bash
python cli.py update --config ./my-library/config.json
```

## Install (EXE)

GitHub Actions builds a Windows installer automatically. Download the latest release installer from the GitHub Releases page and run it to install.

## Configuration

Config is stored under the user profile and optionally in the base folder:

- Primary app config: `%LOCALAPPDATA%\Playlist Administrator\data\config.json`
- If `base_path` is set, a `config.json` is also stored in the base folder and becomes the primary settings source. The app data config keeps a pointer to `base_path`.

Key settings:

- `base_path`: Library root. `Music`, `Playlists`, and `USB_Output` are derived from it.
- `ffmpeg_path`: Path to `ffmpeg` (optional, for audio conversion).
- `spotube_folder_name`: Spotube folder name under the library (optional).
- `spotube_exact_match`: Use simple filename matching for Spotube downloads (default: True).

## Project Structure

- `main.py`: Tkinter entry point.
- `cli.py`: Command-line interface.
- `core/`: Core logic (playlist build/prune, scraping, sync/export, metadata helpers).
- `gui/`: Tkinter UI and settings.
- `utils/`: Config, helpers, i18n.
- `tools/`: Utility scripts.
- `docs/`: Documentation.
- `PLAYBACK_FIX_README.md`: Windows Media Player playback issue fix.
- `YTDLP_UPDATE_GUIDE.md`: yt-dlp update steps.

## Notes

- Spotify scraping relies on the embed page and requires network access. No authentication needed.
- Playlists use MP3 files by default.
- Download utilities (yt-dlp, DAB, spotDL) exist in `core/downloader.py` but are not used by the default update flow.
- Tkinter is the only supported UI entrypoint.
