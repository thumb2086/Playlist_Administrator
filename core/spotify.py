import os
import json
import requests
from bs4 import BeautifulSoup
from zhconv import convert
from utils.helpers import sanitize_filename
from utils.config import ensure_dirs

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

def scrape_via_spotify_embed(config, stats, log_func):
    from utils.i18n import _
    target_urls = config.get('spotify_urls', [])
    if not target_urls:
        log_func(_('skip_no_urls'))
        return

    playlists_path = config['playlists_path']
    ensure_dirs(config)

    import datetime
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    last_updated = config.get('last_updated', {})

    for sp_url in target_urls:
        if stats and stats.stop_event and stats.stop_event.is_set():
            return
        
        # Skip if already updated today
        if last_updated.get(sp_url) == today:
            name = config.get('url_names', {}).get(sp_url, sp_url)
            log_func(_('skip_synced', name))
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
            
            # Special handling for single tracks
            if "track/" in sp_url:
                # For single tracks, extract the track info and add directly to download list
                next_data_tag = soup.find("script", {"id": "__NEXT_DATA__"})
                if next_data_tag:
                    try:
                        data = json.loads(next_data_tag.string)
                        entity = data.get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('entity', {})
                        if entity:
                            track_name = entity.get('name')
                            artists = entity.get('artists', [])
                            if track_name and artists:
                                artist_name = artists[0].get('name')
                                full_track_name = f"{artist_name} - {track_name}"
                                tracks.append(full_track_name)
                                pl_name = sanitize_filename(full_track_name)
                                log_func(f" -> 找到單曲: {full_track_name}")
                    except Exception as e:
                        log_func(_('json_error', e))
                
                # Fallback to HTML parsing if JSON fails
                if not tracks:
                    try:
                        title_tag = soup.find("h1")
                        artist_tag = soup.find("h2") or soup.find("a", {"data-testid": "entity-title"})
                        if title_tag and artist_tag:
                            title = title_tag.get_text(strip=True)
                            artist = artist_tag.get_text(strip=True)
                            full_track_name = f"{artist} - {title}"
                            tracks.append(full_track_name)
                            pl_name = sanitize_filename(full_track_name)
                            log_func(f" -> 找到單曲 (HTML): {full_track_name}")
                    except Exception as e:
                        log_func(f" -> 單曲解析錯誤: {e}")
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
                                import re
                                def clean_artist_name(name):
                                    # Remove "E" prefix (Explicit tag artifact)
                                    # e.g. "EYosebe" -> "Yosebe", "E王ADEN" -> "王ADEN"
                                    if not name: return name
                                    return re.sub(r'^E(?=[A-Z\u4e00-\u9fff\u3040-\u30ff])', '', name)

                                for item in track_list:
                                    track = item.get('track', item)
                                    name = track.get('name')
                                    artists = track.get('artists', [])
                                    if name and artists:
                                        artist_name = clean_artist_name(artists[0].get('name'))
                                        tracks.append(f"{artist_name} - {name}")
                    except Exception as e:
                        log_func(_('json_error', e))

            # HTML fallback for playlists/albums/artists only
            if not tracks and "track/" not in sp_url:
                 rows = soup.find_all("li", class_=lambda x: x and "TracklistRow_trackListRow" in x)
                 if rows:
                     log_func(_('html_fallback', len(rows)))
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

            if tracks:
                # Save name to config mapping
                if 'url_names' not in config: config['url_names'] = {}
                config['url_names'][sp_url] = pl_name
                
                # Record today as last updated
                if 'last_updated' not in config: config['last_updated'] = {}
                config['last_updated'][sp_url] = today
                
                from utils.config import save_config
                save_config(config)

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
                    
                    # Build index to resolve actual filenames (handles "E" prefix and diff extensions)
                    log_func(_('scanning_lib'))
                    import glob
                    search_pattern = os.path.join(library_path, "**", "*")
                    all_files = glob.glob(search_pattern, recursive=True)
                    audio_cache = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]
                    from core.library import build_library_index, find_song_in_library
                    lib_index = build_library_index(audio_cache)

                # Only write M3U files for playlists/albums/artists
                if "track/" not in sp_url:
                    with open(m3u_path, 'w', encoding='utf-8-sig', newline='') as f:
                        f.write("#EXTM3U\r\n")
                        for track in tracks:
                            clean_track = track.strip()
                            
                            # Find actual file in library
                            actual_path = find_song_in_library(clean_track, lib_index)
                            
                            # Ensure all paths are absolute and normalized first
                            abs_song_path = os.path.normpath(os.path.abspath(actual_path if actual_path else os.path.join(library_path, f"{clean_track}.mp3")))
                            abs_playlists_path = os.path.normpath(os.path.abspath(playlists_path))
                            
                            # Calculate relative path from Playlists folder to Music folder (e.g. ../Music/Song.mp3)
                            # rel_path will generate the necessary '..' prefix automatically.
                            rel_path = os.path.relpath(abs_song_path, start=abs_playlists_path)
                            
                            # Standardization: Forward slashes (/) are best for M3U8 and avoid separator issues
                            m3u_entry_path = rel_path.replace('\\', '/')
                            
                            # Write EXTINF and the relative path with CRLF
                            f.write(f"#EXTINF:-1,{clean_track}\r\n")
                            f.write(f"{m3u_entry_path}\r\n")
                    log_func(_('saved_tracks', len(tracks), os.path.basename(m3u_path)))
                    if stats: stats.playlists_scanned += 1
                else:
                    # For single tracks, just log that they were processed
                    log_func(f" -> 單曲已處理: {tracks[0]}")
                    if stats: stats.playlists_scanned += 1
            else:
                log_func(_('warn_no_tracks'))

        except Exception as e:
            log_func(_('scrape_error', e))
