# Architecture Documentation

## Overview

Playlist Administrator is a music library management tool that builds and updates Spotify playlists from local audio files. It uses Spotify's embed page for scraping (no authentication required) and focuses on MP3 files for playlists.

## Core Components

### Core Modules (`core/`)

- **`spotify_playlist_fetcher.py`**: Spotify playlist fetching via embed page
  - `fetch_legacy_embed_playlist()`: Main function to fetch playlist tracks
  - `fetch_playlist()`: Unified interface (simplified to only use embed)
  - Removed: `SpotifyWebAPI` class and `fetch_via_web_api()` function

- **`spotify.py`**: Spotify scraping and playlist building
  - `scrape_via_spotify_embed()`: Main scraping function
  - Parses embed pages to extract track information
  - Builds `.m3u8` playlist files
  - Forces MP3-only matching for playlists

- **`library.py`**: Library management and file operations
  - `update_library_logic()`: Main update workflow
  - Removed: M4A to MP3 conversion functions
  - Removed: `_resolve_spotube_paths()`, `_has_m4a_files()`, `_get_m4a_cache_key()`, `_m4a_files_from_source()`, `convert_spotube_m4a_to_mp3()`

- **`audio_converter.py`**: Audio format conversion
  - `convert_audio_file()`: Generic audio conversion
  - `_migrate_m4a_metadata_to_mp3()`: Metadata migration (reads M4A, writes MP3 - does not modify M4A)

- **`downloader.py`**: Download utilities (yt-dlp, DAB, spotDL)
  - Not used in default update flow
  - Available for manual use

### GUI (`gui/`)

- **`app.py`**: Tkinter main application
  - Removed: `load_playlist_into_player()` call (function didn't exist)
  - Simplified playlist loading to just log selection

- **`settings.py`**: Settings window
  - Removed: Spotify OAuth login section
  - Removed: M4A/MP3 subfolder settings
  - Removed: Conversion worker settings
  - Removed: "Prefer MP3" checkbox
  - Kept: Language, base path, ffmpeg path

### CLI (`cli.py`)

- **`update`**: Run full update flow
- **`scrape`**: Scrape Spotify URLs only
- **`fetch-playlist`**: Fetch playlist tracks via embed
- **`match`**: Test local matching
- Removed: `convert-playlist` command

### Configuration (`utils/config.py`)

Removed settings:
- `spotube_m4a_subfolder`
- `spotube_mp3_subfolder`
- `prefer_mp3_playlists`
- `spotube_convert_workers`
- `spotify_client_id`
- `spotify_client_secret`
- `spotify_fetch_method`

Kept settings:
- `base_path`
- `ffmpeg_path`
- `spotube_folder_name`
- `spotube_exact_match`

## Recent Changes

### Spotify API Removal
- Removed Spotify Web API integration (OAuth, client credentials)
- Removed `SpotifyWebAPI` class and all authentication logic
- Simplified to only use embed page scraping
- No authentication required for Spotify playlist fetching

### M4A Conversion Removal
- Removed M4A to MP3 conversion functionality
- Removed M4A folder creation and management
- Removed conversion worker settings
- Removed M4A cache system
- Playlists now use MP3 files exclusively

### GUI Simplification
- Removed Spotify OAuth login interface
- Removed M4A/MP3 subfolder configuration
- Removed conversion settings
- Fixed missing `load_playlist_into_player` method error

### CLI Cleanup
- Removed `convert-playlist` command
- Kept core functionality: update, scrape, fetch-playlist, match

## File Structure

```
Playlist Administrator/
├── main.py                    # Tkinter entry point
├── streamlit_app.py           # Streamlit UI
├── cli.py                     # Command-line interface
├── core/
│   ├── spotify_playlist_fetcher.py  # Spotify fetching (embed only)
│   ├── spotify.py                    # Spotify scraping & playlist building
│   ├── library.py                    # Library management
│   ├── audio_converter.py            # Audio conversion
│   ├── downloader.py                 # Download utilities
│   ├── sync_manager.py              # Sync operations
│   ├── metadata_enricher.py          # Metadata enrichment
│   └── file_renamer.py              # File renaming
├── gui/
│   ├── app.py                       # Tkinter main app
│   └── settings.py                  # Settings window
├── utils/
│   ├── config.py                    # Configuration
│   ├── helpers.py                   # Helper functions
│   └── i18n.py                      # Internationalization
├── tools/
│   └── fix_flac_names.py            # FLAC naming utility
├── docs/
│   └── architecture.md              # This file
├── README.md                        # English documentation
├── README_ZH.md                     # Chinese documentation
└── requirements.txt                 # Python dependencies
```

## Workflow

1. **Setup**: Configure base path (contains Music/ and Playlists/)
2. **Add URLs**: Add Spotify playlist/album/artist URLs
3. **Update**: Run update flow
   - Scrape Spotify URLs via embed page
   - Build library index of local audio files
   - Match Spotify tracks to local MP3 files
   - Create/update `.m3u8` playlist files
   - Remove missing entries from playlists
   - Move unsorted tracks to `_Unsorted`
4. **Export**: Export playlists to USB/SD if needed

## Notes

- Spotify scraping requires network access but no authentication
- Playlists use MP3 files exclusively
- M4A files are not modified by the application
- Download utilities exist but are not used in default flow
- FFmpeg is optional (only needed for audio conversion)
