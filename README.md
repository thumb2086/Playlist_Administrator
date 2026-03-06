# Playlist Administrator (Streamlit GUI)

An automation tool to organize your music library and export playlists into USB-ready folders.

## What's New

- Download engine is now **spotDL standalone executable** (called via `subprocess`, not imported as a Python package).
- Better metadata output (album/artist/cover) from Spotify-based downloads.
- Existing smart matching is kept to avoid duplicate downloads.
- Legacy downloader remains as fallback when a Spotify track URL is unavailable.

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```
2. Create local binary folder:
```bash
mkdir -p bin
```
3. Download `spotdl` standalone executable from:
   - https://github.com/spotDL/spotify-downloader/releases
4. Download `ffmpeg` executable from the official FFmpeg website:
   - https://ffmpeg.org/download.html
5. Put binaries into `bin/`:
   - Windows: `bin/spotdl.exe`, `bin/ffmpeg.exe`
   - Linux/macOS: `bin/spotdl`, `bin/ffmpeg`

## Run

Streamlit UI:
```bash
streamlit run streamlit_app.py
```

Tkinter UI (legacy):
```bash
python main.py
```

## GUI Settings (spotDL)

In `⚙️ 系統設定 -> 一般 & 路徑`, configure:
- `spotdl 路徑` (default `bin/spotdl.exe`)
- `ffmpeg 路徑` (default `bin/ffmpeg.exe`)
- `格式` (`mp3`, `m4a`, `opus`)
- `強制覆蓋` (`False` = skip existing, `True` = force)
- `Bitrate` (optional, e.g. `320k`)
- `spotDL Timeout` (default `600`)
- `輸出模板` (optional; empty uses `Music/{artist}/{album}/{title}.{output-ext}`)

## Download Flow

1. Scrape Spotify playlist/album/artist/track metadata.
2. Build local library index and detect missing tracks.
3. For missing tracks:
   - Use spotDL when Spotify track URL is available.
   - Fallback to legacy downloader when needed.
4. Update playlist status and sync/export as usual.

## Folder Structure

- `Music/`: master local music library.
- `Playlists/`: `.m3u8` / `.m3u` / `.txt` playlist files.
- `USB_Output/`: export target folder.
- `bin/`: local standalone binaries (`spotdl`, `ffmpeg`) - ignored by git.

## Cloud Build (GitHub Actions + PyInstaller)

Workflow:
- `.github/workflows/build.yml`
- Trigger: push tag `v*`
- Jobs: `build-windows` + `build-linux`
- Python: `3.12`
- Build command:
  - Windows: `pyinstaller --noconfirm --onefile --windowed --name PlaylistAdministrator --add-binary "bin/*;bin" streamlit_app.py`
  - Linux: `pyinstaller --noconfirm --onefile --windowed --name PlaylistAdministrator --add-binary "bin/*:bin" streamlit_app.py`
- Artifacts are uploaded and attached to GitHub Release via `softprops/action-gh-release`.

## Test Checklist

1. Small playlist smoke test
   - Add a small Spotify playlist (3-5 tracks), run update, confirm files are downloaded.
2. Metadata verification
   - Open output files and verify title/artist/album/cover are embedded.
3. No re-download
   - Run update again and confirm existing tracks are skipped.
4. Fallback behavior
   - Test a track without URL mapping and verify fallback downloader still works.
5. Error handling
   - Set invalid `spotdl_path` once, confirm task logs failure and continues with next tracks.
6. Export verification
   - Export selected playlists and verify `USB_Output/` has expected files and structure.
