# Project Structure

## Directory Organization

```text
core/                    # Business logic modules
  audio_converter.py     # Audio format conversion
  dab_client.py          # DAB music service integration
  dab_downloader.py      # DAB-specific download logic
  downloader.py          # YouTube download orchestration
  file_renamer.py        # Automatic file renaming
  library.py             # Core library management
  metadata_enricher.py   # Audio metadata enhancement
  spotify.py             # Spotify integration utilities
  sync_manager.py        # Folder synchronization
gui/                     # Desktop GUI components
  app.py                 # Main Tkinter application
  settings.py            # Settings dialog
utils/                   # Shared utilities
  config.py              # Configuration management
  helpers.py             # Common helper functions
  i18n.py                # Internationalization
  rename_to_artist_title.py
examples/                # Example files and templates
Docs_ZH/                 # Chinese documentation
docs/                    # English documentation
main.py                  # Desktop application entry point
cli.py                   # CLI entry point
requirements.txt         # Python dependencies
```

## Module Responsibilities

### Core Modules

- `library.py`: Central library management, playlist loading, update workflow, statistics
- `downloader.py`: Optional download orchestration with yt-dlp
- `spotify.py`: Spotify playlist analysis and metadata extraction
- `sync_manager.py`: Folder synchronization and file organization
- `metadata_enricher.py`: Audio file metadata enhancement
- `audio_converter.py`: Format conversion and audio processing

### GUI Layer

- `gui/app.py`: Main desktop application with Tkinter
- `gui/settings.py`: Configuration dialogs and user preferences

### Utilities

- `config.py`: JSON configuration management with path derivation
- `helpers.py`: File sanitization, name normalization, common utilities
- `i18n.py`: Multi-language support

## Configuration Architecture

- Centralized config with app-data fallback and optional `base_path` config
- Derived paths from `base_path`
- Runtime directories created automatically when missing
- Persistent user preferences with sensible defaults

## Threading Model

- Main thread for UI operations
- Background threads for long-running work
- Stop/pause events for user control
- Batched UI/log updates for responsiveness
