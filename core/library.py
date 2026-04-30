import os
import glob
import time
import shutil
import random
import requests
import json
import hashlib
from functools import lru_cache
from bs4 import BeautifulSoup
from utils.helpers import sanitize_filename, normalize_name
from utils.config import ensure_dirs, get_data_file
from core.spotify import get_spotify_name

DEFAULT_ARTIST_ALIASES = {
    'claire kuo': '郭靜',
    'jolin': '蔡依林',
    'jolin tsai': '蔡依林',
    'crowd lu': '盧廣仲',
    'pets tseng': '曾沛慈',
    'evangeline wong': '王艷薇',
    'sabrina': '胡恂舞',
    'sabrina hu': '胡恂舞',
    'eric chou': '周興哲',
    'shi shi': '孫盛希',
    'boon hui lu': '文慧如',
    'vicky chen': '陳忻玥',
    'feng ze': '邱鋒澤',
    'ivy': '艾薇',
    'genblue': '幻藍小熊',
    'lbi': '利比',
    'erin': '連穎',
    'eleanor': '李芷婷',
    'ann bai': '白安',
    'diana wang': '王詩安',
    'ethan': '陳威全',
    'chih siou': '持修',
    'show luo': '羅志祥',
}


def _artist_aliases_file_path():
    try:
        return get_data_file('artist_aliases.json')
    except Exception:
        return None


@lru_cache(maxsize=1)
def _load_artist_aliases_cached(cache_key):
    alias_map = dict(DEFAULT_ARTIST_ALIASES)
    alias_file = _artist_aliases_file_path()
    if not alias_file or not os.path.exists(alias_file):
        return alias_map

    try:
        with open(alias_file, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
    except Exception:
        return alias_map

    if not isinstance(loaded, dict):
        return alias_map

    for key, value in loaded.items():
        if not key:
            continue

        if isinstance(value, str) and value.strip():
            alias_map[key.strip().lower()] = value.strip()
            continue

        if isinstance(value, list):
            canonical = key.strip()
            if not canonical:
                continue
            for alias in value:
                if isinstance(alias, str) and alias.strip():
                    alias_map[alias.strip().lower()] = canonical

    return alias_map


def get_artist_aliases():
    alias_file = _artist_aliases_file_path()
    cache_key = None

    if alias_file and os.path.exists(alias_file):
        try:
            cache_key = (alias_file, os.path.getmtime(alias_file))
        except OSError:
            cache_key = (alias_file, None)

    return _load_artist_aliases_cached(cache_key)

def get_playlist_type(spotify_url):
    """Determines the type of Spotify URL (Playlist, Album, Artist)"""
    if "playlist/" in spotify_url:
        return "Playlist"
    elif "album/" in spotify_url:
        return "Album"
    elif "artist/" in spotify_url:
        return "Artist"
    elif "track/" in spotify_url:
        return "Track"
    else:
        return "Unknown"

def load_playlists_data(config):
    """
    Scans the playlists directory and returns a list of playlist data for the UI.
    Returns: List[Dict] with keys: '啟用', '類型', '名稱', '連結', '狀態'
    """
    playlists_path = config.get('playlists_path')
    if not playlists_path:
        return []
    
    playlists_path = os.path.normpath(playlists_path)
    if not os.path.exists(playlists_path):
        return []

    library_path = config.get('library_path')
    
    # 1. Gather all m3u8 files
    m3u8_files = glob.glob(os.path.join(playlists_path, "*.m3u8"))
    
    # 2. Get info from config
    spotify_urls = config.get('spotify_urls', [])
    url_names = config.get('url_names', {})
    
    # Map name back to URL
    name_to_url = {v: k for k, v in url_names.items()}
    
    # 3. Build report for completeness
    report = get_playlist_completeness_report(m3u8_files, library_path)
    
    playlist_data = []
    
    # Process m3u8 files from config/scraped first
    processed_names = set()
    
    # Early normalize library_path for completeness report
    library_path = os.path.normpath(library_path) if library_path else library_path
    
    for sp_url in spotify_urls:
        name = url_names.get(sp_url)
        if not name:
            name = f"未命名歌單 ({sp_url.split('/')[-1][:8]}...)"
            
        m3u_file = os.path.join(playlists_path, f"{sanitize_filename(name)}.m3u8")
        is_complete = "Unknown"
        status_text = "未同步"
        
        if os.path.exists(m3u_file):
            comp, missing, total = report.get(m3u_file, (False, 0, 0))
            is_complete = comp
            status_text = "已主動同步" if comp else f"缺 {missing} 首歌"
        
        playlist_data.append({
            "啟用": True,
            "類型": get_playlist_type(sp_url),
            "名稱": name,
            "連結": sp_url,
            "狀態": status_text
        })
        processed_names.add(name)

    # Add other m3u8 files found in the folder that aren't in the config (local playlists)
    for m3u_file in m3u8_files:
        name = os.path.splitext(os.path.basename(m3u_file))[0]
        if name in processed_names or name.startswith('_'): # Skip internal ones like _Unsorted
            continue
            
        comp, missing, total = report.get(m3u_file, (False, 0, 0))
        status_text = "本地完整" if comp else f"缺 {missing} 首歌"
        
        playlist_data.append({
            "啟用": False,
            "類型": "Local",
            "名稱": name,
            "連結": "",
            "狀態": status_text
        })
        
    return playlist_data

class UpdateStats:
    def __init__(self):
        self.playlists_scanned = 0
        self.songs_downloaded = []
        self.playlist_changes = {}
        self.playlist_updates = {}
        self.stop_event = None

def parse_playlist(file_path):
    songs = []
    if not os.path.exists(file_path):
        return songs

    try:
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            lines = [line.strip() for line in f.readlines()]
    except UnicodeDecodeError:
        with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
            lines = [line.strip() for line in f.readlines()]

    if not lines:
        return songs

    # Check if it's a standard M3U playlist
    is_m3u = any('#EXTM3U' in line for line in lines[:5])

    i = 0
    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue

        if is_m3u:
            if line.startswith('#EXTINF:'):
                # The next non-empty, non-comment line should be the file path
                j = i + 1
                while j < len(lines) and (not lines[j] or lines[j].startswith('#')):
                    j += 1
                
                if j < len(lines):
                    file_path_line = lines[j]
                    # Get filename without extension
                    song_name = os.path.splitext(os.path.basename(file_path_line))[0]
                    songs.append(song_name)
                    i = j + 1
                else:
                    i += 1
            else:
                i += 1 # Skip other comments or the header
        else:
            # If not a standard M3U, treat every non-comment line as a song name
            if not line.startswith('#'):
                songs.append(line)
            i += 1
            
    return songs

def unblock_files(directory, log_func):
    """ Removes the 'Zone.Identifier' (Mark of the Web) from files which causes 0x80070005 errors in UWP apps """
    import subprocess
    if os.name == 'nt':
        try:
            # Use powershell to unblock all files in the directory recursively
            cmd = f'Get-ChildItem -Path "{directory}" -Recurse | Unblock-File'
            creationflags = subprocess.CREATE_NO_WINDOW
            subprocess.run(["powershell", "-Command", cmd], capture_output=True, check=False, creationflags=creationflags)
        except: pass

def _resolve_spotube_paths(config):
    library_path = config.get('library_path')
    m4a_subfolder = config.get('spotube_m4a_subfolder', 'm4a')
    mp3_subfolder = config.get('spotube_mp3_subfolder', 'mp3')
    m4a_path = os.path.join(library_path, m4a_subfolder)
    mp3_path = os.path.join(library_path, mp3_subfolder)
    return m4a_path, mp3_path

def _get_m4a_cache_key(m4a_path, mp3_path):
    m4a_pattern = os.path.join(m4a_path, "**", "*.m4a")
    m4a_files = glob.glob(m4a_pattern, recursive=True)
    mp3_norm = os.path.normpath(mp3_path).lower()
    m4a_files = [f for f in m4a_files if not os.path.normpath(f).lower().startswith(mp3_norm)]
    m4a_files.sort()

    cache_str = ""
    for f in m4a_files:
        try:
            cache_str += f"{f}:{os.path.getmtime(f)}\n"
        except Exception:
            cache_str += f"{f}:0\n"
    return hashlib.md5(cache_str.encode('utf-8')).hexdigest(), m4a_files

def _audio_metadata_identity(file_path):
    """Return normalized title/artist metadata for conversion freshness checks."""
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return None

    try:
        audio = MutagenFile(file_path, easy=True)
        if not audio or not audio.tags:
            return None
        title = audio.tags.get('title', [None])[0]
        artist = audio.tags.get('artist', [None])[0]
        if not title and not artist:
            return None
        return (
            tuple(get_normalized_tokens(title or "")),
            tuple(get_normalized_tokens(artist or "")),
        )
    except Exception:
        return None

def _audio_metadata_filename_stem(file_path):
    """Build a stable filename stem from audio title/artist metadata."""
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return None

    try:
        audio = MutagenFile(file_path, easy=True)
        if not audio or not audio.tags:
            return None
        title = (audio.tags.get('title', [None])[0] or "").strip()
        artist = (audio.tags.get('artist', [None])[0] or "").strip()
        if not title:
            return None

        stem = title
        if artist:
            title_tokens = set(get_normalized_tokens(title))
            artist_tokens = set(get_normalized_tokens(artist))
            if not artist_tokens or not artist_tokens <= title_tokens:
                stem = f"{title} - {artist}"
        return _sanitize_metadata_filename(stem)
    except Exception:
        return None

def _sanitize_metadata_filename(name):
    """Sanitize metadata-derived names without stripping meaningful title text."""
    import re

    cleaned = str(name or "").replace('\xa0', ' ').replace('\u200b', '').strip()
    cleaned = re.sub(r'[<>:"/\\|?*]', '_', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip('. -')
    return (cleaned or "Unknown")[:200]

def _metadata_based_mp3_path(src, mp3_path):
    stem = _audio_metadata_filename_stem(src)
    if not stem:
        stem = os.path.splitext(os.path.basename(src))[0]
    return os.path.join(mp3_path, f"{stem}.mp3"), stem

def _move_matching_legacy_mp3(src, legacy_dest, metadata_dest, log_func):
    if os.path.normcase(os.path.abspath(legacy_dest)) == os.path.normcase(os.path.abspath(metadata_dest)):
        return
    if not os.path.exists(legacy_dest):
        return
    if not _converted_mp3_matches_source(src, legacy_dest):
        return

    try:
        if os.path.exists(metadata_dest):
            if _converted_mp3_matches_source(src, metadata_dest):
                os.remove(legacy_dest)
                if log_func:
                    log_func(f"    Renamed metadata MP3 already exists; removed old name: {os.path.basename(legacy_dest)}")
            return

        os.replace(legacy_dest, metadata_dest)
        if log_func:
            log_func(f"    Renamed MP3 by metadata: {os.path.basename(legacy_dest)} -> {os.path.basename(metadata_dest)}")
    except Exception as e:
        if log_func:
            log_func(f"    Could not rename MP3 by metadata: {os.path.basename(legacy_dest)} ({e})")

def _converted_mp3_matches_source(src, dest):
    """Treat an MP3 as stale when readable metadata differs from its M4A source."""
    src_identity = _audio_metadata_identity(src)
    dest_identity = _audio_metadata_identity(dest)
    if not src_identity or not dest_identity:
        return True

    src_title, src_artist = src_identity
    dest_title, dest_artist = dest_identity
    if src_title and dest_title and src_title != dest_title:
        return False
    if src_artist and dest_artist and src_artist != dest_artist:
        return False
    return True

def _source_match_names(src):
    names = []
    filename_stem = os.path.splitext(os.path.basename(src))[0]
    if filename_stem:
        names.append(filename_stem)

    metadata_stem = _audio_metadata_filename_stem(src)
    if metadata_stem and metadata_stem not in names:
        names.append(metadata_stem)

    identity = _audio_metadata_identity(src)
    if identity:
        title_tokens, artist_tokens = identity
        if title_tokens:
            names.append(" ".join(title_tokens))
        if title_tokens and artist_tokens:
            names.append(f"{' '.join(title_tokens)} - {' '.join(artist_tokens)}")

    deduped = []
    seen = set()
    for name in names:
        key = tuple(get_normalized_tokens(name))
        if key and key not in seen:
            seen.add(key)
            deduped.append(name)
    return deduped

def _build_playlist_song_index(playlists_path):
    if not playlists_path or not os.path.exists(playlists_path):
        return {}

    files = glob.glob(os.path.join(playlists_path, "*.m3u8")) + \
            glob.glob(os.path.join(playlists_path, "*.m3u")) + \
            glob.glob(os.path.join(playlists_path, "*.txt"))
    skip_markers = ["_unsorted", "single tracks", "_unsorted_songs", "_removed songs", "已移除"]
    index = {}
    for pl_file in files:
        base = os.path.basename(pl_file).lower()
        if any(marker in base for marker in skip_markers):
            continue
        for song_name in parse_playlist(pl_file):
            tokens = tuple(get_normalized_tokens(song_name))
            if tokens:
                index.setdefault(tokens, song_name)
            if ' - ' in song_name:
                title = song_name.split(' - ', 1)[0].strip()
                tokens = tuple(get_normalized_tokens(title))
                if tokens:
                    index.setdefault(tokens, song_name)
    return index

def _matches_playlist_index(src, playlist_index):
    if not playlist_index:
        return False
    for name in _source_match_names(src):
        tokens = tuple(get_normalized_tokens(name))
        if tokens in playlist_index:
            return True
        token_set = set(tokens)
        if token_set:
            for playlist_tokens in playlist_index:
                playlist_set = set(playlist_tokens)
                min_size = min(len(token_set), len(playlist_set))
                if min_size and len(token_set & playlist_set) / min_size >= 0.9:
                    return True
    return False

def _find_existing_mp3_for_source(src, mp3_index, metadata_index=None):
    for name in _source_match_names(src):
        found = find_song_exact_format(name, 'mp3', mp3_index)
        if not found and metadata_index:
            found = find_song_in_library(name, mp3_index, metadata_index=metadata_index)
            if found and not found.lower().endswith('.mp3'):
                found = None
        if found and os.path.exists(found) and _converted_mp3_matches_source(src, found):
            return found
    return None

def convert_spotube_m4a_to_mp3(config, log_func, pause_event=None, stop_event=None, progress_cb=None, status_cb=None, source_files=None):
    """Convert Spotube M4A files to MP3, skipping cached or unmatched files."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    from core.audio_converter import convert_audio_file
    from core.ffmpeg_installer import ensure_ffmpeg_available, get_ffmpeg_path
    from utils.config import get_data_file
    from utils.i18n import _

    m4a_path, mp3_path = _resolve_spotube_paths(config)
    if not os.path.exists(m4a_path):
        os.makedirs(m4a_path, exist_ok=True)
        log_func(f" -> Creating M4A folder: {m4a_path}")

    if not ensure_ffmpeg_available(config, log_func):
        log_func(" -> FFmpeg unavailable. Skip M4A -> MP3 conversion.")
        return 0, 0, 0

    os.makedirs(mp3_path, exist_ok=True)

    if source_files is not None:
        m4a_files = sorted({os.path.normpath(f) for f in source_files if f and f.lower().endswith('.m4a')})
        current_cache_key = None
    else:
        current_cache_key, m4a_files = _get_m4a_cache_key(m4a_path, mp3_path)

    if not m4a_files:
        log_func(" -> No M4A files found for conversion.")
        return 0, 0, 0

    search_pattern = os.path.join(config.get('library_path'), "**", "*")
    all_files = [f for f in glob.glob(search_pattern, recursive=True) if os.path.isfile(f)]
    mp3_files = [f for f in all_files if f.lower().endswith('.mp3')]
    mp3_index = build_library_index(mp3_files)
    metadata_index = build_metadata_index(mp3_files)
    playlist_index = _build_playlist_song_index(config.get('playlists_path')) if config.get('spotube_convert_matched_only', False) else None

    tasks = []
    skipped = 0
    for src in m4a_files:
        if os.path.normpath(src).lower().startswith(os.path.normpath(mp3_path).lower()):
            continue

        base = os.path.splitext(os.path.basename(src))[0]
        legacy_dest = os.path.join(mp3_path, f"{base}.mp3")
        dest, name = _metadata_based_mp3_path(src, mp3_path)
        _move_matching_legacy_mp3(src, legacy_dest, dest, log_func)
        tasks.append((src, dest, name))

    total_tasks = len(tasks)
    if total_tasks == 0:
        log_func(" -> No M4A files found for conversion.")
        return 0, 0, 0

    if status_cb:
        for i, (_, _, name) in enumerate(tasks):
            status_cb(i, _('conv_status_queued'), name)

    to_convert = []
    for i, (src, dest, name) in enumerate(tasks):
        if playlist_index is not None and not _matches_playlist_index(src, playlist_index):
            skipped += 1
            if status_cb:
                status_cb(i, _('conv_status_skipped'), f"{name} (not in playlist)")
            continue

        existing_mp3 = _find_existing_mp3_for_source(src, mp3_index, metadata_index)
        if existing_mp3:
            skipped += 1
            if status_cb:
                status_cb(i, _('conv_status_skipped'), name)
            continue

        if os.path.exists(dest):
            try:
                if os.path.getmtime(dest) >= os.path.getmtime(src) and _converted_mp3_matches_source(src, dest):
                    skipped += 1
                    if status_cb:
                        status_cb(i, _('conv_status_skipped'), name)
                    continue
            except Exception:
                pass

        to_convert.append((i, src, dest, name))

    processed = skipped
    if progress_cb:
        progress_cb(processed, total_tasks)

    def _wait_if_paused():
        if not pause_event:
            return True
        while not pause_event.is_set():
            if stop_event and stop_event.is_set():
                return False
            pause_event.wait(0.2)
        return not (stop_event and stop_event.is_set())

    def _worker_count():
        try:
            return max(1, int(config.get('spotube_convert_workers', 4)))
        except Exception:
            return 4

    lock = threading.Lock()
    converted = 0

    def _convert_one(i, src, dest, name):
        if stop_event and stop_event.is_set() or not _wait_if_paused():
            return "cancel"
        if status_cb:
            status_cb(i, _('conv_status_working'), name)
        ok = convert_audio_file(src, dest, 'mp3', log_func, get_ffmpeg_path(config))
        return "ok" if ok else "fail"

    if to_convert:
        log_func(f" -> Conversion workers: {_worker_count()}")

    with ThreadPoolExecutor(max_workers=_worker_count()) as ex:
        future_meta = {
            ex.submit(_convert_one, i, src, dest, name): (i, name)
            for i, src, dest, name in to_convert
            if not (stop_event and stop_event.is_set())
        }
        for future in as_completed(future_meta):
            result = "fail"
            try:
                result = future.result()
            except Exception:
                result = "fail"

            idx, name = future_meta[future]
            if status_cb:
                if result == "ok":
                    status_cb(idx, _('conv_status_done'), name)
                elif result == "cancel":
                    status_cb(idx, _('conv_status_cancelled'), name)
                else:
                    status_cb(idx, _('conv_status_failed'), name)

            with lock:
                processed += 1
                if result == "ok":
                    converted += 1
                else:
                    skipped += 1
                if progress_cb:
                    progress_cb(processed, total_tasks)
                if processed % 10 == 0 or processed == total_tasks:
                    log_func(f" -> Conversion progress: {processed}/{total_tasks}")

            if stop_event and stop_event.is_set():
                log_func(" -> Conversion cancelled.")
                break

    if source_files is None and current_cache_key:
        try:
            with open(get_data_file('m4a_cache.json'), 'w', encoding='utf-8') as f:
                json.dump({'cache_key': current_cache_key}, f)
        except Exception:
            pass

    log_func(f" -> Spotube conversion done: {converted} converted, {skipped} skipped")
    return converted, skipped, total_tasks

def _resolve_playlist_entry_path(entry, playlists_path):
    from urllib.parse import unquote
    # Decode URI-encoded paths (e.g., %E5%A4%A2%E6%83%B3 -> 夢想)
    entry = unquote(entry)
    if os.path.isabs(entry):
        return os.path.normpath(entry)
    return os.path.normpath(os.path.join(playlists_path, entry))

def prune_missing_from_playlists(config, log_func, pause_event=None, stop_event=None):
    """Remove missing audio entries from playlist files."""
    playlists_path = config.get('playlists_path')
    library_path = config.get('library_path')
    if not playlists_path or not os.path.exists(playlists_path):
        return 0, 0

    # Build library index for non-M3U simple lists
    search_pattern = os.path.join(library_path, "**", "*")
    all_files = glob.glob(search_pattern, recursive=True)
    audio_files_cache = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]
    library_index = build_library_index(audio_files_cache)

    pl_files = glob.glob(os.path.join(playlists_path, "*.m3u8")) + \
               glob.glob(os.path.join(playlists_path, "*.m3u"))

    total_removed = 0
    total_files = 0
    skip_markers = ["_unsorted", "single tracks", "_unsorted_songs"]

    for pl_file in pl_files:
        if stop_event and stop_event.is_set():
            log_func(" -> Prune cancelled.")
            break
        if pause_event:
            pause_event.wait()
        base = os.path.basename(pl_file).lower()
        if any(marker in base for marker in skip_markers):
            continue
        total_files += 1
        removed = 0
        try:
            try:
                with open(pl_file, 'r', encoding='utf-8-sig') as f:
                    raw_lines = [line.rstrip('\r\n') for line in f.readlines()]
            except UnicodeDecodeError:
                with open(pl_file, 'r', encoding='gbk', errors='ignore') as f:
                    raw_lines = [line.rstrip('\r\n') for line in f.readlines()]

            if not raw_lines:
                continue

            is_m3u = any('#EXTM3U' in line for line in raw_lines[:5])
            output = []

            i = 0
            while i < len(raw_lines):
                line = raw_lines[i].strip()
                if not line:
                    i += 1
                    continue

                if is_m3u and line.startswith('#EXTINF:'):
                    j = i + 1
                    while j < len(raw_lines) and (not raw_lines[j].strip() or raw_lines[j].startswith('#')):
                        j += 1
                    if j < len(raw_lines):
                        path_line = raw_lines[j].strip()
                        resolved = _resolve_playlist_entry_path(path_line, playlists_path)
                        if os.path.exists(resolved):
                            output.append(line)
                            output.append(path_line)
                        else:
                            removed += 1
                        i = j + 1
                    else:
                        i += 1
                    continue

                if is_m3u:
                    if line.startswith('#'):
                        output.append(line)
                    else:
                        resolved = _resolve_playlist_entry_path(line, playlists_path)
                        if os.path.exists(resolved):
                            output.append(line)
                        else:
                            removed += 1
                    i += 1
                else:
                    # Non-m3u: treat lines as song names and validate via library index
                    if line.startswith('#'):
                        i += 1
                        continue
                    if find_song_in_library(line, library_index):
                        output.append(line)
                    else:
                        removed += 1
                    i += 1

            if is_m3u:
                has_header = any(l.startswith('#EXTM3U') for l in output)
                if not has_header:
                    output.insert(0, "#EXTM3U")

            if removed > 0:
                with open(pl_file, 'w', encoding='utf-8-sig', newline='') as f:
                    for out_line in output:
                        f.write(f"{out_line}\r\n")
                log_func(f" -> Removed {removed} missing entries from {os.path.basename(pl_file)}")
            total_removed += removed
        except Exception as e:
            log_func(f"  ? Error pruning {os.path.basename(pl_file)}: {e}")

    return total_removed, total_files

def get_normalized_tokens(text):
    import re
    from zhconv import convert

    # 1. Convert to lowercase
    text = str(text).lower()
    
    # 1.5 Remove spaces between Chinese/Japanese characters to ensure "你在 不在" matches "你在不在"
    # This also helps with Japanese kana
    text = re.sub(r'(?<=[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff])\s+(?=[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff])', '', text)

    # 2. Convert Chinese characters to Simplified Chinese, but preserve Japanese
    # Only apply zhconv to Chinese characters, not Japanese kana
    try:
        # Split text to preserve Japanese characters
        import re as regex
        # This regex separates Chinese characters from other characters
        def convert_chinese_only(match):
            chinese_text = match.group(0)
            try:
                return convert(chinese_text, 'zh-cn')
            except:
                return chinese_text
        
        # Apply conversion only to Chinese characters (CJK Unified Ideographs)
        text = regex.sub(r'[\u4e00-\u9fff]', convert_chinese_only, text)
        
        # 2.1 Manual overrides for common Traditional/Simplified pairs that zhconv might miss
        mapping = {
            '著': '着',
            '妳': '你',
            '牠': '它',
            '祂': '他',
            '閒': '闲'
        }
        for t_char, s_char in mapping.items():
            text = text.replace(t_char, s_char)
    except:
        # If conversion fails, keep original text
        pass

    # 2.4 Map common English artist names to Chinese for better matching.
    # Built-in aliases can be extended by adding a data/artist_aliases.json file.
    for eng_name, chn_name in get_artist_aliases().items():
        try:
            normalized_alias = convert(chn_name, 'zh-cn')
        except Exception:
            normalized_alias = chn_name
        text = re.sub(r'\b' + re.escape(eng_name) + r'\b', normalized_alias, text, flags=re.IGNORECASE)

    # 2.5 Remove "E" prefix artifact (common in Spotify scrapes)
    # Improved: work at word boundaries, not just start of string
    text = re.sub(r'(?:^|(?<=[^a-z0-9]))e(?=[a-z\u4e00-\u9fff\u3040-\u30ff])', '', text)

    # 2.6 Remove common music title noise phrases
    noise_phrases = [
        r'全新單曲', r'單曲', r'官方完整版', r'官方', r'完整版', 
        r'高清', r'動態歌詞版', r'歌詞版', r'官方版', r'全新',
        r'music video', r'official video', r'official music video', r'video', r'loop', r'lyrics'
    ]
    for phrase in noise_phrases:
        text = re.sub(phrase, ' ', text, flags=re.IGNORECASE)

    # 3. Standardize artist separators and common terms to spaces
    # Handles 'feat.', 'ft.', 'vs', 'vs.', '&', ',', ' x '
    text = re.sub(r'\s*(feat|ft|vs)\.?\s*|\s*[&,x]\s*', ' ', text)

    # 4. Remove content in brackets for common markers
    # Enhanced: remove any brackets containing these keywords anywhere inside
    # Added support for full-width brackets: （ ） ［ ］
    bracket_keywords = r'live|remix|mv|official|lyrics? video|lyric video|動態歌詞版|歌詞版|music video|video|loop'
    text = re.sub(r"[\(\[【（［][^\)\]】）］]*(?:" + bracket_keywords + r")[^\)\]】）］]*[\)\]】）］]", " ", text, flags=re.IGNORECASE)
    
    # For other brackets, just remove the brackets but keep the content (including full-width)
    text = re.sub(r"[\(\[【（［]", " ", text)
    text = re.sub(r"[\)\]】）］]", " ", text)

    # 5. Add spaces between Latin letters and Chinese characters to improve tokenization
    # This helps separate "BIDO曾愷妤" into "BIDO 曾愷妤"
    text = re.sub(r'([a-zA-Z])([\u4e00-\u9fff])', r'\1 \2', text)
    text = re.sub(r'([\u4e00-\u9fff])([a-zA-Z])', r'\1 \2', text)

    # 6. Replace all non-alphanumeric characters (excluding Chinese and Japanese) with spaces
    # This will also handle underscores and other symbols
    # Special fix: handle dash between words without spaces (Artist-Title)
    text = re.sub(r'([a-z\u4e00-\u9fff\u3040-\u30ff])(-)(?=[a-z\u4e00-\u9fff\u3040-\u30ff])', r'\1 \2 ', text, flags=re.IGNORECASE)
    
    # Include Japanese Hiragana (\u3040-\u309f) and Katakana (\u30a0-\u30ff)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+", " ", text)

    # 7. Split into tokens, remove empty strings, deduplicate and sort
    return sorted(list(set([t for t in text.split() if t])))

def build_library_index(audio_files):
    index = {}
    for file_path in audio_files:
        filename = os.path.basename(file_path)
        name_no_ext = os.path.splitext(filename)[0]
        # The key is a tuple of sorted tokens, making it order-independent
        tokens_tuple = tuple(get_normalized_tokens(name_no_ext))
        if tokens_tuple:
            # Store list of files for collision handling (duplicates)
            if tokens_tuple not in index:
                index[tokens_tuple] = []
            index[tokens_tuple].append(file_path)
    return index



def build_metadata_index(audio_files, log_func=None):
    """
    Reads metadata from all files and builds an index:
    tuple(normalized_title_tokens) -> list[file_path]
     This is an O(N) operation to be done once, instead of O(N) per missing song.
    """
    try:
        from mutagen.flac import FLAC
        from mutagen.easyid3 import EasyID3
        from mutagen.id3 import ID3
        from mutagen.mp4 import MP4
        from pathlib import Path
    except ImportError:
        return {}

    index = {}
    count = 0
    
    # Only scan if check enabled
    if not audio_files:
        return index

    for file_path in audio_files:
        try:
            if not os.path.exists(file_path): continue
            
            file_ext = Path(file_path).suffix.lower()
            metadata_title = None
            
            if file_ext == '.flac':
                try:
                    audio = FLAC(file_path)
                    metadata_title = audio.get('TITLE', [None])[0]
                except: pass
            elif file_ext in ['.mp3', '.mp2', '.mp1']:
                try:
                    try:
                        audio = EasyID3(file_path)
                        metadata_title = audio.get('title', [None])[0]
                    except:
                        audio = ID3(file_path)
                        if 'TIT2' in audio:
                            metadata_title = str(audio['TIT2'])
                except: pass
            elif file_ext in ['.m4a', '.mp4']:
                try:
                    audio = MP4(file_path)
                    metadata_title = audio.get('\xa9nam', [None])[0]
                except: pass
            
            if metadata_title:
                tokens = tuple(get_normalized_tokens(metadata_title))
                if tokens:
                    if tokens not in index:
                        index[tokens] = []
                    index[tokens].append(file_path)
                    count += 1
                        
        except Exception:
            continue
            
    if log_func and count > 0:
        pass 
        
    return index

def find_song_in_library(song_name, library_source, metadata_index=None, artist=None, target_duration=None):
    """ 
    Tries to find a song using either a pre-built library index (dict) or a file list (list). 
    Supports verifying artist if provided (fuzzy match on metadata or path).
    Supports duration verification if target_duration is provided.
    """
    query_tokens = tuple(get_normalized_tokens(song_name))
    if not query_tokens:
        return None
    
    # If explicit artist provided, we use it.
    # Otherwise, try to extract from "Artist - Title" format in the query itself.
    target_artist = artist
    target_artist_options = [artist] if artist else []

    title_part = song_name
    title_token_candidates = []
    if ' - ' in song_name:
         parts = song_name.split(' - ', 1)
         if len(parts) == 2:
             left_part = parts[0].strip()
             right_part = parts[1].strip()
             if not target_artist:
                 # Spotify playlist rows are saved as "Title - Artist", while older
                 # paths in the app may still use "Artist - Title". The Spotify
                 # sync path now writes Title - Artist, so only the right side is
                 # valid artist evidence here.
                 target_artist_options.append(right_part)
             title_part = left_part
             candidate_tokens = tuple(get_normalized_tokens(left_part))
             if candidate_tokens:
                 title_token_candidates.append(candidate_tokens)
    
    title_tokens = tuple(get_normalized_tokens(title_part))
    if title_tokens and title_tokens not in title_token_candidates:
        title_token_candidates.insert(0, title_tokens)
    if query_tokens and query_tokens not in title_token_candidates:
        title_token_candidates.append(query_tokens)
    
    # Helper to check if a candidate file matches the artist
    def verify_artist(file_path, target_artist):
        if not target_artist: return True # No artist to check -> accept match
        
        target_tokens = set(get_normalized_tokens(target_artist))
        if not target_tokens: return True
        
        # 1. Check Metadata
        try:
            from mutagen.flac import FLAC
            from mutagen.easyid3 import EasyID3
            from mutagen.mp4 import MP4
            
            meta_artist = None
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.flac':
                a = FLAC(file_path)
                meta_artist = a.get('ARTIST', [None])[0]
            elif ext == '.mp3':
                a = EasyID3(file_path)
                meta_artist = a.get('artist', [None])[0]
            elif ext == '.m4a':
                a = MP4(file_path)
                meta_artist = a.get('\xa9ART', [None])[0]
                
            if meta_artist:
                meta_tokens = set(get_normalized_tokens(meta_artist))
                # Intersection check
                if target_tokens & meta_tokens:
                    return True
        except: pass
        
        # 2. Check File Path (FolderName often is Artist, or Filename is Artist - Title)
        # e.g. Music/Artist Name/Song.mp3 OR Music/Artist - Song.mp3
        path_str = os.path.normpath(file_path).lower()
        path_parts = path_str.split(os.sep)
        
        # Check standard parts (folders)
        for part in path_parts:
            part_tokens = set(get_normalized_tokens(part))
            if target_tokens & part_tokens:
                 return True
                 
        return False

    # Helper to check duration match
    def verify_duration(file_path, target_duration):
        if not target_duration or target_duration <= 0: return True
        
        try:
            from mutagen import File as MutagenFile
            audio = MutagenFile(file_path)
            if audio and audio.info:
                file_duration = audio.info.length
                # Allow 12 seconds difference (to account for different versions/ads/intros)
                if abs(file_duration - target_duration) <= 12:
                    return True
        except: pass
        return False

    candidates = []

    # Check if library_source is a dictionary (index) or list (file list)
    if isinstance(library_source, dict):
        # Flatten logic helper
        def collect_candidates(key_tokens):
            if not key_tokens: return
            paths = library_source.get(key_tokens)
            if paths:
                # Handle both new list format and legacy string format just in case
                if isinstance(paths, list):
                    candidates.extend(paths)
                else:
                    candidates.append(paths)

        # 1. Exact full match
        collect_candidates(query_tokens)
        
        # 2. Title-only match (renamed files)
        if not candidates:
            for candidate_tokens in title_token_candidates:
                if candidate_tokens == query_tokens:
                    continue
                collect_candidates(candidate_tokens)
                if candidates:
                    break
        
        # 3. Flexible matching (simplified: check overlap between search tokens and file tokens)
        if not candidates:
            fuzzy_sources = [tokens for tokens in title_token_candidates if tokens != query_tokens] or [query_tokens]
            for fuzzy_source in fuzzy_sources:
                if candidates:
                    break
                if not fuzzy_source:
                    continue
                title_set = set(fuzzy_source)
                for index_tokens, paths in library_source.items():
                    if not index_tokens: continue
                    index_set = set(index_tokens)
                    
                    # Calculate overlap: intersection / smaller set size
                    overlap = len(title_set & index_set)
                    min_size = min(len(title_set), len(index_set))
                    
                    # STRICTER MATCHING: Higher thresholds to reduce false positives
                    # Small sets (1-3 tokens): require 100% match
                    # Medium sets (4-5 tokens): require 90% match  
                    # Large sets (6+ tokens): require 80% match
                    if min_size <= 3:
                        threshold = 1.0  # 100% for very small sets
                    elif min_size <= 5:
                        threshold = 0.9  # 90% for small-medium sets
                    else:
                        threshold = 0.8  # 80% for larger sets
                    
                    if min_size > 0 and overlap / min_size >= threshold:
                        # Additional check: must have at least 2 matching tokens OR 100% match
                        # This prevents single-word matches like "love" matching wrong songs
                        if overlap >= 2 or (overlap == 1 and min_size == 1):
                            if isinstance(paths, list): candidates.extend(paths)
                            else: candidates.append(paths)

    elif isinstance(library_source, list):
        # Legacy List Mode
        # Fallback to O(n) search
        for file_path in library_source:
            filename = os.path.basename(file_path)
            name_no_ext = os.path.splitext(filename)[0]
            file_tokens = tuple(get_normalized_tokens(name_no_ext))
            
            if not file_tokens: continue
            
            if file_tokens == query_tokens:
                candidates.append(file_path)
            elif any(file_tokens == candidate_tokens for candidate_tokens in title_token_candidates if candidate_tokens != query_tokens):
                candidates.append(file_path)
            elif title_token_candidates:
                # Flexible matching with overlap
                for candidate_tokens in title_token_candidates:
                    if candidate_tokens == query_tokens:
                        continue
                    title_set = set(candidate_tokens)
                    file_set = set(file_tokens)
                    overlap = len(title_set & file_set)
                    min_size = min(len(title_set), len(file_set))
                    
                    # STRICTER MATCHING: Higher thresholds to reduce false positives
                    if min_size <= 3:
                        threshold = 1.0  # 100% for very small sets
                    elif min_size <= 5:
                        threshold = 0.9  # 90% for small-medium sets
                    else:
                        threshold = 0.8  # 80% for larger sets
                        
                    if min_size > 0 and overlap / min_size >= threshold:
                        # Additional check: must have at least 2 matching tokens OR 100% match
                        if overlap >= 2 or (overlap == 1 and min_size == 1):
                            candidates.append(file_path)
                            break

    # 3. Metadata Index Lookup (Pass 2)
    current_best_candidate = None
    
    if metadata_index:
        # Check full name vs metadata title
        res_paths = metadata_index.get(query_tokens)
        if res_paths: 
             if isinstance(res_paths, list): candidates.extend(res_paths)
             else: candidates.append(res_paths)
        
        # Check title vs metadata title. Support both "Artist - Title" and
        # "Title - Artist" because Spotube/Spotify sources are not consistent.
        for candidate_tokens in title_token_candidates:
            if candidate_tokens == query_tokens:
                continue
            res_paths = metadata_index.get(candidate_tokens)
            if res_paths: 
                if isinstance(res_paths, list): candidates.extend(res_paths)
                else: candidates.append(res_paths)
                break
        
        # Fuzzy/Subset Check on Metadata Index
        if not candidates:
            fuzzy_sources = [tokens for tokens in title_token_candidates if tokens != query_tokens] or [query_tokens]
            for fuzzy_tokens in fuzzy_sources:
                if candidates:
                    break
                if not fuzzy_tokens:
                    continue
                for meta_tokens, paths in metadata_index.items():
                    if not meta_tokens: continue
                    is_match = False
                    
                    # Case A: Query is subset of Metadata
                    if len(fuzzy_tokens) > 0 and len(meta_tokens) >= len(fuzzy_tokens):
                        if all(token in meta_tokens for token in fuzzy_tokens):
                             coverage = len(fuzzy_tokens) / len(meta_tokens)
                             if coverage >= 0.3: is_match = True

                    # Case B: Metadata is subset of Query
                    elif len(meta_tokens) > 0 and len(fuzzy_tokens) >= len(meta_tokens):
                        if all(token in fuzzy_tokens for token in meta_tokens):
                             coverage = len(meta_tokens) / len(fuzzy_tokens)
                             if coverage >= 0.6: is_match = True
                    
                    if is_match:
                         if isinstance(paths, list): candidates.extend(paths)
                         else: candidates.append(paths)

    # --- FINAL SELECTION ---
    if not candidates:
        return None
    
    # Remove duplicates while preserving order
    unique_candidates = []
    seen = set()
    for c in candidates:
        if c not in seen:
            unique_candidates.append(c)
            seen.add(c)
    
    # If artist is provided, filter or rank candidates
    target_artist_options = [a for a in target_artist_options if a]
    if target_artist_options:
        verified_candidates = []
        for c in unique_candidates:
            if any(verify_artist(c, candidate_artist) for candidate_artist in target_artist_options):
                # Also verify duration if available
                if verify_duration(c, target_duration):
                    verified_candidates.append(c)
        
        if verified_candidates:
            return verified_candidates[0] # Return best verified match
        else:
            # If we had candidates but none passed artist check, 
            # we DON'T return a random song by the same artist anymore if threshold is high.
            # But we check for duration mismatch as a hard reject.
            if target_duration:
                # If we have a duration target, we MUST match it within reason
                pass
            return None # Fail safe
            
    # If no artist provided but we have a duration, use it
    if target_duration:
        duration_verified = [c for c in unique_candidates if verify_duration(c, target_duration)]
        if duration_verified:
            return duration_verified[0]
        return None

    # Default: Return first candidate found (only if no artist/duration was specified)
    return unique_candidates[0]

def _search_by_metadata(title_tokens, file_list):
    """Helper function to search files by metadata title - LEGACY SLOW FALLBACK"""
    try:
        from mutagen.flac import FLAC
        from mutagen.easyid3 import EasyID3
        from mutagen.id3 import ID3
        from mutagen.mp4 import MP4
        from pathlib import Path
        
        # Search by metadata title
        for file_path in file_list:
            try:
                file_ext = Path(file_path).suffix.lower()
                metadata_title = None
                
                if file_ext == '.flac':
                    audio = FLAC(file_path)
                    metadata_title = audio.get('TITLE', [None])[0]
                elif file_ext in ['.mp3', '.mp2', '.mp1']:
                    try:
                        audio = EasyID3(file_path)
                        metadata_title = audio.get('title', [None])[0]
                    except:
                        try:
                            audio = ID3(file_path)
                            if 'TIT2' in audio:
                                metadata_title = str(audio['TIT2'])
                        except:
                            continue
                elif file_ext in ['.m4a', '.mp4']:
                    audio = MP4(file_path)
                    metadata_title = audio.get('\xa9nam', [None])[0]
                
                if metadata_title:
                    # Compare normalized tokens - use subset matching for flexibility
                    metadata_tokens = tuple(get_normalized_tokens(metadata_title))
                    
                    # First try exact match
                    if metadata_tokens == title_tokens:
                        return file_path
                    
                    # Then try subset matching - all search tokens should be in metadata tokens
                    if len(title_tokens) > 0:
                        if all(token in metadata_tokens for token in title_tokens):
                            # Additional check: ensure at least 30% of metadata tokens are covered
                            # to avoid false positives with very short search terms
                            coverage = len(title_tokens) / len(metadata_tokens) if len(metadata_tokens) > 0 else 0
                            if coverage >= 0.3:  # At least 30% coverage
                                return file_path
                        
            except Exception:
                continue  # Skip files that can't be read
                
    except ImportError:
        pass  # mutagen not available, skip metadata search
        
    return None

def find_song_prefer_flac(song_name, library_source, target_duration=None):
    """ Find song in library, preferring FLAC over other formats. Supports duration check. """
    query_tokens = tuple(get_normalized_tokens(song_name))
    if not query_tokens:
        return None
    
    # Helper for duration check
    def verify_duration(file_path, target_duration):
        if not target_duration or target_duration <= 0: return True
        try:
            from mutagen import File as MutagenFile
            audio = MutagenFile(file_path)
            if audio and audio.info:
                file_duration = audio.info.length
                if abs(file_duration - target_duration) <= 12:
                    return True
        except: pass
        return False

    found_files = []
    
    # Check if library_source is a dictionary (index) or list (file list)
    if isinstance(library_source, dict):
        # 1. FAST PATH: Exact full match
        paths = library_source.get(query_tokens)
        if paths:
            found_files = list(paths) if isinstance(paths, list) else [paths]
    
    elif isinstance(library_source, list):
        # 2. SLOW PATH: Linear Scan
        audio_files = library_source
        for file_path in audio_files:
            filename = os.path.basename(file_path)
            name_no_ext = os.path.splitext(filename)[0]
            file_tokens = tuple(get_normalized_tokens(name_no_ext))
            
            if not file_tokens: continue
            
            is_match = False
            if file_tokens == query_tokens:
                is_match = True
            else:
                # Check overlap with higher thresholds to reduce false positives
                query_set = set(query_tokens)
                file_set = set(file_tokens)
                overlap = len(query_set & file_set)
                min_size = min(len(query_set), len(file_tokens))
                
                if min_size <= 3:
                    threshold = 1.0  # 100% for very small sets
                elif min_size <= 5:
                    threshold = 0.9  # 90% for small-medium sets
                else:
                    threshold = 0.8  # 80% for larger sets
                    
                if min_size > 0 and overlap / min_size >= threshold:
                    # Additional check: at least 2 tokens match OR 100% match
                    if overlap >= 2 or (overlap == 1 and min_size == 1):
                        is_match = True
            
            if is_match:
                found_files.append(file_path)
    
    # 3. Fuzzy match fallback for Dictionary Index
    if not found_files and isinstance(library_source, dict):
        query_set = set(query_tokens)
        for index_tokens, paths in library_source.items():
            if not index_tokens: continue
            index_set = set(index_tokens)
            overlap = len(query_set & index_set)
            min_size = min(len(query_set), len(index_tokens))
            
            if min_size <= 3:
                threshold = 1.0  # 100% for very small sets
            elif min_size <= 5:
                threshold = 0.9  # 90% for small-medium sets
            else:
                threshold = 0.8  # 80% for larger sets
                
            if min_size > 0 and overlap / min_size >= threshold:
                # Additional check: at least 2 tokens match
                if overlap >= 2:
                    if isinstance(paths, list): found_files.extend(paths)
                    else: found_files.append(paths)
    
    if not found_files:
        return None
        
    
    # --- Filter by Duration if requested ---
    if target_duration:
        found_files = [f for f in found_files if verify_duration(f, target_duration)]
    
    if not found_files:
        return None
        
    # Prefer FLAC first
    for file_path in found_files:
        if file_path.lower().endswith('.flac'):
            return file_path
    
    # Then return any other format
    return found_files[0]

def find_song_simple_match(song_name, target_extension, library_source):
    """
    Simple filename matching for Spotube downloads.
    Uses the same tokenization as build_library_index for proper index matching.
    
    Args:
        song_name: Track name from Spotify (format: "Title - Artist")
        target_extension: File extension to match (e.g., '.mp3')
        library_source: Dictionary index of audio files (token_tuple -> paths)
    
    Returns:
        Path to matching file, or None if not found
    """
    target_ext = target_extension.lower()
    if not target_ext.startswith('.'):
        target_ext = '.' + target_ext
    
    # Build query tokens using same method as index
    query_tokens = tuple(get_normalized_tokens(song_name))
    
    # Extract title only for fallback matching
    title_only = None
    title_tokens = None
    artist_tokens = None
    if ' - ' in song_name:
        title_only, artist_part = [part.strip() for part in song_name.split(' - ', 1)]
        title_tokens = tuple(get_normalized_tokens(title_only))
        artist_tokens = tuple(get_normalized_tokens(artist_part))
    
    best_match = None
    best_score = 0
    
    if isinstance(library_source, dict):
        # Fast path: direct token lookup in index
        if query_tokens and query_tokens in library_source:
            paths = library_source[query_tokens]
            if isinstance(paths, list):
                for file_path in paths:
                    if file_path.lower().endswith(target_ext):
                        return file_path
            elif paths.lower().endswith(target_ext):
                return paths
        
        # Fallback: iterate and check filename
        for index_tokens, paths in library_source.items():
            # Get all paths that match the target extension
            if isinstance(paths, list):
                matching_paths = [p for p in paths if p.lower().endswith(target_ext)]
                if not matching_paths:
                    continue
                file_path = matching_paths[0]
            else:
                if not paths.lower().endswith(target_ext):
                    continue
                file_path = paths
            
            # Get filename without extension
            filename = os.path.basename(file_path)
            name_no_ext = os.path.splitext(filename)[0]
            file_tokens = tuple(get_normalized_tokens(name_no_ext))
            
            # Exact token match
            if query_tokens == file_tokens:
                return file_path
            
            # Title-only match (handles Chinese/English artist name differences)
            if title_only:
                # STRICT: Check if ALL title tokens are in file tokens with high threshold
                if title_tokens:
                    title_set = set(title_tokens)
                    file_set = set(file_tokens)
                    artist_set = set(artist_tokens or ())
                    
                    # All title tokens must be present in file tokens
                    if title_set <= file_set and (not artist_set or artist_set & file_set):
                        return file_path
                    
                    # OR: At least 80% of title tokens match AND longest token matches
                    # This prevents "Fish" matching to "Can You Feel The Love Tonight"
                    common = title_set & file_set
                    if len(title_set) > 0:
                        title_match_ratio = len(common) / len(title_set)
                        # Must have at least 80% title coverage
                        if title_match_ratio >= 0.8:
                            # Additional check: longest title token must match
                            longest_title = max(title_set, key=len) if title_set else None
                            if longest_title and longest_title in file_set and (not artist_set or artist_set & file_set):
                                return file_path
            
            # Partial token match (for fuzzy matching) - STRICT threshold
            if query_tokens and file_tokens:
                query_set = set(query_tokens)
                file_set = set(file_tokens)
                title_set = set(title_tokens or ())
                artist_set = set(artist_tokens or ())
                common = query_set & file_set
                min_size = min(len(query_set), len(file_set))
                
                if min_size > 0:
                    match_ratio = len(common) / min_size
                    # Require at least 80% match for fuzzy matching
                    if match_ratio >= 0.8:
                        if title_set and not (title_set & file_set):
                            continue
                        if artist_set and not (artist_set & file_set):
                            continue
                        # Additional check: longest query token must match
                        longest_query = max(query_set, key=len) if query_set else None
                        if longest_query and longest_query in file_set:
                            if len(common) > best_score:
                                best_score = len(common)
                                best_match = file_path
    
    elif isinstance(library_source, list):
        # Legacy list mode - build tokens on the fly
        for file_path in library_source:
            if not file_path.lower().endswith(target_ext):
                continue
            
            filename = os.path.basename(file_path)
            name_no_ext = os.path.splitext(filename)[0]
            file_tokens = tuple(get_normalized_tokens(name_no_ext))
            
            # Exact token match
            if query_tokens == file_tokens:
                return file_path
            
            # Title-only match (STRICT)
            if title_only and title_tokens:
                title_set = set(title_tokens)
                file_set = set(file_tokens)
                artist_set = set(artist_tokens or ())
                
                # All title tokens must be present
                if title_set <= file_set and (not artist_set or artist_set & file_set):
                    return file_path
                
                # OR: 80% coverage with longest token verification
                common = title_set & file_set
                if len(title_set) > 0:
                    match_ratio = len(common) / len(title_set)
                    if match_ratio >= 0.8:
                        longest_title = max(title_set, key=len) if title_set else None
                        if longest_title and longest_title in file_set and (not artist_set or artist_set & file_set):
                            return file_path
            
            # Partial token match (STRICT threshold)
            if query_tokens and file_tokens:
                query_set = set(query_tokens)
                file_set = set(file_tokens)
                title_set = set(title_tokens or ())
                artist_set = set(artist_tokens or ())
                common = query_set & file_set
                min_size = min(len(query_set), len(file_set))
                
                if min_size > 0:
                    match_ratio = len(common) / min_size
                    if match_ratio >= 0.8:
                        if title_set and not (title_set & file_set):
                            continue
                        if artist_set and not (artist_set & file_set):
                            continue
                        longest_query = max(query_set, key=len) if query_set else None
                        if longest_query and longest_query in file_set:
                            if len(common) > best_score:
                                best_score = len(common)
                                best_match = file_path
    
    return best_match

def find_song_exact_format(song_name, target_extension, library_source):
    """ 
    Find song in library that strictly matches the target extension (e.g., '.mp3', '.flac')
    Returns the path if found, else None.
    Supports subset matching for renamed files (e.g., playlist '癒合' matches file '告五人 - 癒合.mp3')
    """
    query_tokens = tuple(get_normalized_tokens(song_name))
    if not query_tokens:
        return None
    
    # Extract title part for flexible matching. Spotify playlist rows are saved
    # as "Title - Artist", so do not use the artist side as a title fallback.
    title_part = song_name
    artist_tokens = tuple()
    if ' - ' in song_name:
        parts = song_name.split(' - ', 1)
        if len(parts) == 2:
            title_part = parts[0].strip()
            artist_tokens = tuple(get_normalized_tokens(parts[1].strip()))
    title_tokens = tuple(get_normalized_tokens(title_part))
    
    found_files = []
    
    # Helper to check extension match
    target_ext = target_extension.lower()
    if not target_ext.startswith('.'):
        target_ext = '.' + target_ext
    
    # Check if library_source is a dictionary (index) or list (file list)
    if isinstance(library_source, dict):
        # 1. FAST PATH: Exact full match
        paths = library_source.get(query_tokens)
        if paths:
            if isinstance(paths, list):
                found_files = list(paths)
            else:
                found_files = [paths]
            # Check extension immediately — if found, return early
            for file_path in found_files:
                if file_path.lower().endswith(target_ext):
                    return file_path
        
        # 2. Title-only match (for renamed files)
        if title_tokens and title_tokens != query_tokens:
            paths = library_source.get(title_tokens)
            if paths:
                ext_candidates = paths if isinstance(paths, list) else [paths]
                for file_path in ext_candidates:
                    if file_path.lower().endswith(target_ext):
                        return file_path
                found_files.extend(ext_candidates)
        
        # 3. Subset matching (slow fallback — always run if no extension match yet)
        fuzzy_source = title_tokens if title_tokens else query_tokens
        if fuzzy_source:
            best_match = None
            best_score = 0
            fuzzy_tokens = fuzzy_source
            for index_tokens, paths in library_source.items():
                if not index_tokens: continue
                score = 0
                
                # Case A: Query is subset of Index (Strict, but now with score fallback)
                if len(fuzzy_tokens) > 0 and len(index_tokens) >= len(fuzzy_tokens):
                    # Check overlap/coverage instead of strict "all"
                    index_set = set(index_tokens)
                    fuzzy_set = set(fuzzy_tokens)
                    overlap_count = len(index_set & fuzzy_set)
                    
                    # Higher thresholds to reduce false positives
                    min_size = len(fuzzy_set)
                    if min_size <= 3:
                        required_ratio = 1.0  # 100% for very small sets
                    elif min_size <= 5:
                        required_ratio = 0.9  # 90% for small-medium sets
                    else:
                        required_ratio = 0.8  # 80% for larger sets
                    
                    if overlap_count / len(fuzzy_set) >= required_ratio:
                        coverage = overlap_count / len(index_tokens)
                        score = overlap_count * (coverage + 0.5) # Bonus for higher coverage
                
                # Case B: Index is subset of Query
                elif len(index_tokens) > 0 and len(fuzzy_tokens) >= len(index_tokens):
                    index_set = set(index_tokens)
                    fuzzy_set = set(fuzzy_tokens)
                    overlap_count = len(index_set & fuzzy_set)
                    
                    # Higher thresholds to reduce false positives
                    min_size = len(index_set)
                    if min_size <= 3:
                        required_ratio = 1.0  # 100% for very small sets
                    elif min_size <= 5:
                        required_ratio = 0.9  # 90% for small-medium sets
                    else:
                        required_ratio = 0.8  # 80% for larger sets
                    
                    if overlap_count / len(index_set) >= required_ratio:
                        coverage = overlap_count / len(fuzzy_set)
                        score = overlap_count * (coverage + 0.5)
                
                if score > 0:
                    artist_set = set(artist_tokens)
                    if artist_set and not (artist_set & set(index_tokens)):
                        continue
                    ext_candidates = paths if isinstance(paths, list) else [paths]
                    for file_path in ext_candidates:
                        if file_path.lower().endswith(target_ext):
                            if score > best_score:
                                best_score = score
                                best_match = file_path
            
            if best_match:
                return best_match
                        
    elif isinstance(library_source, list):
        # SLOW PATH: Linear Scan
        audio_files = library_source
        for file_path in audio_files:
            filename = os.path.basename(file_path)
            name_no_ext = os.path.splitext(filename)[0]
            file_tokens = tuple(get_normalized_tokens(name_no_ext))
            
            if not file_tokens: continue
            
            is_match = False
            # Exact match
            if file_tokens == query_tokens:
                is_match = True
            # Title-only match
            elif title_tokens and file_tokens == title_tokens:
                is_match = True
            # Subset match
            else:
                fuzzy_source = title_tokens if title_tokens else query_tokens
                if fuzzy_source:
                    title_set = set(fuzzy_source)
                    file_set = set(file_tokens)
                    artist_set = set(artist_tokens)
                    overlap = len(title_set & file_set)
                    min_size = min(len(title_set), len(file_set))
                    if min_size > 0 and overlap / min_size >= 0.5:
                        is_match = not artist_set or bool(artist_set & file_set)
            
            if is_match:
                if file_path.lower().endswith(target_ext):
                    return file_path
                found_files.append(file_path)
    else:
        return None
        
    return None

def move_unsorted_songs(config, log_func):
    """ Creates playlist for songs not in any playlist (without moving files) """
    from utils.i18n import _
    log_func(_('moving_unsorted'))
    
    # Normalize paths to standard Windows backslashes for reliable string comparison
    library_path = os.path.normpath(os.path.abspath(config['library_path']))
    playlists_path = os.path.normpath(os.path.abspath(config['playlists_path']))
    unsorted_dir = os.path.join(library_path, "_Unsorted")
    
    # Standardize unsorted_dir for comparison
    unsorted_dir_norm = unsorted_dir.lower() + os.sep
    
    # 1. Gather all songs from all playlists
    all_playlist_files = glob.glob(os.path.join(playlists_path, "*.m3u8")) + \
                         glob.glob(os.path.join(playlists_path, "*.m3u"))
    
    songs_in_playlists = set()
    total_playlist_entries = 0
    for pl_file in all_playlist_files:
        base = os.path.basename(pl_file)
        # Skip the unsorted/single tracks playlists themselves
        if any(x in base for x in ["_未分類", "_Unsorted", "Single Tracks", "單曲"]): continue
        songs = parse_playlist(pl_file)
        total_playlist_entries += len(songs)
        songs_in_playlists.update(songs)
    
    # Build tokens for comparison
    playlist_tokens = set()
    for s in songs_in_playlists:
        t = tuple(get_normalized_tokens(s))
        if t: playlist_tokens.add(t)
    log_func(f" -> 所有播放清單歌曲數(去重): {len(playlist_tokens)} / 總條目: {total_playlist_entries}")
        
    # 2. Identify orphan files in Music root and subdirectories
    search_pattern = os.path.join(library_path, "**", "*")
    all_library_files = [os.path.normpath(f) for f in glob.glob(search_pattern, recursive=True) if os.path.isfile(f)]
    
    orphans_map = {}
    for f in all_library_files:
        # ROBUST CHECK: skip if file is actually inside the _Unsorted directory
        if f.lower().startswith(unsorted_dir_norm): continue
        if os.path.basename(f).startswith('.'): continue
        if not f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm')): continue
        
        filename_no_ext = os.path.splitext(os.path.basename(f))[0]
        file_tokens = tuple(get_normalized_tokens(filename_no_ext))

        if file_tokens not in playlist_tokens:
            existing = orphans_map.get(file_tokens)
            if not existing:
                orphans_map[file_tokens] = f
            else:
                # Prefer MP3 when multiple formats exist for the same song
                cur_ext = os.path.splitext(existing)[1].lower()
                new_ext = os.path.splitext(f)[1].lower()
                if cur_ext != '.mp3' and new_ext == '.mp3':
                    orphans_map[file_tokens] = f

    orphans = list(orphans_map.values())
            
    # 3. Create playlist for unsorted songs (without moving files)
    # Use a localized name for the playlist
    # If it's explicitly a single track from user, we might want to call it "Single Tracks"
    pl_name = "_" + _('removed_songs_pl')
    m3u_path = os.path.join(playlists_path, f"{pl_name}.m3u8")
    
    # Check if we should also handle manual single tracks (songs in Music/Single Tracks)
    single_tracks_dir = os.path.join(library_path, "Single Tracks")
    single_tracks_pl = os.path.join(playlists_path, "Single Tracks.m3u8")
    
    if os.path.exists(single_tracks_dir):
        st_files = [f for f in os.listdir(single_tracks_dir) if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]
        if st_files:
            with open(single_tracks_pl, 'w', encoding='utf-8-sig', newline='') as f:
                f.write("#EXTM3U\r\n")
                for base in sorted(st_files):
                    name_no_ext = os.path.splitext(base)[0]
                    rel_path = f"../Music/Single Tracks/{base}"
                    f.write(f"#EXTINF:-1,{name_no_ext}\r\n")
                    f.write(f"{rel_path}\r\n")
    
    # Cleanup old legacy name if it exists
    old_m3u_path = os.path.join(playlists_path, "_Unsorted_Songs.m3u8")
    if old_m3u_path != m3u_path and os.path.exists(old_m3u_path):
        try: os.remove(old_m3u_path)
        except: pass
    
    # Create playlist for unsorted songs (keep files in original location)
    if orphans:
        try:
            os.makedirs(playlists_path, exist_ok=True)
            with open(m3u_path, 'w', encoding='utf-8-sig', newline='') as f:
                f.write("#EXTM3U\r\n")
                for file_path in sorted(orphans):
                    # Get relative path from playlists folder to the audio file
                    abs_file_path = os.path.normpath(os.path.abspath(file_path))
                    abs_playlists_path = os.path.normpath(os.path.abspath(playlists_path))
                    
                    # Calculate relative path
                    try:
                        rel_path = os.path.relpath(abs_file_path, abs_playlists_path)
                        # Convert to forward slashes for M3U compatibility
                        rel_path = rel_path.replace('\\', '/')
                    except ValueError:
                        # Cross-drive issue: use absolute path or fallback
                        # Use forward slashes and remove drive letter for compatibility
                        rel_path = abs_file_path.replace('\\', '/')
                        if ':' in rel_path:
                            # Remove drive letter for cross-drive compatibility
                            rel_path = rel_path.split(':', 1)[1].lstrip('/\\')
                        # Fallback to absolute path if relative path fails
                        rel_path = abs_file_path
                    
                    name_no_ext = os.path.splitext(os.path.basename(file_path))[0]
                    f.write(f"#EXTINF:-1,{name_no_ext}\r\n")
                    f.write(f"{rel_path}\r\n")
            
            log_func(f" -> 已為 {len(orphans)} 首未分類歌曲創建播放清單")
        except Exception as e:
            log_func(f"  ⚠️ 創建未分類播放清單失敗: {e}")
    else:
        # Remove empty playlist if no unsorted songs
        if os.path.exists(m3u_path):
            try: os.remove(m3u_path)
            except: pass
        log_func(" -> 沒有未分類歌曲")
    
    return len(orphans)

def update_library_logic_legacy(config, stats, log_func, progress_func=None, post_scrape_callback=None, post_download_callback=None, speed_display_callback=None):
    from core.spotify import scrape_via_spotify_embed
    from core.downloader import download_song, download_with_spotdl
    from utils.config import get_data_file
    import time
    import json
            
    # 0. Initialize
    library_path = config['library_path']
    playlists_path = config['playlists_path']
    
    # Get audio formats (support list or legacy single string)
    audio_formats = config.get('audio_formats', [])
    if not audio_formats:
        audio_formats = [config.get('audio_format', 'mp3')]
        
    # Define legacy audio_format for compatibility
    audio_format = audio_formats[0]
    
    # spotDL runtime config (standalone executable via subprocess)
    spotdl_cfg = {
        "spotdl_path": config.get("spotdl_path", "bin/spotdl.exe"),
        "ffmpeg_path": config.get("ffmpeg_path", "bin/ffmpeg.exe"),
        "format": config.get("spotdl_format", "mp3"),
        "overwrite": "force" if config.get("spotdl_force_overwrite", False) else "skip",
        "bitrate": config.get("spotdl_bitrate"),
        "timeout": int(config.get("spotdl_timeout", 600)),
    }
    spotdl_output_template = config.get("spotdl_output_template")
    if not spotdl_output_template:
        spotdl_output_template = os.path.join(library_path, "{artist}", "{album}", "{title}.{output-ext}")
    # Compatibility for user-provided "{format}" token
    spotdl_output_template = spotdl_output_template.replace("{format}", "{output-ext}")
        
    from utils.i18n import _
    
    # Get DAB Music credentials if available
    dab_credentials = None
    use_dab_lossless = config.get('dab_use_lossless', False)
    use_dab_metadata = config.get('dab_use_metadata', False)
    
    if use_dab_lossless or use_dab_metadata:
        dab_credentials = {
            'email': config.get('dab_email', ''),
            'password': config.get('dab_password', '')
        }
        if not dab_credentials['email'] or not dab_credentials['password']:
            log_func('⚠️ DAB Music credentials not configured. Using YouTube only.')
            use_dab_lossless = False
            use_dab_metadata = False
            dab_credentials = None

    # 1. Maintenance & Cleanup
    log_func(_('scanning_lib'))
    # 1.1 Unblock files to resolve 0x80070005 (Access Denied)
    unblock_files(library_path, log_func)

    # 1.2 Load failed FLAC cache
    failed_flac_cache = {}
    try:
        failed_flac_cache_file = get_data_file('failed_flac.json')
        if os.path.exists(failed_flac_cache_file):
            if os.path.getsize(failed_flac_cache_file) > 0:
                with open(failed_flac_cache_file, 'r', encoding='utf-8') as f:
                    failed_flac_cache = json.load(f)
                log_func(f"  前次失敗FLAC記錄: {len(failed_flac_cache)} 首")
            else:
                 log_func("  快取檔案為空，將重新建立")
    except json.JSONDecodeError:
        log_func("  快取檔案損毀 (JSON Error)，將重新建立")
        failed_flac_cache = {}
    except Exception as e:
        log_func(f"  無法讀取FLAC失敗快取: {e}")
        failed_flac_cache = {}

    # 2. Scrape Spotify (Update local tracklists from URL)
    scrape_via_spotify_embed(config, stats, log_func)
    if post_scrape_callback:
        post_scrape_callback()
    
    # Load song -> Spotify track URL mapping (generated by scraper)
    spotify_track_map = {}
    spotify_norm_map = {}
    try:
        spotify_track_map_path = get_data_file('spotify_track_map.json')
        if os.path.exists(spotify_track_map_path) and os.path.getsize(spotify_track_map_path) > 0:
            with open(spotify_track_map_path, 'r', encoding='utf-8') as smf:
                loaded_map = json.load(smf)
                if isinstance(loaded_map, dict):
                    spotify_track_map = loaded_map
                    for key_name, track_url in spotify_track_map.items():
                        normalized_tokens = tuple(get_normalized_tokens(key_name))
                        if normalized_tokens and track_url:
                            spotify_norm_map[normalized_tokens] = track_url
    except Exception as map_err:
        log_func(f"  ⚠️ 讀取 Spotify track URL 快取失敗: {map_err}")
        spotify_track_map = {}
        spotify_norm_map = {}

    def resolve_track_url(song_name):
        if not song_name:
            return None
        key_candidates = {
            song_name.strip().lower(),
            sanitize_filename(song_name).strip().lower()
        }
        for key in key_candidates:
            url = spotify_track_map.get(key)
            if isinstance(url, str) and "open.spotify.com/track/" in url:
                return url
        
        tokens = tuple(get_normalized_tokens(song_name))
        if tokens:
            return spotify_norm_map.get(tokens)
        return None

    # 3. Build Fresh Index and Scan Playlists
    # Scan for all playlist formats
    files = glob.glob(os.path.join(playlists_path, "*.m3u8")) + \
            glob.glob(os.path.join(playlists_path, "*.m3u")) + \
            glob.glob(os.path.join(playlists_path, "*.txt"))
            
    if not files:
        log_func(_('no_pl_files'))
        return

    # Build the library index for fast lookups
    log_func(_('building_index'))
    search_pattern = os.path.join(library_path, "**", "*")
    all_files = glob.glob(search_pattern, recursive=True)
    audio_files_cache = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]
    library_index = build_library_index(audio_files_cache)
    log_func(_('indexed_songs', len(audio_files_cache)))
    
    songs_to_download = [] # List of {'name': s, 'playlist': pl, 'needed_formats': []}
    songs_missing_lyrics = [] # List of (song_name, existing_path)
    
    # Pre-scan existing files for missing lyrics
    for audio_path in audio_files_cache:
        lrc_path = os.path.splitext(audio_path)[0] + ".lrc"
        if not os.path.exists(lrc_path):
            # Extract song name from filename
            song_name = os.path.splitext(os.path.basename(audio_path))[0]
            songs_missing_lyrics.append((song_name, audio_path))

    # Map playlist names back to artist names for "Artist" type playlists to provide better search hints
    pl_name_to_artist = {}
    url_names_cfg = config.get('url_names', {})
    for sp_url, name in url_names_cfg.items():
        if get_playlist_type(sp_url) == "Artist":
            pl_name_to_artist[name] = name

    # First Pass: Filename Index Check (Fast)
    for pl_file in files:
        if stats and stats.stop_event and stats.stop_event.is_set():
             log_func(_('task_stopped'))
             return

        pl_name = os.path.splitext(os.path.basename(pl_file))[0]
        songs = parse_playlist(pl_file)
        for song_name in songs:
             if stats and stats.stop_event and stats.stop_event.is_set():
                  log_func(_('task_stopped'))
                  return

             # Check which formats are missing
             missing_formats = []
             should_retry_flac = config.get('retry_failed_flac', False)
             for fmt in audio_formats:
                 if not find_song_exact_format(song_name, fmt, library_index):
                     # If format is FLAC, check if it was previously failed and we shouldn't retry
                     if fmt == 'flac' and not should_retry_flac:
                         # Normalize song name for consistent hashing
                         norm_name = song_name.strip().lower()
                         song_key = hashlib.md5(norm_name.encode('utf-8')).hexdigest()
                         if song_key in failed_flac_cache:
                             continue # Skip adding FLAC to missing if it's in failed cache
                     missing_formats.append(fmt)
             
             if missing_formats:
                 # Check if already in list to avoid duplicates across diff playlists
                 # Use a composite check: match name AND merge missing formats if needed
                 existing_entry = next((item for item in songs_to_download if item['name'] == song_name), None)
                 
                 if existing_entry:
                     # Merge missing formats (union)
                     current_missing = set(existing_entry['needed_formats'])
                     new_missing = set(missing_formats)
                     existing_entry['needed_formats'] = list(current_missing.union(new_missing))
                     if not existing_entry.get('url'):
                         existing_entry['url'] = resolve_track_url(song_name)
                 else:
                     artist_hint = pl_name_to_artist.get(pl_name)
                     songs_to_download.append({
                         'name': song_name, 
                         'playlist': pl_name, 
                         'needed_formats': missing_formats,
                         'artist_hint': artist_hint,
                         'url': resolve_track_url(song_name)
                     })
    
    # Second Pass: Deep Metadata Scan (Slower but necessary for renamed files)
    if songs_to_download:
        log_func(f"  🔍 初步掃描: 發現 {len(songs_to_download)} 首缺歌，正在進行深度 Metadata 比對...")
        
        # Build metadata index (Scan all files once)
        metadata_index = build_metadata_index(audio_files_cache, log_func)
        
        still_missing = []
        for item in songs_to_download:
            song_name = item['name']
            needed_formats = item['needed_formats']
            
            # Check against metadata index - returns a path if found
            found_path = find_song_in_library(song_name, library_index, metadata_index=metadata_index)
            
            if found_path:
                # Found a file via metadata! Check its extension.
                ext = os.path.splitext(found_path)[1].lower().lstrip('.')
                
                # If the found file matches one of the needed formats, remove it
                if ext in needed_formats:
                    # Create a new list without the found format
                    needed_formats = [fmt for fmt in needed_formats if fmt != ext]
                    item['needed_formats'] = needed_formats
                    log_func(f"  ✅ [Metadata Found] {song_name} -> {found_path}")
            
            # If we still need formats (either didn't find anything, or found one but needed others)
            if needed_formats:
                still_missing.append(item)
            else:
                log_func(f"  ✅ [All Formats Found] {song_name}")
                
        if len(songs_to_download) != len(still_missing):
            log_func(f"  ✅ 透過 Metadata 找回 {len(songs_to_download) - len(still_missing)} 首歌 (部分或全部格式)")
        
        songs_to_download = still_missing
        
        if len(songs_to_download) == 0:
            log_func(f"  🎉 所有歌曲都已找到，無需下載")
        else:
            log_func(f"  📋 最終需要下載: {len(songs_to_download)} 首歌")

    total_missing = len(songs_to_download)
    log_func(_('stats_complete', total_missing))
    
    if progress_func: progress_func(0, total_missing)
    
    # PHASE 2: Download
    if total_missing > 0:
        log_func(_('dl_start'))
        log_func(f"🔄 開始下載迴圈，共 {total_missing} 首歌曲")
        current_dl = 0
        successful_downloads = 0
        
        # Create a wrapper to pass overall ETA to progress function
        overall_start_time = time.time()
        total_downloaded_time = 0  # Track cumulative download time
        
        # Initial progress call to show task starting
        if progress_func:
            # Provide an initial rough estimate (2 minutes per song)
            initial_eta = total_missing * 120  # 2 minutes per song
            progress_func(0, total_missing, initial_eta)
        
        def progress_with_overall_eta(current, total, song_eta=None):
            if progress_func:
                # Use provided song_eta if available, otherwise calculate based on average time
                if song_eta is not None and isinstance(song_eta, (int, float)):
                    # Use the provided ETA directly, even if small
                    eta_seconds = song_eta
                elif current and current > 0 and total_downloaded_time > 0:
                    # Calculate overall ETA based on progress and average time per song
                    avg_time_per_song = total_downloaded_time / max(1, current)
                    remaining_songs = total - current
                    eta_seconds = remaining_songs * avg_time_per_song
                else:
                    eta_seconds = 0
                
                # Ensure eta_seconds is numeric
                try:
                    eta_seconds = float(eta_seconds)
                except (ValueError, TypeError):
                    eta_seconds = 0
                
                if eta_seconds > 0:
                    eta_min = int(eta_seconds // 60)
                    eta_sec = int(eta_seconds % 60)
                    overall_eta = f"{eta_min}:{eta_sec:02d}"
                else:
                    overall_eta = "即將完成" if current and current > 0 else None
                
                progress_func(current, total, overall_eta)
            else:
                progress_func(0, total, None)
        
        # Initialize song status tracking for downloads
        download_status = {}
        for i, item in enumerate(songs_to_download):
            song_name = item['name']
            needed_formats = item.get('needed_formats', [audio_format])
            
            # 根據格式設定初始狀態
            if 'flac' in needed_formats:
                initial_status = '⏳ 等待 FLAC'
            else:
                initial_status = '⏳ 等待中'
                
            download_status[i] = {
                'name': song_name,
                'status': initial_status,
                'order': i + 1
            }
            # Initialize song status in UI
            if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
                stats.app.update_song_status(i, initial_status, song_name)

        # Process all downloads sequentially (including FLAC)
        for i, item in enumerate(songs_to_download):
            song_name = item['name']
            pl_name = item['playlist']
            needed_formats = item.get('needed_formats', [audio_format])
            remaining = total_missing - (current_dl + 1)
            
            if stats and stats.stop_event and stats.stop_event.is_set():
                 log_func(_('task_stopped'))
                 return

            if hasattr(stats, 'pause_event') and stats.pause_event:
                 stats.pause_event.wait()
            
            # Check if this FLAC song was previously failed and should be skipped
            if 'flac' in needed_formats:
                # Normalize song name for consistent hashing
                norm_name = song_name.strip().lower()
                song_key = hashlib.md5(norm_name.encode('utf-8')).hexdigest()
                should_retry_flac = config.get('retry_failed_flac', False)
                
                if not should_retry_flac and song_key in failed_flac_cache:
                    log_func(f"  ⏭️ [FLAC Skipped] {song_name} (previously failed)")
                    # Only remove FLAC from needed formats, keep other formats (e.g. MP3)
                    needed_formats = [f for f in needed_formats if f != 'flac']
                    item['needed_formats'] = needed_formats
                    
                    if not needed_formats:
                        # Only needed FLAC and it was skipped → skip entire song
                        if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
                            stats.app.update_song_status(i, '⏭️ 跳過', song_name)
                        current_dl += 1
                        if progress_func: 
                            progress_func(current_dl, total_missing, None)
                        continue
            
            # Set appropriate initial status based on format
            if 'flac' in needed_formats:
                initial_status = '🔽 FLAC'
            else:
                initial_status = '🔽 下載中'
                
            # Update status to downloading
            if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
                stats.app.update_song_status(i, initial_status, song_name)
                 
            # Check if log_func supports immediate parameter
            if hasattr(log_func, '__code__') and 'immediate' in log_func.__code__.co_varnames:
                log_func(_('dl_progress', current_dl+1, total_missing, remaining, pl_name, song_name), immediate=True)
            else:
                log_func(_('dl_progress', current_dl+1, total_missing, remaining, pl_name, song_name))
            
            # Create a progress callback for this song
            song_start_time = time.time()
            def song_progress_callback(current, total, eta=None):
                # Calculate remaining songs here to avoid UnboundLocalError
                remaining_songs = total_missing - current_dl
                
                # Update overall progress with current song progress
                # Use current_dl + (current/total) to show progress within current song
                if total and total > 0:
                    song_progress = current / total
                    overall_progress = current_dl + song_progress
                else:
                    overall_progress = current_dl
                
                # Calculate overall ETA for the entire task
                if total_downloaded_time > 0 and current_dl > 0:
                    avg_time_per_song = total_downloaded_time / current_dl
                    eta_seconds = remaining_songs * avg_time_per_song
                    # Ensure eta_seconds is numeric
                    try:
                        eta_seconds = float(eta_seconds)
                    except (ValueError, TypeError):
                        eta_seconds = None
                    progress_with_overall_eta(overall_progress, total_missing, eta_seconds)
                else:
                    # For first song, try to use current song's ETA as rough estimate
                    if current and current > 0 and song_start_time:
                        current_duration = time.time() - song_start_time
                        if current_duration > 1: # Wait for stable speed
                            # Estimate total time for this song
                            est_total_song_time = current_duration / (current/total)
                            remaining_song_time = est_total_song_time - current_duration
                            
                            if remaining_songs > 0:
                                # Estimate 2 minutes per remaining song as fallback
                                estimated_remaining_time = remaining_song_time + (remaining_songs * 120)
                            else:
                                estimated_remaining_time = remaining_song_time
                            progress_with_overall_eta(overall_progress, total_missing, estimated_remaining_time)
                        else:
                            progress_with_overall_eta(overall_progress, total_missing, None)
                    else:
                        progress_with_overall_eta(overall_progress, total_missing, None)
            
            needed_formats = item.get('needed_formats', [audio_format])
            # Process all formats including FLAC (DAB Music handles FLAC via dab_downloader)
            
            if not needed_formats:
                continue  # Skip if no formats to download
                
            downloaded_paths = []
            failed_formats = []
            
            for fmt in needed_formats:
                # Update UI to show specific format
                if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
                    stats.app.update_song_status(i, f'🔽 {fmt.upper()}', song_name)
                
                artist_hint = item.get('artist_hint')
                spotify_url = item.get('url')
                res = None

                # Prefer spotDL for lossy formats when Spotify track URL exists
                if spotify_url and fmt in ('mp3', 'm4a', 'opus'):
                    spotdl_cfg["format"] = fmt
                    log_func(f"  🎯 [spotDL] {song_name} -> {fmt.upper()}")
                    res_path = download_with_spotdl(spotify_url, spotdl_output_template, spotdl_cfg)
                    if res_path and os.path.exists(res_path):
                        res = str(res_path)
                    else:
                        log_func(f"  ⚠️ [spotDL Failed] {song_name}，回退舊下載流程")
                
                # Fallback: legacy downloader (yt-dlp / DAB)
                if not res:
                    if not spotify_url and fmt in ('mp3', 'm4a', 'opus'):
                        log_func(f"  ℹ️ [No Spotify URL] {song_name}，使用舊下載流程")
                    res = download_song(song_name, library_path, fmt, log_func, audio_files_cache, stats, None, song_progress_callback, current_dl, use_dab_lossless, use_dab_metadata, dab_credentials, config, artist_hint)
                
                if res and os.path.exists(res):
                    downloaded_paths.append(res)
                    audio_files_cache.append(res)
                else:
                    failed_formats.append(fmt)
            
            # Handle FLAC failure cache independently
            norm_name = song_name.strip().lower()
            song_key = hashlib.md5(norm_name.encode('utf-8')).hexdigest()

            if 'flac' in failed_formats:
                failed_flac_cache[song_key] = {
                    'name': song_name,
                    'timestamp': time.time(),
                    'reason': 'dab_unavailable'
                }
                log_func(f"  ℹ️ [FLAC Unavailable] {song_name} - DAB Music 無此歌曲")
                
                # Save cache immediately to prevent loss on cancellation
                try:
                    failed_flac_cache_file = get_data_file('failed_flac.json')
                    os.makedirs(os.path.dirname(failed_flac_cache_file), exist_ok=True)
                    with open(failed_flac_cache_file, 'w', encoding='utf-8') as f:
                        json.dump(failed_flac_cache, f, ensure_ascii=False, indent=2)
                except:
                    pass
            elif 'flac' in needed_formats and 'flac' not in failed_formats:
                # FLAC was requested and succeeded, remove from failed cache if present
                if song_key in failed_flac_cache:
                    del failed_flac_cache[song_key]
                    # Also save periodically or at the end

            
            if downloaded_paths:
                # At least one format succeeded
                if failed_formats:
                    status_text = f'⚠️ 部分完成 ({",".join(f.upper() for f in failed_formats)} 失敗)'
                else:
                    status_text = '✅ 完成'
                
                if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
                    stats.app.update_song_status(i, status_text, song_name)
                
                # Track time spent on this song
                song_end_time = time.time()
                song_duration = song_end_time - song_start_time
                total_downloaded_time += song_duration
                
                stats.songs_downloaded.append(song_name)
                # Track which playlist this song was updated for
                if pl_name not in stats.playlist_updates:
                    stats.playlist_updates[pl_name] = []
                stats.playlist_updates[pl_name].append(song_name)
                successful_downloads += 1
                
                if post_download_callback:
                    post_download_callback(audio_files_cache)

                if successful_downloads % 10 == 0:
                    log_func(_('dl_rest', successful_downloads))
                    time.sleep(15)
            else:
                # All formats failed
                if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
                    stats.app.update_song_status(i, '❌ 失敗', song_name)
            
            current_dl += 1
            # Update progress with overall ETA calculation
            if total_downloaded_time > 0 and current_dl > 0:
                avg_time_per_song = total_downloaded_time / current_dl
                remaining_songs = total_missing - current_dl
                eta_seconds = remaining_songs * avg_time_per_song
                # Ensure eta_seconds is numeric
                try:
                    eta_seconds = float(eta_seconds)
                except (ValueError, TypeError):
                    eta_seconds = None
                if progress_func: 
                    progress_func(current_dl, total_missing, eta_seconds)
            else:
                if progress_func: 
                    progress_func(current_dl, total_missing, None)
            
            # Only add delay if not the last song and not cancelled
            if current_dl < total_missing - 1:
                delay = random.uniform(3, 8)
                time.sleep(delay)
    
    # Save failed FLAC cache
    try:
        failed_flac_cache_file = get_data_file('failed_flac.json')
        os.makedirs(os.path.dirname(failed_flac_cache_file), exist_ok=True)
        with open(failed_flac_cache_file, 'w', encoding='utf-8') as f:
            json.dump(failed_flac_cache, f, ensure_ascii=False, indent=2)
        if failed_flac_cache:
            log_func(f"  💾 已儲存 {len(failed_flac_cache)} 首FLAC失敗記錄")
    except Exception as e:
        log_func(f"  ⚠️ 無法儲存FLAC失敗快取: {e}")

    # PHASE 4: Metadata Enrichment
    if config.get('enable_metadata_enrichment', True) or config.get('auto_metadata', False):
        try:
            from core.metadata_enricher import create_metadata_enricher
            log_func(_('metadata_enrichment_start'))
            enricher = create_metadata_enricher(config)
            enricher.enrich_library_metadata(library_path, log_func)
            enricher.cleanup()
        except ImportError:
            log_func("⚠️ Metadata enrichment module not found.")
        except Exception as e:
            log_func(f"⚠️ Metadata enrichment failed: {e}")
        
    # PHASE 3: Retroactive Lyrics Download (Only run if enabled and there are existing songs missing lyrics)
    if songs_missing_lyrics and config.get('enable_retroactive_lyrics', False):
        from core.downloader import download_lyrics
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import json
        from utils.config import get_data_file
        
        log_func(_('retroactive_lyrics', len(songs_missing_lyrics)))
        total_lyrics_to_fetch = len(songs_missing_lyrics)
        lyrics_fetched_count = 0
        consecutive_failures = 0
        max_consecutive_failures = 10  # Skip to next phase after too many failures
        
        # Load failed lyrics cache
        failed_cache_file = get_data_file('failed_lyrics.json')
        failed_cache = {}
        try:
            if os.path.exists(failed_cache_file):
                with open(failed_cache_file, 'r', encoding='utf-8') as f:
                    failed_cache = json.load(f)
        except:
            failed_cache = {}
        
        # Filter out songs that were previously marked as failed
        filtered_songs = []
        for name, path in songs_missing_lyrics:
            # Create a unique key for the song (based on name)
            song_key = hashlib.md5(name.encode('utf-8')).hexdigest()
            # Check if we should retry or skip
            should_retry = config.get('retry_failed_lyrics', False)
            
            if should_retry or song_key not in failed_cache:
                filtered_songs.append((name, path))
            else:
                log_func(f"  ⏭️ [Lyrics Skipped] {name} (previously failed)")
        
        if not filtered_songs:
            log_func("  ℹ️ 所有缺少歌詞的歌曲都已標記為失敗，跳過歌詞補抓")
        else:
            log_func(f"  ℹ️ 跳過 {len(songs_missing_lyrics) - len(filtered_songs)} 首先前失敗的歌曲")
            songs_missing_lyrics = filtered_songs
            total_lyrics_to_fetch = len(songs_missing_lyrics)
        
        # Create song status tracking
        song_status = {}
        for i, (name, path) in enumerate(songs_missing_lyrics):
            song_status[i] = {
                'name': name,
                'status': '⏳ 等待中',
                'order': i + 1
            }
            # Initialize song status in UI
            if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
                stats.app.update_song_status(i, '⏳ 等待中', name)
        
        # Multi-threading settings
        max_workers = config.get('max_threads', 4)
        results_lock = threading.Lock()
        
        def process_single_song(song_data):
            nonlocal lyrics_fetched_count, consecutive_failures, failed_cache, song_status
            
            i, (name, path) = song_data
            if stats and stats.stop_event and stats.stop_event.is_set():
                return None, None
            
            if hasattr(stats, 'pause_event') and stats.pause_event:
                stats.pause_event.wait()
            
            # Update status to processing
            with results_lock:
                song_status[i]['status'] = '🔍 搜尋中'
                if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
                    stats.app.update_song_status(i, '🔍 搜尋中', name)
            
            lrc_path = os.path.splitext(path)[0] + ".lrc"
            success = download_lyrics(name, lrc_path, lambda msg: None)  # Suppress individual logs
            
            with results_lock:
                if success:
                    lyrics_fetched_count += 1
                    consecutive_failures = 0
                    song_status[i]['status'] = '✅ 成功'
                    if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
                        stats.app.update_song_status(i, '✅ 成功', name)
                    return f"  ✅ [Lyrics] {name}", i + 1
                else:
                    # Mark as failed in cache
                    song_key = hashlib.md5(name.encode('utf-8')).hexdigest()
                    failed_cache[song_key] = {
                        'name': name,
                        'timestamp': time.time(),
                        'reason': 'not_found'
                    }
                    
                    consecutive_failures += 1
                    song_status[i]['status'] = '❌ 失敗'
                    if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
                        stats.app.update_song_status(i, '❌ 失敗', name)
                    if consecutive_failures >= max_consecutive_failures:
                        return f"  ⚠️ [Lyrics] 連續 {max_consecutive_failures} 次失敗，跳過剩餘歌詞下載", None
                    return f"  ❌ [Lyrics] {name}", i + 1
        
        # Process songs with multi-threading
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_index = {
                executor.submit(process_single_song, (i, song_data)): i 
                for i, song_data in enumerate(songs_missing_lyrics)
            }
            
            # Collect results as they complete
            completed_count = 0
            
            for future in as_completed(future_to_index):
                if consecutive_failures >= max_consecutive_failures:
                    break
                    
                result, progress = future.result()
                completed_count += 1
                
                # Update status in UI from main thread after future completes
                if progress is not None:
                    idx = progress - 1
                    if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
                        stats.app.update_song_status(idx, song_status[idx]['status'], song_status[idx]['name'])
                
                # Show progress every 10 songs or every 5 songs for small batches
                progress_interval = 10 if total_lyrics_to_fetch > 50 else 5
                if completed_count % progress_interval == 0 or completed_count == total_lyrics_to_fetch:
                    success_rate = (lyrics_fetched_count / completed_count * 100) if completed_count > 0 else 0
                    log_func(f"🎵 歌詞補抓進度: {completed_count}/{total_lyrics_to_fetch} (成功: {lyrics_fetched_count}, 成功率: {success_rate:.1f}%)")
        
        # Final summary
        if lyrics_fetched_count > 0:
            log_func(f"🎉 歌詞補抓完成: 成功 {lyrics_fetched_count} / {total_lyrics_to_fetch} 首")
        
        # Save failed cache
        try:
            os.makedirs(os.path.dirname(failed_cache_file), exist_ok=True)
            with open(failed_cache_file, 'w', encoding='utf-8') as f:
                json.dump(failed_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log_func(f"  ⚠️ 無法儲存失敗歌詞快取: {e}")
    elif songs_missing_lyrics and not config.get('enable_retroactive_lyrics', False):
        log_func(f" -> 跳過歌詞補抓 ({len(songs_missing_lyrics)} 首歌曲缺少歌詞，但已停用自動補抓功能)")
    
    if total_missing == 0:
        log_func(_('lib_up_to_date'))
        if progress_func: progress_func(100, 100)

    # FINAL STEP: Analyze and move unsorted songs
    try:
        move_unsorted_songs(config, log_func)
    except: pass
    
    # METADATA ENRICHMENT STEP: Enrich metadata for existing files
    if config.get('enable_metadata_enrichment', False):
        try:
            from core.metadata_enricher import create_metadata_enricher
            enricher = create_metadata_enricher(config)
            
            def metadata_progress(current, total):
                if progress_func:
                    # Convert to percentage for display
                    percentage = (current / total) * 100 if total and total > 0 else 0
                    progress_func(percentage, 100)
            
            enriched_count = enricher.enrich_library_metadata(library_path, log_func, metadata_progress)
            enricher.cleanup()
            
            if enriched_count > 0:
                log_func(f'🎉 Enriched metadata for {enriched_count} files')
            else:
                log_func('ℹ️ No files needed metadata enrichment')
                
        except Exception as e:
            log_func(f' Metadata enrichment failed: {str(e)}')
    
    log_func(_('update_complete'))

def update_library_logic(config, stats, log_func, progress_func=None, post_scrape_callback=None, post_download_callback=None, speed_display_callback=None):
    from core.spotify import scrape_via_spotify_embed
    from utils.i18n import _
    import time

    # 0. Initialize
    library_path = config['library_path']
    playlists_path = config['playlists_path']

    def _check_cancel():
        if stats and stats.stop_event and stats.stop_event.is_set():
            log_func(_('task_stopped'))
            return True
        return False

    def _wait_if_paused():
        if not (stats and hasattr(stats, 'pause_event') and stats.pause_event):
            return True
        while not stats.pause_event.is_set():
            if stats.stop_event and stats.stop_event.is_set():
                return False
            stats.pause_event.wait(0.2)
        return True

    # 1. Maintenance & Cleanup
    if not _wait_if_paused():
        return
    if _check_cancel():
        return
    log_func(_('scanning_lib'))
    unblock_files(library_path, log_func)

    if progress_func:
        progress_func(5, 100, None)

    # 2. Convert Spotube M4A -> MP3
    if not _wait_if_paused():
        return
    if _check_cancel():
        return
    log_func(" -> Converting Spotube M4A to MP3")
    def _conv_progress(done, total):
        if not progress_func or not total:
            return
        pct = 5 + (float(done) / float(total)) * 35.0
        progress_func(pct, 100, None)

    status_cb = None
    if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
        status_cb = stats.app.update_song_status

    converted, skipped, total = convert_spotube_m4a_to_mp3(
        config,
        log_func,
        pause_event=getattr(stats, 'pause_event', None),
        stop_event=getattr(stats, 'stop_event', None),
        progress_cb=_conv_progress,
        status_cb=status_cb
    )
    if converted > 0:
        log_func(f" -> M4A to MP3: {converted} converted")

    if progress_func:
        progress_func(40, 100, None)

    # 3. Scrape Spotify and build playlists
    if not _wait_if_paused():
        return
    if _check_cancel():
        return
    scrape_via_spotify_embed(config, stats, log_func)
    if post_scrape_callback:
        post_scrape_callback()

    if progress_func:
        progress_func(70, 100, None)

    # 4. Remove missing tracks from playlists
    if not _wait_if_paused():
        return
    if _check_cancel():
        return
    removed, total_files = prune_missing_from_playlists(config, log_func, pause_event=getattr(stats, 'pause_event', None), stop_event=getattr(stats, 'stop_event', None))
    if removed == 0:
        log_func(_('lib_up_to_date'))

    if progress_func:
        progress_func(85, 100, None)

    # 5. Analyze and move unsorted songs
    if not _wait_if_paused():
        return
    if _check_cancel():
        return
    try:
        move_unsorted_songs(config, log_func)
    except Exception:
        pass

    if progress_func:
        progress_func(95, 100, None)

    # Metadata enrichment (optional)
    if config.get('enable_metadata_enrichment', False):
        if not _wait_if_paused():
            return
        if _check_cancel():
            return
        try:
            from core.metadata_enricher import create_metadata_enricher
            enricher = create_metadata_enricher(config)

            def metadata_progress(current, total):
                if progress_func:
                    percentage = (current / total) * 100 if total and total > 0 else 0
                    progress_func(percentage, 100)

            enricher.enrich_library_metadata(library_path, log_func, metadata_progress)
            enricher.cleanup()
        except Exception as e:
            log_func(f' Metadata enrichment failed: {str(e)}')

    if progress_func:
        progress_func(100, 100, None)

    log_func(_('update_complete'))

def get_playlist_completeness_report(files, library_path):
    """Returns a dict mapping file -> (is_complete, missing_count, total_count)"""
    from utils.i18n import _
    
    # Build library index for fast lookup
    search_pattern = os.path.join(library_path, "**", "*")
    all_files = glob.glob(search_pattern, recursive=True)
    audio_files_cache = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]
    library_index = build_library_index(audio_files_cache)
    
    # Get current audio format preference (support multiple formats)
    from utils.config import load_config, get_data_file
    config = load_config()
    audio_formats = config.get('audio_formats', [])
    if not audio_formats:
        # Fallback to legacy single format
        audio_formats = [config.get('audio_format', 'mp3')]
    
    # Load failed_flac_cache to exclude known-unavailable FLAC from missing count
    failed_flac_cache = {}
    if 'flac' in audio_formats:
        try:
            failed_flac_cache_file = get_data_file('failed_flac.json')
            if os.path.exists(failed_flac_cache_file):
                with open(failed_flac_cache_file, 'r', encoding='utf-8') as f:
                    failed_flac_cache = json.load(f)
        except:
            failed_flac_cache = {}
    
    report = {}
    for pl_file in files:
        songs = parse_playlist(pl_file)
        missing = 0
        for song_name in songs:
            # Determine which formats this song actually needs
            song_formats = list(audio_formats)
            if 'flac' in song_formats and failed_flac_cache:
                norm_name = song_name.strip().lower()
                song_key = hashlib.md5(norm_name.encode('utf-8')).hexdigest()
                if song_key in failed_flac_cache:
                    # FLAC known unavailable, don't require it
                    song_formats = [f for f in song_formats if f != 'flac']
            
            if not song_formats:
                # All formats were excluded (only had FLAC and it failed)
                continue
            
            is_song_complete = True
            for fmt in song_formats:
                # Check strict existence of each format
                if not find_song_exact_format(song_name, fmt, library_index):
                    is_song_complete = False
                    break
            
            if not is_song_complete:
                missing += 1
        
        report[pl_file] = (missing == 0, missing, len(songs))
    
    return report

def export_usb_logic(config, selected_playlists, log_func, export_quality='original'):
    from utils.i18n import _
    from core.audio_converter import convert_audio_if_needed, check_ffmpeg_available
    import tempfile
    
    log_func(_('export_start'))
    
    # Check if conversion is needed and ffmpeg is available
    if export_quality != 'original':
        if not check_ffmpeg_available():
            log_func('⚠️ FFmpeg not found. Keeping original quality.')
            export_quality = 'original'
        else:
            log_func(f'🔄 Export quality: {export_quality.upper()}')
    
    export_path = config['export_path']
    library_path = config['library_path']
    
    if os.path.exists(export_path):
        shutil.rmtree(export_path)
        time.sleep(0.5)
    os.makedirs(export_path)
    
    if not selected_playlists:
        log_func(_('no_pl_selected'))
        return

    search_pattern = os.path.join(library_path, "**", "*")
    all_files = glob.glob(search_pattern, recursive=True)
    audio_files_cache = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]

    for pl_file in selected_playlists:
        if not os.path.exists(pl_file): continue
        
        pl_name = os.path.splitext(os.path.basename(pl_file))[0]
        dest_folder = os.path.join(export_path, pl_name)
        if not os.path.exists(dest_folder):
            os.makedirs(dest_folder)
            
        songs = parse_playlist(pl_file)
        log_func(_('exporting_pl', pl_name))
        
        count = 0
        converted_files = []  # Track converted files for cleanup
        failed_quality = []   # Track songs that couldn't meet quality requirements
        
        for song_name in songs:
            src = find_song_in_library(song_name, audio_files_cache)
            if src and os.path.exists(src):
                try:
                    # Check source format and validate conversion requirements
                    src_ext = os.path.splitext(src)[1].lower()
                    
                    # Validate conversion requirements
                    if export_quality == 'flac' and src_ext != '.flac':
                        # MP3 to FLAC conversion is not allowed (lossy to lossless)
                        log_func(f"  ❌ [Quality Error] {song_name}: 無法將 {src_ext[1:].upper()} 轉換為 FLAC (有損轉無損不被允許)")
                        failed_quality.append(song_name)
                        continue
                    elif export_quality == 'mp3' and src_ext == '.flac':
                        # FLAC to MP3 conversion is allowed (lossless to lossy)
                        log_func(f"  🔄 [Quality Conversion] {song_name}: FLAC 轉換為 MP3 (320kbps)")
                    elif export_quality != 'original' and src_ext == f'.{export_quality}':
                        # Already in target format
                        log_func(f"  ✅ [Quality Match] {song_name}: 已經是 {export_quality.upper()} 格式")
                    
                    # Handle conversion if needed
                    if export_quality != 'original':
                        final_src, was_converted = convert_audio_if_needed(src, export_quality, log_func)
                        if was_converted:
                            converted_files.append(final_src)
                    else:
                        final_src = src
                    
                    # Determine output filename based on target format
                    if export_quality != 'original':
                        base_name = os.path.splitext(os.path.basename(final_src))[0]
                        dest_filename = f"{base_name}.{export_quality}"
                    else:
                        dest_filename = os.path.basename(final_src)
                    
                    dest_path = os.path.join(dest_folder, dest_filename)
                    shutil.copy2(final_src, dest_path)
                    count += 1
                    
                except Exception as e:
                    log_func(_('copy_error', e))
            else:
                log_func(f"  ❌ [Not Found] {song_name}: 檔案不存在")
                failed_quality.append(song_name)
        
        # Clean up temporary converted files
        for temp_file in converted_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass  # Ignore cleanup errors
        
        log_func(_('exported_count', count, len(songs)))
        
        # Report quality conversion failures
        if failed_quality:
            log_func(f"  ⚠️ 品質不符: {len(failed_quality)} 首歌曲無法匯出為指定品質")
            if export_quality == 'flac':
                log_func(f"     提示: FLAC 需要原始檔案為 FLAC 格式，MP3 無法轉換為 FLAC")
                log_func(f"     建議: 請選擇 '保持原始品質' 或 '轉換為 MP3'，或確保音樂庫中有 FLAC 版本")
        
    log_func(_('export_done_open'))
    abs_export_path = os.path.abspath(export_path)
    if os.path.exists(abs_export_path):
        os.startfile(abs_export_path)
    else:
        log_func(_('open_dir_error', abs_export_path))


def get_detailed_stats(config, audio_files=None):
    """
    Returns a dictionary with:
    - total_songs: count of unique files in library
    - total_size_mb: total size of library in MB
    - recently_added: list of (filename, date) for last 5 downloads
    - total_playlist_entries: sum of lengths of all playlists
    - unique_playlist_entries: count of unique song names across all playlists
    - potential_size_gb: what the size would be if duplicates were real files
    - savings_mb: space saved due to deduplication
    """
    library_path = config['library_path']
    playlists_path = config['playlists_path']
    
    # 1. Library Stats
    if audio_files is None:
        search_pattern = os.path.join(library_path, "**", "*")
        all_files = [f for f in glob.glob(search_pattern, recursive=True) if os.path.isfile(f)]
        audio_files = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]
    
    # Count unique tracks (dedupe m4a/mp3/etc with same normalized tokens)
    # placeholder: filled after tokenization
    total_songs = 0
    flac_count = 0
    lossy_count = 0
    mp3_count = 0
    m4a_count = 0
    total_size_bytes = 0
    for f in audio_files:
        try:
            if os.path.exists(f):
                total_size_bytes += os.path.getsize(f)
        except (OSError, IOError):
            # Skip files that can't be accessed (deleted, moved, etc.)
            continue
    total_size_mb = total_size_bytes / (1024 * 1024)
    
    # Recently added (by mtime)
    # Filter out files that don't exist before sorting
    existing_audio_files = [f for f in audio_files if os.path.exists(f)]
    
    def safe_getmtime(filepath):
        try:
            return os.path.getmtime(filepath)
        except (OSError, IOError):
            return 0
    
    audio_files_sorted = sorted(existing_audio_files, key=safe_getmtime, reverse=True)
    recent_5 = []
    for f in audio_files_sorted[:5]:
        try:
            mtime = os.path.getmtime(f)
            import datetime
            date_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
            recent_5.append((os.path.basename(f), date_str))
        except (OSError, IOError):
            # Skip files that can't be accessed
            continue
        
    # Build token index for library (dedupe across formats)
    library_tokens = set()
    token_to_exts = {}
    for file_path in audio_files:
        if os.path.exists(file_path):
            filename = os.path.basename(file_path)
            name_no_ext = os.path.splitext(filename)[0]
            tokens_tuple = tuple(get_normalized_tokens(name_no_ext))
            if tokens_tuple:
                library_tokens.add(tokens_tuple)
                ext = os.path.splitext(filename)[1].lower()
                token_to_exts.setdefault(tokens_tuple, set()).add(ext)

    unique_library_tracks = len(library_tokens)
    total_songs = unique_library_tracks
    flac_count = len([t for t, exts in token_to_exts.items() if exts.intersection({'.flac', '.wav'})])
    lossy_count = len([t for t, exts in token_to_exts.items() if exts.intersection({'.mp3', '.m4a', '.webm'})])
    mp3_count = len([t for t, exts in token_to_exts.items() if '.mp3' in exts])
    m4a_count = len([t for t, exts in token_to_exts.items() if '.m4a' in exts])
    unconverted_count = 0
    for tokens_tuple, exts in token_to_exts.items():
        if '.m4a' in exts and '.mp3' not in exts:
            unconverted_count += 1

    # 2. Duplicate/Savings Stats
    pl_files = glob.glob(os.path.join(playlists_path, "*.m3u8")) + \
               glob.glob(os.path.join(playlists_path, "*.m3u")) + \
               glob.glob(os.path.join(playlists_path, "*.txt"))
    
    all_pl_songs = []
    unique_pl_songs = set()
    unique_pl_tokens = set()
    skip_markers = ["_unsorted", "single tracks", "_unsorted_songs"]
    for pl_file in pl_files:
        base = os.path.basename(pl_file).lower()
        if any(x in base for x in skip_markers):
            continue
        songs = parse_playlist(pl_file)
        all_pl_songs.extend(songs)
        for s in songs:
            unique_pl_songs.add(s)
            t = tuple(get_normalized_tokens(s))
            if t:
                unique_pl_tokens.add(t)
    
    total_playlist_entries = len(all_pl_songs)
    unique_playlist_entries = len(unique_pl_songs)
    unique_playlist_tokens = len(unique_pl_tokens)
    not_in_playlists_count = 0
    if library_tokens:
        not_in_playlists_count = len([t for t in library_tokens if t not in unique_pl_tokens])
    
    # Calculate actual savings by summing sizes of duplicate songs
    duplicates_count = total_playlist_entries - unique_playlist_entries
    
    # Build song name to file path mapping for accurate size calculation
    song_to_files = {}
    for file_path in audio_files:
        if os.path.exists(file_path):
            filename = os.path.basename(file_path)
            name_no_ext = os.path.splitext(filename)[0]
            tokens_tuple = tuple(get_normalized_tokens(name_no_ext))
            if tokens_tuple:
                if tokens_tuple not in song_to_files:
                    song_to_files[tokens_tuple] = []
                song_to_files[tokens_tuple].append(file_path)
    
    # Count song occurrences in playlists
    song_occurrences = {}
    for pl_file in pl_files:
        songs = parse_playlist(pl_file)
        for song_name in songs:
            query_tokens = tuple(get_normalized_tokens(song_name))
            if query_tokens:
                if query_tokens not in song_occurrences:
                    song_occurrences[query_tokens] = 0
                song_occurrences[query_tokens] += 1
    
    # Calculate actual savings: for each song that appears multiple times, 
    # add (occurrences - 1) * total_file_size (sum of all formats: MP3 + FLAC etc.)
    actual_savings_bytes = 0
    for tokens_tuple, occurrences in song_occurrences.items():
        if occurrences > 1 and tokens_tuple in song_to_files:
            # Sum sizes of ALL format files for this song (e.g. MP3 + FLAC)
            song_total_size = 0
            for file_path in song_to_files[tokens_tuple]:
                if os.path.exists(file_path):
                    try:
                        song_total_size += os.path.getsize(file_path)
                    except (OSError, IOError):
                        continue
            if song_total_size > 0:
                actual_savings_bytes += (occurrences - 1) * song_total_size
    
    savings_mb = actual_savings_bytes / (1024 * 1024)
    
    return {
          'total_songs': unique_library_tracks,
          'flac_count': flac_count,
          'lossy_count': lossy_count,
          'mp3_count': mp3_count,
          'm4a_count': m4a_count,
          'total_size_mb': total_size_mb,
          'recent_5': recent_5,
          'total_playlist_entries': total_playlist_entries,
          'unique_playlist_entries': unique_playlist_entries,
          'unique_playlist_tokens': unique_playlist_tokens,
          'duplicates_count': duplicates_count,
          'savings_mb': savings_mb,
          'unconverted_count': unconverted_count,
          'not_in_playlists_count': not_in_playlists_count
      }
