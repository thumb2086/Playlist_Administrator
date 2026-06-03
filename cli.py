import argparse
import glob
import json
import os
import sys
import threading

try:
    import win32gui
except ImportError:
    win32gui = None


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
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        safe = message.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
        print(safe, flush=True)


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
        path = find_song_exact_format(track, mp3_index)
        method = "exact"

        if not path and not args.prefer_mp3:
            path = find_song_exact_format(track, lib_index)
            method = "exact-all"

        if not path:
            path = find_song_simple_match(track, mp3_index)
            method = "simple"

        if not path and not args.prefer_mp3:
            path = find_song_simple_match(track, lib_index)
            method = "simple-all"

        if not path:
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
    from core.spotify_playlist_fetcher import fetch_legacy_embed_playlist

    import requests

    session = requests.Session()

    # Use Embed API to fetch playlist.
    print(f"[INFO] Fetching via Embed API...")
    result = fetch_legacy_embed_playlist(args.url, session)

    print(f"\nURL: {args.url}")
    print(f"Source: {result.source}")
    print(f"HTTP Status: {result.status_code}")
    if result.playlist_name:
        print(f"Playlist Name: {result.playlist_name}")
    if result.error:
        print(f"Error: {result.error}")
    print(f"Tracks Found: {len(result.tracks)}")

    if args.show_tracks and result.tracks:
        print(f"\nTrack List:")
        for i, track in enumerate(result.tracks, 1):
            print(f"{i}. {track}")

    if args.output and result.tracks:
        _write_debug_tracks(args.output, result.tracks)
        print(f"Output written to: {args.output}")

    return 0 if result.tracks else 1


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

    fetch_parser = subparsers.add_parser(
        "fetch-playlist",
        help="Fetch playlist tracks via the Spotify embed API.",
    )
    fetch_parser.add_argument("url", help="Spotify playlist URL.")
    fetch_parser.add_argument("--show-tracks", action="store_true", help="Print the track list.")
    fetch_parser.add_argument("--output", help="Write track list to a debug file.")
    fetch_parser.set_defaults(func=cmd_fetch_playlist)

    # ---- Pipeline (new orchestrated flow) ----

    def cmd_pipeline(args):
        from core.pipeline import PipelineOrchestrator, PipelineState

        config = _load_config(args.config)
        if args.force:
            _force_refresh(config)

        state = PipelineState(
            config=config,
            log_func=_print_log,
            progress_cb=lambda step, cur, total, msg: (
                _progress(cur, total) if args.progress else None
            ),
        )
        orch = PipelineOrchestrator(config)
        if args.list_steps:
            for idx, name, weight in orch.list_steps():
                print(f"  {idx}. {name} (weight {weight})")
            return 0
        if args.step is not None:
            return 0 if orch.run_step(int(args.step), state) else 1
        if args.from_step is not None:
            return 0 if orch.run(state, from_step=int(args.from_step)) else 1
        return 0 if orch.run(state) else 1

    pl_parser = subparsers.add_parser("pipeline", help="Run the full pipeline (convert, scrape, prune, unsorted, metadata).")
    pl_parser.add_argument("--force", action="store_true", help="Ignore last_updated timestamps.")
    pl_parser.add_argument("--progress", action="store_true", help="Print progress callbacks.")
    pl_parser.add_argument("--step", help="Run a single step by index (e.g. 0 = convert).")
    pl_parser.add_argument("--from-step", help="Start from this step index.")
    pl_parser.add_argument("--list-steps", action="store_true", help="List all pipeline steps and exit.")
    pl_parser.set_defaults(func=cmd_pipeline)

    # ---- Spotube automation ----

    def cmd_spotube_download(args):
        from core.spotube_controller import SpotubeController
        config = _load_config(args.config)
        ctrl = SpotubeController(config)
        ctrl.download_playlist(args.name, force=args.force)
        return 0

    def cmd_spotube_download_all(args):
        from core.spotube_controller import SpotubeController
        config = _load_config(args.config)
        url_names = config.get("url_names", {})
        if not url_names:
            print("ERROR: config.json has no url_names entries.")
            return 1
        ctrl = SpotubeController(config)
        ctrl.download_all_playlists(url_names, force=args.force)
        return 0

    def cmd_spotube_status(args):
        from core.spotube_controller import SpotubeController
        from core.spotube_file_handler import move_spotube_downloads
        config = _load_config(args.config)

        ctrl = SpotubeController(config)
        running = ctrl.is_running()
        print(f"Spotube 執行中: {'是' if running else '否'}")
        if running and win32gui:
            hwnd = ctrl.hwnd
            rect = win32gui.GetWindowRect(hwnd)
            ox, oy = ctrl._client_origin()
            print(f"  視窗位置: ({rect[0]}, {rect[1]}) 大小: ({rect[2]-rect[0]}×{rect[3]-rect[1]})")
            print(f"  客戶區原點: ({ox}, {oy})")

        # Check download folder.
        dl_path = config.get(
            "spotube_download_path",
            os.path.expandvars(r"%USERPROFILE%\Downloads\Spotube"),
        )
        if os.path.isdir(dl_path):
            files = [f for f in os.listdir(dl_path) if f.lower().endswith(".m4a")]
            print(f"  下載資料夾 ({dl_path}): {len(files)} 個 .m4a 檔案")
        else:
            print(f"  下載資料夾不存在: {dl_path}")

        # Count m4a files in library.
        m4a_path = os.path.join(config.get("library_path", ""), "m4a")
        if os.path.isdir(m4a_path):
            m4a_count = len(glob.glob(os.path.join(m4a_path, "*.m4a")))
            print(f"  Library m4a: {m4a_count} 個檔案")
        else:
            print(f"  Library m4a 資料夾不存在: {m4a_path}")

        # List download state
        downloaded = ctrl.list_downloaded()
        print(f"  已下載記錄: {len(downloaded)} 個")
        for name in downloaded[:10]:
            safe_name = name.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
            print(f"    [OK] {safe_name}")
        if len(downloaded) > 10:
            print(f"    … 還有 {len(downloaded)-10} 個")

        # List config playlists.
        url_names = config.get("url_names", {})
        print(f"  已設定歌單: {len(url_names)} 個")
        for i, (url, name) in enumerate(url_names.items(), 1):
            safe_name = name.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
            prefix = "[V]" if name in downloaded else "   "
            print(f"    {prefix} {i}. {safe_name}")

        return 0

    def cmd_spotube_move(args):
        from core.spotube_file_handler import move_spotube_downloads
        config = _load_config(args.config)
        moved = move_spotube_downloads(config, _print_log, dry_run=args.dry_run)
        return 0

    sp_dl = subparsers.add_parser("spotube-download", help="下載指定歌單 (透過 Spotube GUI 自動化)")
    sp_dl.add_argument("name", help="歌單名稱（與 url_names 中的名稱匹配）")
    sp_dl.add_argument("--force", action="store_true", help="忽略已下載記錄，強制重新下載")
    sp_dl.set_defaults(func=cmd_spotube_download)

    sp_all = subparsers.add_parser("spotube-download-all", help="下載所有已設定的歌單")
    sp_all.add_argument("--force", action="store_true", help="忽略已下載記錄，強制重新下載")
    sp_all.set_defaults(func=cmd_spotube_download_all)

    sp_st = subparsers.add_parser("spotube-status", help="檢視 Spotube 和下載狀態")
    sp_st.set_defaults(func=cmd_spotube_status)

    sp_mv = subparsers.add_parser("spotube-move", help="將 Downloads/Spotube 中的檔案搬移到 Library m4a 資料夾")
    sp_mv.add_argument("--dry-run", action="store_true", help="僅模擬，不實際搬移")
    sp_mv.set_defaults(func=cmd_spotube_move)

    def cmd_spotube_reset(args):
        from core.spotube_controller import SpotubeController
        config = _load_config(args.config)
        ctrl = SpotubeController(config)
        ctrl.reset_state(args.name)
        if args.name:
            print(f"已清除 '{args.name}' 的下載記錄")
        else:
            print("已清除所有下載記錄")
        return 0

    sp_rs = subparsers.add_parser("spotube-reset", help="清除已下載記錄")
    sp_rs.add_argument("--name", help="只清除指定歌單的記錄（省略則全部清除）")
    sp_rs.set_defaults(func=cmd_spotube_reset)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
