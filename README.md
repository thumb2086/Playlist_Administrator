# Playlist Administrator

Lightweight library maintenance for Spotube users: convert M4A to MP3, classify tracks, and build Spotify playlists without downloading audio.

## Latest Usage (Spotube M4A -> MP3 / Playlists)

- Base Folder: `C:\Users\CPXru\Music\Spotube`
- Convert: `Spotube\*.m4a` -> `Spotube\mp3\*.mp3`
- Playlists: build `.m3u8` under `Spotube\Playlists\` and remove missing files
- No download. Only convert, classify, and update playlists.

### Key Settings

`data/config.json` (or GUI/Streamlit settings)
- `spotube_folder_name`: `""` (use base folder directly)
- `spotube_mp3_subfolder`: `mp3`
- `spotube_convert_workers`: conversion threads (suggest 6-8)
- `prefer_mp3_playlists`: `true` (prefer MP3 in playlists)

### Folder Structure (after run)

```
C:\Users\CPXru\Music\Spotube\
  config.json
  *.m4a
  mp3\
    *.mp3
  Playlists\
    *.m3u8
  _Unsorted\        (only if needed)
  USB_Output\       (only if export is used)
```

### Buttons

- Start/Update: run conversion + playlist update
- Pause: pause and resume safely
- Cancel: stop at the next safe checkpoint (current ffmpeg job finishes)

### Requirements

- `ffmpeg` must be available or M4A -> MP3 will be skipped.

## Run

Streamlit UI:
```bash
streamlit run streamlit_app.py
```

Tkinter UI:
```bash
python main.py
```
