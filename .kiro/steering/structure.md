# Project Structure

## Directory Organization

```
├── core/                    # Business logic modules
│   ├── audio_converter.py   # Audio format conversion
│   ├── dab_client.py       # DAB music service integration
│   ├── dab_downloader.py   # DAB-specific download logic
│   ├── downloader.py       # YouTube download orchestration
│   ├── file_renamer.py     # Automatic file renaming
│   ├── library.py          # Core library management
│   ├── metadata_enricher.py # Audio metadata enhancement
│   ├── spotify.py          # Spotify integration utilities
│   └── sync_manager.py     # Folder synchronization
├── gui/                    # Desktop GUI components
│   ├── app.py             # Main Tkinter application
│   └── settings.py        # Settings dialog
├── utils/                  # Shared utilities
│   ├── config.py          # Configuration management
│   ├── helpers.py         # Common helper functions
│   ├── i18n.py           # Internationalization
│   └── rename_to_artist_title.py # File naming utilities
├── data/                   # Application data (created at runtime)
│   ├── config.json        # User configuration
│   ├── changelog.json     # Version history
│   └── Music/             # Downloaded audio files
├── examples/              # Example files and templates
├── test_library/          # Test audio files
├── Docs_ZH/              # Chinese documentation
├── main.py               # Desktop application entry point
├── streamlit_app.py      # Web interface entry point
└── requirements.txt      # Python dependencies
```

## Module Responsibilities

### Core Modules
- **library.py**: Central library management, playlist loading, statistics
- **downloader.py**: YouTube download orchestration with yt-dlp
- **spotify.py**: Spotify playlist analysis and metadata extraction
- **sync_manager.py**: Folder synchronization and file organization
- **metadata_enricher.py**: Audio file metadata enhancement
- **audio_converter.py**: Format conversion and audio processing

### GUI Layer
- **gui/app.py**: Main desktop application with Tkinter
- **streamlit_app.py**: Web-based interface with real-time updates
- **gui/settings.py**: Configuration dialogs and user preferences

### Utilities
- **config.py**: JSON configuration management with path derivation
- **helpers.py**: File sanitization, name normalization, common utilities
- **i18n.py**: Multi-language support (Chinese/English)

## Naming Conventions
- **Files**: snake_case for Python files
- **Classes**: PascalCase (e.g., `PlaylistApp`, `UpdateStats`)
- **Functions**: snake_case (e.g., `load_config`, `sanitize_filename`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `CONFIG_FILE`, `DEFAULT_TIMEOUT`)

## Configuration Architecture
- **Centralized Config**: Single JSON file in `data/config.json`
- **Path Derivation**: All paths derived from `base_path` setting
- **Runtime Directories**: Created automatically if missing
- **User Preferences**: Stored persistently with sensible defaults

## Threading Model
- **Main Thread**: UI operations and user interaction
- **Background Threads**: Download operations, file processing
- **Event System**: Stop/pause events for user control
- **Queue-Based Logging**: Batched UI updates for performance