import os
import json
import requests
from bs4 import BeautifulSoup
from zhconv import convert
from utils.helpers import sanitize_filename
from utils.config import ensure_dirs, get_data_file

def _song_key(song_name):
    """Stable key for per-track URL mapping."""
    return sanitize_filename(song_name).strip().lower()

def _extract_track_spotify_url(track_obj):
    """Extract canonical Spotify track URL from a Spotify track payload."""
    if not isinstance(track_obj, dict):
        return None

    external_urls = track_obj.get('external_urls')
    if isinstance(external_urls, dict):
        ext_sp = external_urls.get('spotify')
        if ext_sp:
            return ext_sp

    direct_url = track_obj.get('shareUrl') or track_obj.get('url') or track_obj.get('spotify_url')
    if direct_url and isinstance(direct_url, str) and "open.spotify.com/track/" in direct_url:
        return direct_url

    uri = track_obj.get('uri')
    if isinstance(uri, str) and uri.startswith("spotify:track:"):
        track_id = uri.split(":")[-1].strip()
        if track_id:
            return f"https://open.spotify.com/track/{track_id}"

    track_id = track_obj.get('id')
    if isinstance(track_id, str) and track_id.strip():
        return f"https://open.spotify.com/track/{track_id.strip()}"

    return None

def get_spotify_name(sp_url):
    """Helper to fetch ONLY the name of a Spotify playlist, artist, or album from its embed page"""
    sp_id = None
    is_artist = "artist/" in sp_url
    is_album = "album/" in sp_url
    
    if is_artist:
        try:
            sp_id = sp_url.split('?')[0].split('artist/')[-1]
        except: return None
    elif is_album:
        try:
            sp_id = sp_url.split('?')[0].split('album/')[-1]
        except: return None
    elif "playlist/" in sp_url:
        try:
            sp_id = sp_url.split('?')[0].split('playlist/')[-1]
        except: return None
    elif "track/" in sp_url:
        try:
            sp_id = sp_url.split('?')[0].split('track/')[-1]
        except: return None
    else: 
        sp_id = sp_url.strip()
    
    if not sp_id: return None
    
    if is_artist:
        type_path = "artist"
    elif is_album:
        type_path = "album"
    elif "track/" in sp_url:
        type_path = "track"
    else:
        type_path = "playlist"
    
    embed_url = f"https://open.spotify.com/embed/{type_path}/{sp_id}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
    }
    
    try:
        resp = requests.get(embed_url, headers=headers, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Try NEXT_DATA
        next_data_tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_data_tag:
            data = json.loads(next_data_tag.string)
            entity = data.get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('entity', {})
            if entity and 'name' in entity:
                return convert(entity['name'], 'zh-tw')
        
        # Try meta tag as fallback for name
        meta_title = soup.find("meta", property="og:title")
        if meta_title:
             raw_name = meta_title.get("content", "")
             if "on Spotify" in raw_name: raw_name = raw_name.split("on Spotify")[0].strip()
             return convert(raw_name, 'zh-tw')

    except: pass
    return None

def scrape_via_spotify_embed(config, stats, log_func, target_urls=None, skip_sync=False):
    """
    Scrape Spotify playlists via embed API.

    Args:
        skip_sync: If True, only fetch playlist name and track list without
                  scanning library or writing M3U files. Useful for adding
                  new playlists quickly.
    """
    from utils.i18n import _
    target_urls = target_urls or config.get('spotify_urls', [])
    if not target_urls:
        log_func(_('skip_no_urls'))
        return

    playlists_path = config['playlists_path']
    ensure_dirs(config)

    import datetime
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    last_updated = config.get('last_updated', {})
    
    track_map_path = get_data_file('spotify_track_map.json')
    track_url_map = {}
    try:
        if os.path.exists(track_map_path) and os.path.getsize(track_map_path) > 0:
            with open(track_map_path, 'r', encoding='utf-8') as tf:
                loaded_map = json.load(tf)
                if isinstance(loaded_map, dict):
                    track_url_map = loaded_map
    except Exception as map_e:
        log_func(f" -> 讀取 Spotify track URL 快取失敗: {map_e}")
        track_url_map = {}
    track_map_updated = False
    track_map_added = 0
    track_map_changed = 0

    for sp_url in target_urls:
        if stats and stats.stop_event and stats.stop_event.is_set():
            return
        
        # Skip if already updated today
        if last_updated.get(sp_url) == today:
            name = config.get('url_names', {}).get(sp_url, sp_url)
            # log_func(_('skip_synced', name)) # Suppressed to reduce noise
            # Even if skipped, ensure the playlist name exists in changes dict for report consistency
            if stats and name not in stats.playlist_changes:
                stats.playlist_changes[name] = {'added': [], 'removed': []}
            continue

        sp_id = None
        is_artist = "artist/" in sp_url
        is_album = "album/" in sp_url
        
        if is_artist:
            try:
                sp_id = sp_url.split('?')[0].split('artist/')[-1]
            except: pass
        elif is_album:
            try:
                sp_id = sp_url.split('?')[0].split('album/')[-1]
            except: pass
        elif "playlist/" in sp_url:
            try:
                # Remove query params
                clean_url = sp_url.split('?')[0]
                sp_id = clean_url.split('playlist/')[-1]
            except: pass
        elif "track/" in sp_url:
            try:
                # Remove query params
                clean_url = sp_url.split('?')[0]
                sp_id = clean_url.split('track/')[-1]
            except: pass
        else:
             sp_id = sp_url.strip()

        if not sp_id:
            log_func(_('skip_invalid', sp_url))
            continue

        if is_artist:
            type_path = "artist"
        elif is_album:
            type_path = "album"
        elif "track/" in sp_url:
            type_path = "track"
        else:
            type_path = "playlist"
            
        embed_url = f"https://open.spotify.com/embed/{type_path}/{sp_id}"
        log_func(_('scanning_pl', sp_id))
        log_func(_('connecting_spotify'))
        
        try:
            if stats and hasattr(stats, 'pause_event'):
                 stats.pause_event.wait()
            
            # Check for cancellation before making request
            if stats and stats.stop_event and stats.stop_event.is_set():
                return

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            resp = requests.get(embed_url, headers=headers, timeout=10)  # Add timeout
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            tracks = []
            pl_name = None
            
            # Special handling for single tracks
            if "track/" in sp_url:
                # For single tracks, extract the track info and add directly to download list
                next_data_tag = soup.find("script", {"id": "__NEXT_DATA__"})
                if next_data_tag:
                    try:
                        data = json.loads(next_data_tag.string)
                        
                        def get_path(obj, keys):
                            curr = obj
                            for k in keys:
                                if isinstance(curr, dict) and k in curr: curr = curr[k]
                                else: return None
                            return curr

                        entity = get_path(data, ['props', 'pageProps', 'state', 'data', 'entity'])
                        if entity:
                            track_name = entity.get('name')
                            artists = entity.get('artists', [])
                            if track_name and artists:
                                artist_name = artists[0].get('name')
                                full_track_name = f"{artist_name} - {track_name}"
                                tracks.append(full_track_name)
                                pl_name = sanitize_filename(full_track_name)
                                log_func(f" -> 找到單曲: {full_track_name}")
                                
                                single_track_url = _extract_track_spotify_url(entity)
                                if single_track_url:
                                    track_key = _song_key(full_track_name)
                                    previous_track_url = track_url_map.get(track_key)
                                    if previous_track_url != single_track_url:
                                        if previous_track_url is None:
                                            track_map_added += 1
                                        else:
                                            track_map_changed += 1
                                        track_url_map[track_key] = single_track_url
                                        track_map_updated = True
                                
                                # --- NEW: Metadata caching for single track ---
                                try:
                                    from utils.config import CONFIG_DIR
                                    cache_dir = os.path.join(CONFIG_DIR, 'spotify_cache')
                                    os.makedirs(cache_dir, exist_ok=True)
                                    
                                    meta = {
                                        'title': track_name,
                                        'artist': artist_name,
                                    }
                                    
                                    # Try to reach album or visual identity
                                    album = entity.get('album', {})
                                    if album:
                                        meta['album'] = album.get('name', '')
                                        meta['release_date'] = album.get('release_date') or album.get('date', '')
                                        images = album.get('images', [])
                                        if images and len(images) > 0:
                                            meta['cover_url'] = images[0].get('url', '')
                                    
                                    # Fallback to visualIdentity for covers (common in tracks)
                                    if not meta.get('cover_url'):
                                        images = get_path(entity, ['visualIdentity', 'image'])
                                        if images and len(images) > 0:
                                            meta['cover_url'] = images[0].get('url', '')
                                            
                                    clean_filename = sanitize_filename(full_track_name)
                                    meta_file = os.path.join(cache_dir, f"{clean_filename}.json")
                                    with open(meta_file, 'w', encoding='utf-8') as mf:
                                        json.dump(meta, mf, ensure_ascii=False, indent=2)
                                except Exception as meta_e:
                                    log_func(f" -> 儲存 Metadata 快取失敗: {meta_e}")
                                # --- END NEW ---
                                
                        # FINAL FALLBACK: If meta is missing cover or album, try OG tags
                        if not tracks: # or if we want to enrich HTML fallback
                             pass # we can do more here if needed
                    except Exception as e:
                        log_func(_('json_error', e))
                
                # Fallback to HTML parsing if JSON fails or is incomplete
                if not tracks:
                    try:
                        title_tag = soup.find("h1") or soup.find("meta", property="og:title")
                        artist_tag = soup.find("h2") or soup.find("meta", property="og:description")
                        if title_tag:
                            title = title_tag.get_text(strip=True) if not title_tag.get('content') else title_tag.get('content')
                            # Handle "Artist - Song" format in title or description
                            if artist_tag:
                                artist = artist_tag.get_text(strip=True) if not artist_tag.get('content') else artist_tag.get('content').split('·')[0].strip()
                            else:
                                artist = "Unknown"
                                
                            full_track_name = f"{artist} - {title}"
                            tracks.append(full_track_name)
                            pl_name = sanitize_filename(full_track_name)
                            log_func(f" -> 找到單曲 (HTML Fallback): {full_track_name}")
                            
                            # Cache basic meta from HG/OG tags
                            try:
                                from utils.config import CONFIG_DIR
                                cache_dir = os.path.join(CONFIG_DIR, 'spotify_cache')
                                os.makedirs(cache_dir, exist_ok=True)
                                
                                meta = {'title': title, 'artist': artist}
                                og_image = soup.find("meta", property="og:image")
                                if og_image:
                                    meta['cover_url'] = og_image.get('content')
                                
                                clean_filename = sanitize_filename(full_track_name)
                                meta_file = os.path.join(cache_dir, f"{clean_filename}.json")
                                with open(meta_file, 'w', encoding='utf-8') as mf:
                                    json.dump(meta, mf, ensure_ascii=False, indent=2)
                            except: pass
                    except Exception as e:
                        log_func(f" -> 單曲解析特急錯誤: {e}")
            else:
                # Regular playlist/album/artist processing
                if is_artist:
                    prefix = "Artist"
                elif is_album:
                    prefix = "Album"
                else:
                    prefix = "Spotify"
                pl_name = f"{prefix}_{sp_id}"

            # Skip regular processing for single tracks since they're already handled above
            if "track/" not in sp_url:
                next_data_tag = soup.find("script", {"id": "__NEXT_DATA__"})
                if next_data_tag:
                    try:
                        data = json.loads(next_data_tag.string)
                        def get_path(obj, keys):
                            curr = obj
                            for k in keys:
                                if isinstance(curr, dict) and k in curr: curr = curr[k]
                                else: return None
                            return curr

                        entity = get_path(data, ['props', 'pageProps', 'state', 'data', 'entity'])
                        if entity:
                            if 'name' in entity: 
                                raw_name = convert(entity['name'], 'zh-tw')
                                pl_name = sanitize_filename(raw_name)
                            
                            track_list = entity.get('trackList') or \
                                        entity.get('topTracks') or \
                                        (entity.get('tracks') and entity.get('tracks').get('items')) or \
                                        (entity.get('tracks') and entity.get('tracks').get('data'))
                            
                            if track_list:
                                log_func(f" -> JSON 解析: 找到 {len(track_list)} 首歌曲")
                                import re
                                def clean_artist_name(name):
                                    # Remove "E" prefix (Explicit tag artifact)
                                    if not name: return name
                                    return re.sub(r'^E(?=[A-Z\u4e00-\u9fff\u3040-\u30ff])', '', name)

                                for item in track_list:
                                    track = item.get('track', item)
                                    
                                    # Handle both old and new JSON formats
                                    # Old format: name, artists[]
                                    # New format: title, subtitle
                                    name = track.get('name') or track.get('title')
                                    artists = track.get('artists', [])
                                    
                                    if artists and len(artists) > 0:
                                        artist_name = clean_artist_name(artists[0].get('name'))
                                    else:
                                        # Try new format: subtitle field contains artist
                                        artist_name = clean_artist_name(track.get('subtitle'))
                                    
                                    if name:
                                        if artist_name:
                                            # Use "title - artist" format to match Spotify/Spotube naming convention
                                            full_track_name = f"{name} - {artist_name}"
                                        else:
                                            full_track_name = name
                                        tracks.append(full_track_name)
                                        
                                        track_url = _extract_track_spotify_url(track)
                                        if track_url:
                                            track_key = _song_key(full_track_name)
                                            previous_track_url = track_url_map.get(track_key)
                                            if previous_track_url != track_url:
                                                if previous_track_url is None:
                                                    track_map_added += 1
                                                else:
                                                    track_map_changed += 1
                                                track_url_map[track_key] = track_url
                                                track_map_updated = True
                                        
                                        # --- NEW: Extract and save rich metadata ---
                                        try:
                                            # Try to create a cache directory for Spotify metadata
                                            from utils.config import CONFIG_DIR
                                            cache_dir = os.path.join(CONFIG_DIR, 'spotify_cache')
                                            os.makedirs(cache_dir, exist_ok=True)
                                            
                                            meta = {
                                                'title': name,
                                                'artist': artist_name,
                                            }
                                            
                                            # Try to get album info
                                            album = track.get('album', {})
                                            if album:
                                                meta['album'] = album.get('name', '')
                                                meta['release_date'] = album.get('release_date') or album.get('date', '')
                                                # Try to get cover art
                                                images = album.get('images', [])
                                                if images and len(images) > 0:
                                                    meta['cover_url'] = images[0].get('url', '')
                                            
                                            # Fallback for playlist tracks too
                                            if not meta.get('cover_url'):
                                                images = get_path(track, ['visualIdentity', 'image'])
                                                if images and len(images) > 0:
                                                    meta['cover_url'] = images[0].get('url', '')
                                                    
                                            elif is_album and 'name' in entity:
                                                meta['album'] = entity['name']
                                                
                                            # Save to JSON
                                            clean_filename = sanitize_filename(full_track_name)
                                            meta_file = os.path.join(cache_dir, f"{clean_filename}.json")
                                            with open(meta_file, 'w', encoding='utf-8') as mf:
                                                json.dump(meta, mf, ensure_ascii=False, indent=2)
                                                
                                        except Exception as meta_e:
                                            log_func(f" -> 儲存 Metadata 快取失敗: {meta_e}")
                                        # --- END NEW ---
                                        
                    except Exception as e:
                        log_func(_('json_error', e))

            # HTML fallback for playlists/albums/artists only
            if not tracks and "track/" not in sp_url:
                 rows = soup.find_all("li", class_=lambda x: x and "TracklistRow_trackListRow" in x)
                 if rows:
                     log_func(f" -> HTML 備援解析: 找到 {len(rows)} 首歌曲")
                     import re
                     def clean_html_text(text):
                         # Aggressively clean "E" prefix which often appears in HTML scraping
                         if not text: return text
                         return re.sub(r'^E(?=[A-Z\u4e00-\u9fff\u3040-\u30ff])', '', text)

                     for row in rows:
                         t_tag = row.find("h3", class_=lambda x: x and "TracklistRow_title" in x)
                         a_tag = row.find("h4", class_=lambda x: x and "TracklistRow_subtitle" in x)
                         
                         if t_tag and a_tag:
                             # Try to get direct text if possible, but get_text is safer for coverage
                             artist_text = a_tag.get_text(strip=True)
                             title_text = t_tag.get_text(strip=True)
                             
                             artist_clean = clean_html_text(artist_text)
                             tracks.append(f"{artist_clean} - {title_text}")

            # Save name mapping even if no tracks were resolved
            if pl_name:
                url_names = config.get('url_names', {})
                if url_names.get(sp_url) != pl_name:
                    url_names[sp_url] = pl_name
                    config['url_names'] = url_names
                    from utils.config import save_config
                    save_config(config)

            if tracks:
                # Save name to config mapping
                if 'url_names' not in config: config['url_names'] = {}
                config['url_names'][sp_url] = pl_name

                # Record today as last updated
                if 'last_updated' not in config: config['last_updated'] = {}
                config['last_updated'][sp_url] = today

                from utils.config import save_config
                save_config(config)

                # If skip_sync, only save name and log, don't scan library or write M3U
                if skip_sync:
                    log_func(f" -> 已儲存歌單 '{pl_name}' ({len(tracks)} 首) - 同步將在更新時執行")
                    continue

                # For single tracks, don't create playlist files - just mark as processed
                if "track/" not in sp_url:
                    from core.library import parse_playlist # Local import to avoid circular dep if any
                    
                    # Cleanup old M3U8 if name changed
                    old_pl_name = config.get('url_names', {}).get(sp_url)
                    if old_pl_name and old_pl_name != pl_name:
                        old_path = os.path.join(playlists_path, f"{old_pl_name}.m3u8")
                        if os.path.exists(old_path):
                            try:
                                os.remove(old_path)
                                log_func(f"清理舊的播放清單檔: {old_pl_name}.m3u8")
                            except: pass
                        # Also cleanup legacy .m3u if it exists
                        legacy_path = os.path.join(playlists_path, f"{old_pl_name}.m3u")
                        if os.path.exists(legacy_path):
                             try: os.remove(legacy_path)
                             except: pass

                    m3u_path = os.path.join(playlists_path, f"{pl_name}.m3u8")
                
                # Only process playlist files for non-tracks
                if "track/" not in sp_url:
                    # Check if file exists to compare
                    old_songs = set()
                    if os.path.exists(m3u_path):
                        old_songs = set(parse_playlist(m3u_path))
                    
                    new_songs = set(tracks)
                    added = list(new_songs - old_songs)
                    removed = list(old_songs - new_songs)
                    
                    # Always initialize the key for the report
                    if stats and pl_name not in stats.playlist_changes:
                        stats.playlist_changes[pl_name] = {'added': [], 'removed': []}

                    if stats and (added or removed):
                        stats.playlist_changes[pl_name] = {'added': added, 'removed': removed}

                    # Get library path from config to calculate relative path
                    library_path = config.get('library_path', 'Music')
                    log_func(f" -> 掃描音樂庫: {library_path}")
                    
                    # Build index to resolve actual filenames (handles "E" prefix and diff extensions)
                    log_func(_('scanning_lib'))
                    import glob
                    search_pattern = os.path.join(library_path, "**", "*")
                    all_files = glob.glob(search_pattern, recursive=True)
                    audio_cache = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]
                    from core.library import build_library_index, build_metadata_index, find_song_in_library, find_song_exact_format, find_song_simple_match
                    lib_index = build_library_index(audio_cache)
                    mp3_files = [f for f in audio_cache if f.lower().endswith('.mp3')]
                    mp3_index = build_library_index(mp3_files)
                    metadata_index = build_metadata_index(mp3_files)
                    all_metadata_index = build_metadata_index(audio_cache)
                    log_func(f" -> 音樂庫索引建立完成: {len(audio_cache)} 個音訊檔案, {len(lib_index)} 個索引項目")
                    # Debug: show first few audio files found
                    if audio_cache:
                        log_func(f"    範例檔案: {os.path.basename(audio_cache[0])}")
                        if len(audio_cache) > 1:
                            log_func(f"    範例檔案: {os.path.basename(audio_cache[1])}")

                # Only write M3U files for playlists/albums/artists
                if "track/" not in sp_url:
                    # Echo Nightly compatible format: UTF-8 (NO BOM), LF line endings, URI encoded paths
                    with open(m3u_path, 'w', encoding='utf-8', newline='\n') as f:
                        f.write("#EXTM3U\n")
                        missing_tracks = 0
                        kept_tracks = 0
                        # Debug: write Spotify tracks to file for diagnosis
                        if tracks:
                            log_func(f"    Spotify 抓取共 {len(tracks)} 首")
                            debug_file = os.path.join(config.get('playlists_path', '.'), '_spotify_debug.txt')
                            with open(debug_file, 'w', encoding='utf-8') as dbg_f:
                                for i, track in enumerate(tracks):
                                    dbg_f.write(f"{i+1}. {track}\n")
                        
                        for track in tracks:
                            clean_track = track.strip()

                            # Find actual file in library (MP3 only)
                            actual_path = None
                            # For Spotube: use simple exact match first (filenames match Spotify exactly)
                            if config.get('spotube_exact_match', True):
                                actual_path = find_song_simple_match(clean_track, 'mp3', lib_index)
                            # Fallback to fuzzy matching if simple match fails
                            if not actual_path:
                                actual_path = find_song_exact_format(clean_track, 'mp3', lib_index)
                            # Final MP3 fallback: use title metadata when Spotube filename is abbreviated.
                            if not actual_path and metadata_index:
                                actual_path = find_song_in_library(clean_track, mp3_index, metadata_index=metadata_index)
                            if not actual_path:
                                missing_tracks += 1
                                # Debug: log all missing tracks
                                log_func(f"    ⚠️ 找不到: {clean_track}")
                                continue
                            kept_tracks += 1
                            
                            # Ensure all paths are absolute and normalized first
                            abs_song_path = os.path.normpath(os.path.abspath(actual_path))
                            abs_playlists_path = os.path.normpath(os.path.abspath(playlists_path))
                            
                            # Calculate relative path from Playlists folder to Music folder (e.g. ../Music/Song.mp3)
                            # rel_path will generate the necessary '..' prefix automatically.
                            try:
                                rel_path = os.path.relpath(abs_song_path, start=abs_playlists_path)
                            except ValueError:
                                # Cross-drive issue: use absolute path or fallback
                                # Use forward slashes and remove drive letter for compatibility
                                rel_path = abs_song_path.replace('\\', '/')
                                if ':' in rel_path:
                                    # Remove drive letter for cross-drive compatibility
                                    rel_path = rel_path.split(':', 1)[1].lstrip('/\\')
                                # Fallback to absolute path if relative path fails
                                rel_path = abs_song_path
                            

                            # Standardization: Forward slashes (/) are best for M3U8 and avoid separator issues
                            from utils.helpers import encode_uri_path
                            m3u_entry_path = encode_uri_path(rel_path.replace('\\', '/'))
                            
                            # Write EXTINF and the relative path with LF (Echo Nightly compatible)
                            f.write(f"#EXTINF:-1,{clean_track}\n")
                            f.write(f"{m3u_entry_path}\n")
                    log_func(_('saved_tracks', kept_tracks, os.path.basename(m3u_path)))
                    if missing_tracks > 0:
                        log_func(f" -> 略過 {missing_tracks} 首本機找不到的歌曲，未寫入 {os.path.basename(m3u_path)}")
                    if stats: stats.playlists_scanned += 1
                    
                    # Snapshot diff: Track removed songs across sync sessions
                    try:
                        from core.snapshot_manager import (
                            load_snapshot_cache, detect_removed_songs,
                            update_snapshot, save_snapshot_cache,
                            append_to_removed_songs_m3u8
                        )
                        
                        cache_data = load_snapshot_cache()
                        old_tracks = cache_data.get("playlists", {}).get(pl_name, {}).get("tracks", [])
                        removed = detect_removed_songs(old_tracks, tracks)
                        
                        if removed:
                            # Append removed songs to _Removed Songs.m3u8
                            appended = append_to_removed_songs_m3u8(removed, config, lib_index)
                            if appended > 0:
                                log_func(f" -> 發現並記錄 {appended} 首下架歌曲到 '_Removed Songs.m3u8'")
                        
                        # Update snapshot with current tracks
                        update_snapshot(cache_data, pl_name, tracks)
                        save_snapshot_cache(cache_data)
                    except Exception as snapshot_e:
                        # Non-critical: log but don't fail the sync
                        log_func(f" -> 快照更新提示: {snapshot_e}")
                else:
                    # For single tracks, just log that they were processed
                    log_func(f" -> 單曲已處理: {tracks[0]}")
                    if stats: stats.playlists_scanned += 1
            else:
                log_func(_('warn_no_tracks'))

        except Exception as e:
            log_func(_('scrape_error', e))
    
    if track_map_updated:
        try:
            with open(track_map_path, 'w', encoding='utf-8') as tf:
                json.dump(track_url_map, tf, ensure_ascii=False, indent=2)
            log_func(
                " -> Spotify track URL 快取已更新: "
                f"本次新增 {track_map_added} 首、更新 {track_map_changed} 首，快取總計 {len(track_url_map)} 首"
            )
        except Exception as map_write_e:
            log_func(f" -> Spotify track URL 快取寫入失敗: {map_write_e}")
