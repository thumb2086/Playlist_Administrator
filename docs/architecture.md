# Architecture Documentation

## Overview

Playlist Administrator is a desktop-first music library management tool that builds and updates Spotify playlists from local audio files. It uses Spotify's embed page for scraping, requires no Spotify authentication, and treats the Tkinter desktop app as the primary UI.

## Entry Points

- `main.py`: Tkinter desktop entry point
- `cli.py`: Command-line entry point for automation and debugging

## Core Components

### Core Modules (`core/`)

- `spotify_playlist_fetcher.py`
  - Fetches Spotify playlist tracks through the embed page
- `spotify.py`
  - Scrapes Spotify data and builds playlist content
- `library.py`
  - Runs the main update workflow, conversion helpers, playlist cleanup, and statistics
- `audio_converter.py`
  - Handles audio format conversion and metadata migration
- `sync_manager.py`
  - Exports and synchronizes playlists to external folders
- `downloader.py`
  - Optional download utilities not used by the default update flow

### GUI (`gui/`)

- `app.py`
  - Main Tkinter application
- `settings.py`
  - Settings dialog and user preferences
- `update_dialog.py`
  - Update notification dialog

### Utilities (`utils/`)

- `config.py`
  - Loads, saves, and derives application paths
- `helpers.py`
  - Shared filename and normalization helpers
- `i18n.py`
  - Internationalization

## Runtime Flow

1. Load config from app data or the selected `base_path`
2. Derive `library_path`, `playlists_path`, and `export_path`
3. Ensure required folders exist
4. Run one of:
   - Tkinter UI workflow through `main.py`
   - CLI workflow through `cli.py`

## Main Update Workflow

`core.library.update_library_logic()` currently coordinates:

1. Directory validation
2. Spotube-related M4A to MP3 conversion
3. Spotify embed scraping
4. Playlist generation and refresh
5. Missing-track pruning
6. Unsorted-track organization

## File Structure

```text
Playlist Administrator/
├── main.py
├── cli.py
├── core/
├── gui/
├── utils/
├── tools/
├── docs/
├── Docs_ZH/
├── README.md
├── README_ZH.md
└── requirements.txt
```

## Notes

- Tkinter is the only supported UI entrypoint.
- Spotify scraping depends on the embed page and network access.
- FFmpeg is optional but required for conversion-related workflows.
