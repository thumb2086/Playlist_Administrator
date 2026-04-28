import argparse
import glob
import json
import os
import sys
import threading


def _bootstrap_local_site_packages():
    # Let the CLI work with the repository-local virtualenv even when it is
    # launched by a bundled/system Python.
    project_dir = os.path.dirname(os.path.abspath(__file__))
    site_packages = os.path.join(project_dir, ".venv", "Lib", "site-packages")
    if os.path.isdir(site_packages) and site_packages not in sys.path:
        sys.path.insert(0, site_packages)

    # Older pkg_resources used by zhconv expects pkgutil.ImpImporter, which was
    # removed in newer Python versions. This compatibility shim is harmless on
    # Python versions that still provide it.
    try:
        import pkgutil
        import zipimport

        if not hasattr(pkgutil, "ImpImporter"):
            pkgutil.ImpImporter = zipimport.zipimporter
    except Exception:
        pass


_bootstrap_local_site_packages()


def _load_config(config_path=None):
    from utils import config as config_module

    if not config_path:
        return config_module.load_config()

    config_path = os.path.abspath(config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    if "base_path" not in config or not config["base_path"]:
        config["base_path"] = os.path.dirname(config_path)
    config_module.derive_paths(config)

    config_module.CONFIG_DIR = os.path.dirname(config_path)
    config_module.CONFIG_FILE = config_path

    from utils.i18n import I18N

    I18N.set_language(config.get("language", "zh-TW"))
    return config


def _make_stats():
    from core.library import UpdateStats

    stats = UpdateStats()
    stats.stop_event = threading.Event()
    stats.pause_event = threading.Event()
    stats.pause_event.set()
    return stats


def _print_log(message):
    print(message, flush=True)


def _progress(current, total=100, eta=None):
    if not total:
        return
    print(f"[progress] {current}/{total}", flush=True)


def _force_refresh(config, target_urls=None):
    urls = target_urls or config.get("spotify_urls", [])
    last_updated = config.setdefault("last_updated", {})
    for url in urls:
        last_updated.pop(url, None)


def cmd_update(args):
    from core.library import update_library_logic

    config = _load_config(args.config)
    if args.force:
        _force_refresh(config)

    stats = _make_stats()
    update_library_logic(config, stats, _print_log, progress_func=_progress if args.progress else None)
    return 0


def cmd_scrape(args):
    from core.spotify import scrape_via_spotify_embed

    config = _load_config(args.config)
    target_urls = args.url or None
    if args.force:
        _force_refresh(config, target_urls)

    stats = _make_stats()
    scrape_via_spotify_embed(config, stats, _print_log, target_urls=target_urls)
    return 0


def _default_debug_file(config):
    playlists_path = config.get("playlists_path") or "."
    debug_file = os.path.join(playlists_path, "_spotify_debug.txt")
    if os.path.exists(debug_file):
        return debug_file

    daily_mix = os.path.join(playlists_path, "Daily Mix 1.m3u8")
    if os.path.exists(daily_mix):
        return daily_mix

    return debug_file


def _read_spotify_debug(debug_file):
    tracks = []
    with open(debug_file, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#EXTINF:"):
                _, track_name = line.split(",", 1) if "," in line else ("", "")
                if track_name:
                    tracks.append(track_name.strip())
                continue
            if line.startswith("#") or line.lower().endswith((".mp3", ".m4a", ".flac", ".wav", ".webm")):
                continue
            if ". " in line:
                prefix, rest = line.split(". ", 1)
                if prefix.isdigit():
                    line = rest
            tracks.append(line)
    return tracks


def _audio_files(library_path):
    exts = (".mp3", ".m4a", ".flac", ".wav", ".webm")
    pattern = os.path.join(library_path, "**", "*")
    return [path for path in glob.glob(pattern, recursive=True) if path.lower().endswith(exts)]


def cmd_match(args):
    from core.library import (
        build_library_index,
        build_metadata_index,
        find_song_exact_format,
        find_song_in_library,
        find_song_simple_match,
    )

    config = _load_config(args.config)
    debug_file = args.file or _default_debug_file(config)
    tracks = _read_spotify_debug(debug_file)
    audio_files = _audio_files(config["library_path"])
    lib_index = build_library_index(audio_files)
    mp3_files = [path for path in audio_files if path.lower().endswith(".mp3")]
    mp3_index = build_library_index(mp3_files)
    metadata_index = build_metadata_index(mp3_files)
    all_metadata_index = build_metadata_index(audio_files)

    found = []
    missing = []
    method_counts = {}

    for track in tracks:
        path = None
        method = None

        if args.prefer_mp3:
            path = find_song_simple_match(track, "mp3", lib_index)
            method = "simple"
            if not path:
                path = find_song_exact_format(track, "mp3", lib_index)
                method = "exact"
            if not path and metadata_index:
                path = find_song_in_library(track, mp3_index, metadata_index=metadata_index)
                method = "metadata"

        if not path and not args.prefer_mp3:
            path = find_song_in_library(track, lib_index, metadata_index=all_metadata_index)
            method = "library"

        if path:
            found.append((track, path, method))
            method_counts[method] = method_counts.get(method, 0) + 1
        else:
            missing.append(track)

    print(f"Tracks: {len(tracks)}")
    print(f"Audio files: {len(audio_files)}")
    print(f"Index entries: {len(lib_index)}")
    print(f"MP3 metadata entries: {len(metadata_index)}")
    print(f"All metadata entries: {len(all_metadata_index)}")
    print(f"Matched: {len(found)}")
    print(f"Missing: {len(missing)}")
    print(f"Methods: {method_counts}")

    if missing:
        print("\nMissing tracks:")
        for track in missing:
            print(f"- {track}")

    if args.verbose:
        print("\nMatches:")
        for track, path, method in found:
            print(f"[{method}] {track} => {path}")

    return 1 if missing and args.fail_on_missing else 0


def cmd_convert_playlist(args):
    from core.library import (
        _resolve_spotube_paths,
        build_library_index,
        build_metadata_index,
        convert_spotube_m4a_to_mp3,
        find_song_exact_format,
        find_song_in_library,
        find_song_simple_match,
    )

    config = _load_config(args.config)
    debug_file = args.file or _default_debug_file(config)
    tracks = _read_spotify_debug(debug_file)
    m4a_path, mp3_path = _resolve_spotube_paths(config)

    mp3_files = _audio_files(mp3_path) if os.path.isdir(mp3_path) else []
    mp3_index = build_library_index(mp3_files)
    mp3_metadata = build_metadata_index(mp3_files)

    m4a_files = [
        path for path in _audio_files(m4a_path)
        if path.lower().endswith(".m4a")
    ] if os.path.isdir(m4a_path) else []
    m4a_index = build_library_index(m4a_files)
    m4a_metadata = build_metadata_index(m4a_files)

    already_done = []
    missing_sources = []
    source_files = []
    seen_sources = set()

    for track in tracks:
        mp3_match = find_song_simple_match(track, "mp3", mp3_index)
        if not mp3_match:
            mp3_match = find_song_exact_format(track, "mp3", mp3_index)
        if not mp3_match and mp3_metadata:
            mp3_match = find_song_in_library(track, mp3_index, metadata_index=mp3_metadata)

        if mp3_match:
            already_done.append((track, mp3_match))
            continue

        source = find_song_in_library(track, m4a_index, metadata_index=m4a_metadata)
        if source and source.lower().endswith(".m4a"):
            norm_source = os.path.normpath(source)
            if norm_source not in seen_sources:
                source_files.append(norm_source)
                seen_sources.add(norm_source)
        else:
            missing_sources.append(track)

    print(f"Tracks: {len(tracks)}")
    print(f"Existing MP3 matches: {len(already_done)}")
    print(f"M4A sources to convert: {len(source_files)}")
    print(f"Missing M4A sources: {len(missing_sources)}")

    if missing_sources:
        print("\nMissing M4A sources:")
        for track in missing_sources:
            print(f"- {track}")

    if args.dry_run:
        if source_files:
            print("\nWould convert:")
            for path in source_files:
                print(f"- {path}")
        return 0

    if not source_files:
        print("No playlist M4A files need conversion.")
        return 0

    converted, skipped, total = convert_spotube_m4a_to_mp3(
        config,
        _print_log,
        source_files=source_files,
    )
    print(f"Conversion summary: {converted} converted, {skipped} skipped, {total} total")
    return 0


def _write_debug_tracks(path, tracks):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for index, track in enumerate(tracks, 1):
            f.write(f"{index}. {track}\n")


def _print_track_list(title, tracks):
    print(f"\n{title} ({len(tracks)}):")
    for index, track in enumerate(tracks, 1):
        print(f"{index}. {track}")


def cmd_fetch_playlist(args):
    from core.spotify_playlist_fetcher import (
        compare_track_lists,
        fetch_legacy_embed_playlist,
        fetch_redesigned_playlist,
    )

    import requests

    session = requests.Session()
    redesigned = fetch_redesigned_playlist(args.url, session)
    legacy = fetch_legacy_embed_playlist(args.url, session)
    diff = compare_track_lists(redesigned.tracks, legacy.tracks)

    print(f"URL: {args.url}")
    print(f"Redesigned source: {redesigned.source}")
    print(f"Redesigned status: {redesigned.status_code}")
    if redesigned.playlist_name:
        print(f"Redesigned playlist: {redesigned.playlist_name}")
    if redesigned.error:
        print(f"Redesigned error: {redesigned.error}")
    print(f"Redesigned tracks: {len(redesigned.tracks)}")

    print(f"Legacy source: {legacy.source}")
    print(f"Legacy status: {legacy.status_code}")
    if legacy.playlist_name:
        print(f"Legacy playlist: {legacy.playlist_name}")
    if legacy.error:
        print(f"Legacy error: {legacy.error}")
    print(f"Legacy tracks: {len(legacy.tracks)}")

    print(f"Only redesigned: {len(diff['only_new'])}")
    for track in diff["only_new"]:
        print(f"+ {track}")

    print(f"Only legacy: {len(diff['only_legacy'])}")
    for track in diff["only_legacy"]:
        print(f"- {track}")

    if diff["same_order_differences"]:
        print(f"Order/content differences: {len(diff['same_order_differences'])}")
        for line in diff["same_order_differences"][: args.max_order_diff]:
            print(line)

    for probe in args.probe or []:
        in_redesigned = probe in redesigned.tracks
        in_legacy = probe in legacy.tracks
        print(
            "Probe: "
            f"{probe} | redesigned={'yes' if in_redesigned else 'no'} "
            f"| legacy={'yes' if in_legacy else 'no'}"
        )

    if args.show_tracks:
        _print_track_list("Redesigned tracks", redesigned.tracks)
        _print_track_list("Legacy tracks", legacy.tracks)

    if args.output:
        _write_debug_tracks(args.output, redesigned.tracks)
        print(f"Wrote redesigned tracks to: {args.output}")

    return 0 if redesigned.tracks else 1


def build_parser():
    parser = argparse.ArgumentParser(description="Playlist Administrator command line tools")
    parser.add_argument(
        "--config",
        help="Path to config.json. Defaults to the app config resolved by utils.config.load_config().",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    update_parser = subparsers.add_parser("update", help="Run the full update flow.")
    update_parser.add_argument("--force", action="store_true", help="Ignore last_updated for this run.")
    update_parser.add_argument("--progress", action="store_true", help="Print progress callbacks.")
    update_parser.set_defaults(func=cmd_update)

    scrape_parser = subparsers.add_parser("scrape", help="Scrape Spotify and rebuild playlist files.")
    scrape_parser.add_argument("--url", action="append", help="Spotify URL to scrape. Can be passed multiple times.")
    scrape_parser.add_argument("--force", action="store_true", help="Ignore last_updated for selected URLs.")
    scrape_parser.set_defaults(func=cmd_scrape)

    match_parser = subparsers.add_parser("match", help="Test local matching using _spotify_debug.txt.")
    match_parser.add_argument("--file", help="Path to a Spotify debug track list.")
    match_parser.add_argument("--prefer-mp3", action=argparse.BooleanOptionalAction, default=True)
    match_parser.add_argument("--verbose", "-v", action="store_true", help="Print every matched path.")
    match_parser.add_argument("--fail-on-missing", action="store_true", help="Exit with code 1 when tracks are missing.")
    match_parser.set_defaults(func=cmd_match)

    convert_parser = subparsers.add_parser(
        "convert-playlist",
        help="Convert only M4A files needed by a Spotify debug track list.",
    )
    convert_parser.add_argument("--file", help="Path to a Spotify debug track list.")
    convert_parser.add_argument("--dry-run", action="store_true", help="Print planned conversions without writing MP3 files.")
    convert_parser.set_defaults(func=cmd_convert_playlist)

    fetch_parser = subparsers.add_parser(
        "fetch-playlist",
        help="Fetch a Spotify playlist with the redesigned scraper and compare it with the legacy parser.",
    )
    fetch_parser.add_argument("url", help="Spotify playlist URL.")
    fetch_parser.add_argument("--show-tracks", action="store_true", help="Print both full track lists.")
    fetch_parser.add_argument("--output", help="Write redesigned track list to a debug text file.")
    fetch_parser.add_argument("--max-order-diff", type=int, default=20, help="Maximum order differences to print.")
    fetch_parser.add_argument("--probe", action="append", help="Track name to check in both fetched lists.")
    fetch_parser.set_defaults(func=cmd_fetch_playlist)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
