import os

FAVORITES_PLAYLIST = "_Favorites.m3u8"


def favorites_path(config):
    return os.path.join(config.get('playlists_path', ''), FAVORITES_PLAYLIST)


def load_favorites(config):
    """Return list of absolute song paths stored in the favorites playlist."""
    path = favorites_path(config)
    if not os.path.exists(path):
        return []
    playlists_path = os.path.abspath(config.get('playlists_path', ''))
    songs = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if os.path.isabs(line):
                    songs.append(os.path.normpath(line))
                else:
                    songs.append(os.path.normpath(os.path.join(playlists_path, line)))
    except Exception:
        return []
    return songs


def is_favorite(config, song_path):
    target = os.path.normpath(os.path.abspath(song_path))
    return any(os.path.normpath(os.path.abspath(p)) == target for p in load_favorites(config))


def toggle_favorite(config, song_path):
    """Toggle a song in favorites. Returns True when now favorited."""
    target = os.path.normpath(os.path.abspath(song_path))
    favorites = load_favorites(config)
    normed = [os.path.normpath(os.path.abspath(p)) for p in favorites]
    if target in normed:
        kept = [p for p, n in zip(favorites, normed) if n != target]
        _write_favorites(config, kept)
        return False
    favorites.append(target)
    _write_favorites(config, favorites)
    return True


def _write_favorites(config, songs):
    """Write favorites playlist with raw relative paths (Echo Nightly compatible)."""
    from urllib.parse import unquote

    playlists_path = os.path.abspath(config.get('playlists_path', ''))
    os.makedirs(playlists_path, exist_ok=True)
    with open(favorites_path(config), 'w', encoding='utf-8', newline='\n') as f:
        f.write("#EXTM3U\n")
        for song in songs:
            abs_path = os.path.normpath(os.path.abspath(unquote(song)))
            try:
                rel_path = os.path.relpath(abs_path, playlists_path).replace('\\', '/')
            except ValueError:
                rel_path = abs_path.replace('\\', '/')
            name = os.path.splitext(os.path.basename(abs_path))[0]
            f.write(f"#EXTINF:-1,{name}\n")
            f.write(f"{rel_path}\n")