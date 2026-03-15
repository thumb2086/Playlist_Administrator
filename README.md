# Playlist Administrator

Library maintenance for Spotube and local music libraries: convert M4A to MP3, build/update Spotify playlists, and manage exports. Default workflow does not download audio.

## What It Does

- Convert Spotube M4A to MP3 into a dedicated `mp3` subfolder (multi-threaded).
- Build and refresh `.m3u8` playlists from Spotify playlist/album/artist/track URLs via the embed page.
- Remove missing entries from playlists.
- Move unsorted tracks to `_Unsorted` when needed.
- Export selected playlists to USB/SD in Copy or Mirror mode.
- Tkinter desktop UI with a built-in player and lyrics (`.lrc`).
- Streamlit UI with dashboard and settings.

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the UI:
   ```bash
   python main.py
   ```
   Or:
   ```bash
   streamlit run streamlit_app.py
   ```
3. Set your Base Folder (library root). It can be:
   - A folder that already contains `Music` and `Playlists`, or
   - A Spotube folder that contains `.m4a` files directly.
4. Add Spotify URLs, then click Start/Update.

## Install (EXE)

GitHub Actions builds a Windows installer automatically. Download the latest release installer from the GitHub Releases page and run it to install.

## Configuration

Config is stored under the user profile and optionally in the base folder:

- Primary app config: `%LOCALAPPDATA%\Playlist Administrator\data\config.json`
- If `base_path` is set, a `config.json` is also stored in the base folder and becomes the primary settings source. The app data config keeps a pointer to `base_path`.

Key settings:

- `base_path`: Library root. `Music`, `Playlists`, and `USB_Output` are derived from it.
- `ffmpeg_path`: Path to `ffmpeg` for M4A to MP3 conversion.
- `spotube_folder_name`: Spotube folder name under the library. Set to `""` to use the base folder directly.
- `spotube_mp3_subfolder`: Output folder name for MP3s (default `mp3`).
- `spotube_convert_workers`: Conversion worker count (default 4).
- `prefer_mp3_playlists`: Prefer MP3 when building playlists.

## Project Structure

- `main.py`: Tkinter entry point.
- `streamlit_app.py`: Streamlit UI.
- `core/`: Core logic (playlist build/prune, conversion, scraping, sync/export, metadata helpers).
- `gui/`: Tkinter UI and settings.
- `utils/`: Config, helpers, i18n.
- `tools/`: Utility scripts.
- `Docs_ZH/`: Additional Chinese docs.
- `PLAYBACK_FIX_README.md`: Windows Media Player playback issue fix.
- `YTDLP_UPDATE_GUIDE.md`: yt-dlp update steps.

## Notes

- `ffmpeg` is required for M4A to MP3 conversion. If missing, conversion is skipped.
- Spotify scraping relies on the embed page and requires network access.
- Download utilities (yt-dlp, DAB, spotDL) exist in `core/downloader.py` but are not used by the default update flow.
