"""
Snapshot Manager for tracking removed songs from Spotify playlists.
Provides persistent storage and comparison of playlist states across sync sessions.
"""

import os
import json
from datetime import datetime
from utils.helpers import sanitize_filename
from utils.config import get_data_file

SNAPSHOT_CACHE_FILENAME = 'snapshot_cache.json'
REMOVED_SONGS_FILENAME = '_Removed Songs.m3u8'
LEGACY_REMOVED_SONGS_FILENAMES = (
    REMOVED_SONGS_FILENAME,
    '_已移除的歌曲.m3u8',
)


def load_snapshot_cache():
    """
    Load snapshot cache from JSON file.
    Returns dict with playlists state, or empty dict if not exists.
    """
    cache_path = get_data_file(SNAPSHOT_CACHE_FILENAME)
    if not os.path.exists(cache_path):
        return {"playlists": {}, "version": "1.0"}
    
    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, dict) and "playlists" in data:
                return data
            return {"playlists": {}, "version": "1.0"}
    except Exception:
        return {"playlists": {}, "version": "1.0"}


def save_snapshot_cache(cache_data):
    """
    Save snapshot cache to JSON file.
    """
    cache_path = get_data_file(SNAPSHOT_CACHE_FILENAME)
    try:
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def get_removed_songs_playlist_paths(playlists_path):
    """Return removed-songs playlist candidates, canonical path first."""
    if not playlists_path:
        return []

    return [os.path.join(playlists_path, name) for name in LEGACY_REMOVED_SONGS_FILENAMES]


def get_removed_songs_playlist_path(playlists_path):
    """Return the canonical removed-songs playlist path."""
    if not playlists_path:
        return None
    return os.path.join(playlists_path, REMOVED_SONGS_FILENAME)


def is_removed_songs_playlist_name(name):
    """Return True when a playlist filename/stem matches removed-songs aliases."""
    if not name:
        return False

    normalized = os.path.splitext(os.path.basename(name))[0].strip().lower()
    aliases = {
        os.path.splitext(filename)[0].strip().lower()
        for filename in LEGACY_REMOVED_SONGS_FILENAMES
    }
    return normalized in aliases


def _read_removed_songs_entries(path):
    """Read removed-songs entries from one playlist file while preserving order."""
    entries = []
    if not path or not os.path.exists(path):
        return entries

    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            lines = [line.rstrip('\r\n') for line in f.readlines()]
    except UnicodeDecodeError:
        with open(path, 'r', encoding='gbk', errors='ignore') as f:
            lines = [line.rstrip('\r\n') for line in f.readlines()]
    except Exception:
        return entries

    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith('#EXTINF:'):
            parts = line.split(',', 1)
            track_name = parts[1].strip() if len(parts) > 1 else ''
            path_line = ''
            if index + 1 < len(lines):
                path_line = lines[index + 1].strip()
            if track_name:
                entries.append((track_name, path_line))
            index += 2
            continue
        index += 1

    return entries


def normalize_removed_songs_playlist(playlists_path):
    """
    Collapse legacy removed-songs playlists into the canonical file.

    Returns:
        Dict with keys: canonical_path, migrated, merged, removed_legacy, total_tracks.
    """
    canonical_path = get_removed_songs_playlist_path(playlists_path)
    result = {
        "canonical_path": canonical_path,
        "migrated": False,
        "merged": False,
        "removed_legacy": [],
        "total_tracks": 0,
    }
    if not playlists_path:
        return result

    candidate_paths = get_removed_songs_playlist_paths(playlists_path)
    existing_paths = [path for path in candidate_paths if os.path.exists(path)]
    if not existing_paths:
        return result

    legacy_paths = [path for path in existing_paths if os.path.normcase(path) != os.path.normcase(canonical_path)]
    if not legacy_paths:
        result["total_tracks"] = len(_read_removed_songs_entries(canonical_path))
        return result

    if not os.path.exists(canonical_path) and len(existing_paths) == 1:
        os.replace(existing_paths[0], canonical_path)
        result["migrated"] = True
        result["removed_legacy"].append(existing_paths[0])
        result["total_tracks"] = len(_read_removed_songs_entries(canonical_path))
        return result

    merged_entries = []
    seen_tracks = set()
    for path in existing_paths:
        for track_name, entry_path in _read_removed_songs_entries(path):
            if track_name in seen_tracks:
                continue
            seen_tracks.add(track_name)
            merged_entries.append((track_name, entry_path))

    os.makedirs(playlists_path, exist_ok=True)
    with open(canonical_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write("#EXTM3U\n")
        for track_name, entry_path in merged_entries:
            f.write(f"#EXTINF:-1,{track_name}\n")
            f.write(f"{entry_path}\n")

    result["merged"] = True
    result["total_tracks"] = len(merged_entries)
    for path in legacy_paths:
        try:
            os.remove(path)
            result["removed_legacy"].append(path)
        except Exception:
            pass
    return result


def detect_removed_songs(old_tracks, current_tracks):
    """
    Compare old and current track lists to find removed songs.
    
    Args:
        old_tracks: List of track names from previous snapshot
        current_tracks: List of track names from current Spotify fetch
    
    Returns:
        List of track names that exist in old but not in current
    """
    if not old_tracks:
        return []
    
    old_set = set(old_tracks)
    current_set = set(current_tracks)
    
    removed = old_set - current_set
    return list(removed)


def update_snapshot(cache_data, playlist_name, tracks):
    """
    Update snapshot data for a specific playlist.
    
    Args:
        cache_data: The full cache dictionary
        playlist_name: Name of the playlist to update
        tracks: List of current track names
    """
    if "playlists" not in cache_data:
        cache_data["playlists"] = {}
    
    cache_data["playlists"][playlist_name] = {
        "tracks": tracks.copy(),
        "last_updated": datetime.now().isoformat()
    }


def get_existing_removed_songs(playlists_path):
    """
    Get list of songs already in removed songs playlist to avoid duplicates.
    
    Returns:
        Set of track names (format: "Artist - Song")
    """
    existing = set()

    for removed_m3u_path in get_removed_songs_playlist_paths(playlists_path):
        for track_name, _ in _read_removed_songs_entries(removed_m3u_path):
            existing.add(track_name)

    return existing


def append_to_removed_songs_m3u8(removed_tracks, config, lib_index):
    """
    Append removed tracks to removed songs playlist file.
    Uses Echo Nightly compatible format (UTF-8 no BOM, LF, URI encoded paths).
    
    Args:
        removed_tracks: List of track names to append
        config: Application configuration
        lib_index: Library index for resolving file paths
    """
    if not removed_tracks:
        return 0
    
    playlists_path = config.get('playlists_path')
    if not playlists_path:
        return 0

    normalize_removed_songs_playlist(playlists_path)
    removed_m3u_path = get_removed_songs_playlist_path(playlists_path)
    
    # Get existing tracks to avoid duplicates
    existing_tracks = get_existing_removed_songs(playlists_path)
    
    # Filter out already recorded tracks
    new_tracks = [t for t in removed_tracks if t not in existing_tracks]
    
    if not new_tracks:
        return 0
    
    # Import needed functions
    from core.library import find_song_in_library
    
    # Prepare entries
    entries = []
    for track in new_tracks:
        # Try to find the file in library
        actual_path = find_song_in_library(track, lib_index)
        
        if actual_path and os.path.exists(actual_path):
            # Calculate relative path from playlists folder
            abs_song_path = os.path.normpath(os.path.abspath(actual_path))
            abs_playlists_path = os.path.normpath(os.path.abspath(playlists_path))
            
            try:
                rel_path = os.path.relpath(abs_song_path, start=abs_playlists_path)
            except ValueError:
                # Cross-drive fallback
                rel_path = abs_song_path.replace('\\', '/')
                if ':' in rel_path:
                    rel_path = rel_path.split(':', 1)[1].lstrip('/\\')
            
            # Format: forward slashes (URI encoding removed for Windows/Echo compatibility)
            m3u_entry_path = rel_path.replace('\\', '/')
        else:
            # If file not found, use a placeholder path (will be resolved later)
            safe_filename = sanitize_filename(track)
            m3u_entry_path = f"../Music/{safe_filename}.mp3"
        
        entries.append((track, m3u_entry_path))
    
    # Write to file (append mode, Echo Nightly compatible format)
    mode = 'a' if os.path.exists(removed_m3u_path) else 'w'
    with open(removed_m3u_path, mode, encoding='utf-8', newline='\n') as f:
        # If new file, write header
        if mode == 'w':
            f.write("#EXTM3U\n")
        
        for track, path in entries:
            f.write(f"#EXTINF:-1,{track}\n")
            f.write(f"{path}\n")
    
    return len(entries)


def process_playlist_snapshot(playlist_name, current_tracks, config, lib_index):
    """
    Process a single playlist: detect removed songs and update snapshot.
    
    Args:
        playlist_name: Name of the playlist
        current_tracks: Current list of track names from Spotify
        config: Application configuration
        lib_index: Library index for resolving file paths
    
    Returns:
        Tuple of (removed_count, all_removed_tracks)
    """
    # Load existing snapshot
    cache_data = load_snapshot_cache()
    
    # Get old tracks for this playlist
    old_data = cache_data.get("playlists", {}).get(playlist_name, {})
    old_tracks = old_data.get("tracks", [])
    
    # Detect removed songs
    removed = detect_removed_songs(old_tracks, current_tracks)
    
    # Append removed songs to M3U8
    appended_count = 0
    if removed:
        appended_count = append_to_removed_songs_m3u8(removed, config, lib_index)
    
    # Update snapshot with current tracks
    update_snapshot(cache_data, playlist_name, current_tracks)
    save_snapshot_cache(cache_data)
    
    return appended_count, removed
