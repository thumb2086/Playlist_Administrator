# Playlist Administrator

![Version](https://img.shields.io/badge/version-1.6.0-blue)

Playlist Administrator is a Windows desktop tool for maintaining a local music library around Spotify playlists and Spotube downloads. It refreshes Spotify-derived `.m3u8` playlists, converts Spotube M4A files to MP3, tracks removed songs, exports playlists, and gives you quick statistics about the library.

The normal update flow does not download new audio from Spotify. It works with audio files already in your local library.

## Highlights

- Tkinter desktop UI with dark/light themes, settings, player, lyrics, progress, pause/stop controls, and a statistics tab.
- Spotify playlist/album/artist/track scraping through Spotify embed pages, with no Spotify API credentials required.
- M3U8 playlist generation with local file matching and missing-file pruning.
- Spotube M4A to MP3 conversion through FFmpeg, using metadata-based matching so renamed files are not treated as missing.
- Removed-song tracking into the fixed internal playlist `_Removed Songs.m3u8`.
- `_Unsorted.m3u8` generation for library tracks that are not referenced by user playlists.
- Playlist statistics that exclude internal files such as `_Removed Songs.m3u8`, `_Unsorted.m3u8`, and `_spotify_debug.txt`.
- USB/SD playlist export in copy or mirror mode.
- Optional LRC lyrics support and retroactive lyrics fetching.
- Session log files under the selected base folder.
- CLI commands for update, scraping, fetching playlist tracks, and testing matching.
- GitHub Actions release builds: push a tag like `v1.6.1` and the build injects version `1.6.1` into the app and installer.

## Library Layout

Choose a Base Folder in settings. A typical library looks like this:

```text
Base Folder/
  Music/
    mp3/
    m4a/
    ...
  playlists/
    Daily Mix 1.m3u8
    _Removed Songs.m3u8
    _Unsorted.m3u8
  config.json
  logs/
  USB_Output/
```

The app derives `Music`, `playlists`, `USB_Output`, and other working paths from `base_path`.

## Quick Start

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Run the desktop UI:

   ```bash
   python main.py
   ```

3. Open settings and choose your Base Folder.

4. Add Spotify URLs in the Library tab, then run the update flow.

## Desktop Workflow

The main update flow does the following:

1. Scans the local music library and unblocks Windows downloaded files when needed.
2. Converts Spotube M4A files to MP3 if FFmpeg is available.
3. Scrapes configured Spotify URLs and rebuilds matching `.m3u8` playlists.
4. Records songs removed from Spotify playlists into `_Removed Songs.m3u8`.
5. Prunes playlist entries that point to missing local files.
6. Creates or updates `_Unsorted.m3u8` for local tracks not used by playlists.
7. Refreshes statistics using metadata-aware MP3/M4A matching.

## Settings

Important settings include:

- `base_path`: Library root. Other paths are derived from it.
- `language`: `zh-TW` or `en`.
- `theme`: `dark` or `light`.
- `ffmpeg_path`: FFmpeg executable path, used for M4A to MP3 conversion.
- `spotube_folder_name`: Spotube folder name under the library.
- `spotube_convert_matched_only`: Convert only M4A files that match playlist entries.
- `spotube_strict_matching`: Legacy matching option retained for compatibility.
- `enable_retroactive_lyrics`: Fetch missing lyrics for existing songs.
- `lyrics_folder_name`: Folder used for `.lrc` lyrics.
- `auto_update_check`: Check GitHub Releases on startup.
- `debug_mode`: Enables detailed timing and debug logs.

Configuration is stored in:

- `%LOCALAPPDATA%\Playlist Administrator\data\config.json`
- `Base Folder\config.json` when `base_path` is set

The app-data config keeps the pointer to `base_path`; the base-folder config becomes the primary working config.

## CLI Usage

All commands accept `--config path/to/config.json`.

### `update`

Run the main update flow.

```bash
python cli.py update
python cli.py update --config path/to/config.json
python cli.py update --force
python cli.py update --progress
```

### `scrape`

Scrape Spotify URLs and rebuild playlist files.

```bash
python cli.py scrape
python cli.py scrape --url "https://open.spotify.com/playlist/..."
python cli.py scrape --url "https://open.spotify.com/playlist/..." --force
```

### `fetch-playlist`

Inspect Spotify embed results without running the full update flow.

```bash
python cli.py fetch-playlist "https://open.spotify.com/playlist/..."
python cli.py fetch-playlist "https://open.spotify.com/playlist/..." --show-tracks
python cli.py fetch-playlist "https://open.spotify.com/playlist/..." --output tracks.txt
```

### `match`

Test local library matching against `_spotify_debug.txt` or another track list.

```bash
python cli.py match
python cli.py match --file "tracks.txt"
python cli.py match --no-prefer-mp3
python cli.py match --verbose
python cli.py match --fail-on-missing
```

## Release Builds

GitHub Actions builds a Windows installer when a version tag is pushed.

```bash
git tag v1.6.1
git push origin v1.6.1
```

The workflow:

- validates tags such as `v1.6.1`
- injects `1.6.1` into `utils/version.py` for the build
- updates README badges inside the build workspace
- passes `1.6.1` to Inno Setup as `AppVersion`
- creates a GitHub Release named `Playlist Administrator v1.6.1`

`utils/version.py` is kept as the baseline major/minor version in source, for example `1.6.0` or `1.7.0`. Patch releases are handled by the tag during CI.

## Project Structure

- `main.py`: Tkinter entry point.
- `cli.py`: Command-line interface.
- `core/library.py`: Main update flow, conversion, playlist pruning, export, statistics, and matching.
- `core/spotify.py`: Spotify embed scraping and playlist writing.
- `core/snapshot_manager.py`: Removed-song snapshot tracking.
- `core/audio_converter.py`: Audio conversion helpers.
- `core/ffmpeg_installer.py`: FFmpeg discovery/installation helpers.
- `gui/app.py`: Main desktop UI.
- `gui/settings.py`: Settings window.
- `gui/update_dialog.py`: Update notification dialog.
- `utils/config.py`: Config loading, path derivation, debug/timing helpers.
- `utils/version.py`: Baseline app version and release metadata.
- `utils/logger.py`: Session file logging.
- `installer/PlaylistAdministrator.iss`: Inno Setup installer script.
- `docs/` and `Docs_ZH/`: Architecture and maintenance notes.
- `tools/`: Utility scripts.

## Notes

- Spotify scraping depends on Spotify embed pages and may break if Spotify changes its page structure.
- FFmpeg is required for M4A to MP3 conversion.
- Internal playlists such as `_Removed Songs.m3u8` and `_Unsorted.m3u8` are intentionally excluded from user playlist statistics.
- The desktop UI is the primary supported interface. The CLI is mainly for automation and diagnostics.
