# Technology Stack

## Core Technologies
- **Python 3.x**: Primary programming language
- **Tkinter**: Desktop GUI framework
- **yt-dlp**: YouTube downloading engine
- **ffmpeg**: Audio processing and conversion
- **BeautifulSoup4**: Web scraping for playlist analysis
- **Mutagen**: Audio metadata manipulation
- **pygame**: Audio playback functionality

## Key Dependencies
```
yt-dlp[default]  # YouTube downloader with all optional dependencies
requests         # HTTP client
beautifulsoup4   # HTML parsing
ffmpeg-python    # FFmpeg Python bindings
mutagen          # Audio metadata
pygame           # Audio playback
syncedlyrics     # Lyrics synchronization
zhconv           # Chinese text conversion
pyinstaller      # Executable packaging
```

## Architecture Patterns
- **Modular Design**: Separated into `core/`, `gui/`, and `utils/` modules
- **Configuration-Driven**: JSON-based configuration system in `data/config.json`
- **Threading**: Background operations for downloads and UI responsiveness
- **Event-Driven**: Stop/pause events for user control
- **Bridge Pattern**: StatusBridge for UI-backend communication

## Common Commands

### Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run desktop GUI
python main.py

# Build executable
pyinstaller app.spec
```

### System Requirements
- **ffmpeg**: Must be installed and available in PATH
- **Python 3.7+**: Required for all dependencies
- **Internet Connection**: Required for downloading and playlist analysis

## File Structure Conventions
- `Library/`: Master repository for all downloaded audio files
- `Playlists/`: Playlist metadata and M3U8 files
- `USB_Export/`: Temporary export folder (cleared on each export)
- `data/`: Configuration and application data
- `core/`: Business logic modules
- `gui/`: UI components
- `utils/`: Shared utilities and helpers
