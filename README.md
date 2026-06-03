# Playlist Administrator

A Flutter desktop app for music library management and Spotube playlist automation.

## Features

- **Spotube Automation** — Automatically download playlists via Spotube GUI
- **Audio Conversion** — M4A → MP3 with batch processing
- **Spotify Scraping** — Fetch playlists via Spotify Embed API
- **Playlist Management** — Track completeness, prune missing files
- **Statistics** — Library size, format distribution, coverage charts

## Build

```bash
flutter pub get
flutter create --platforms=windows .
flutter build windows --release
```

## CLI

```bash
dart run lib/cli_main.dart pipeline
dart run lib/cli_main.dart spotube-download "Daily Mix 1"
dart run lib/cli_main.dart spotube-download-all
dart run lib/cli_main.dart spotube-move
dart run lib/cli_main.dart status
```

## Calibration

```bash
dart run lib/calibrate.dart
```

## Release

Push a `v*` tag to trigger GitHub Actions:

```bash
git tag v2.0.0
git push origin v2.0.0
```

## Dependencies

- `win32` — Windows API (Spotube automation)
- `http` + `html` — Spotify scraping
- `fl_chart` — Charts
- `ffi` — FFI support
