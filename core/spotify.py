import os
import json
import requests
from bs4 import BeautifulSoup
from zhconv import convert
from utils.helpers import sanitize_filename
from utils.config import ensure_dirs

def get_playlist_name(sp_url):
    """Helper to fetch ONLY the name of a Spotify playlist from its embed page"""
    pl_id = None
    if "playlist/" in sp_url:
        try:
            pl_id = sp_url.split('?')[0].split('playlist/')[-1]
        except: return None
    else: pl_id = sp_url.strip()
    
    if not pl_id: return None
    
    embed_url = f"https://open.spotify.com/embed/playlist/{pl_id}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7'
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
            continue

        pl_id = None
        if "playlist/" in sp_url:
            try:
                # Remove query params
                clean_url = sp_url.split('?')[0]
                pl_id = clean_url.split('playlist/')[-1]
            except: pass
        else:
             pl_id = sp_url.strip()

        if not pl_id:
            log_func(_('skip_invalid', sp_url))
            continue

        embed_url = f"https://open.spotify.com/embed/playlist/{pl_id}"
        log_func(_('scanning_pl', pl_id))
        log_func(_('connecting_spotify'))
        
        try:
            if stats and hasattr(stats, 'pause_event'):
                 stats.pause_event.wait()

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7'
            }
            resp = requests.get(embed_url, headers=headers)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            tracks = []
            pl_name = f"Spotify_{pl_id}"

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
                                      (entity.get('tracks') and entity.get('tracks').get('items'))
                         
                         if track_list:
                             import re
                             def clean_artist_name(name):
                                 # Remove "E" prefix if followed by Uppercase (Explicit tag artifact)
                                 # e.g. "EYosebe" -> "Yosebe"
                                 if not name: return name
                                 return re.sub(r'^E(?=[A-Z])', '', name)

                             for item in track_list:
                                 track = item.get('track', item)
                                 name = track.get('name')
                                 artists = track.get('artists', [])
                                 if name and artists:
                                     artist_name = clean_artist_name(artists[0].get('name'))
                                     tracks.append(f"{artist_name} - {name}")
                 except Exception as e:
                     log_func(_('json_error', e))

            if not tracks:
                 rows = soup.find_all("li", class_=lambda x: x and "TracklistRow_trackListRow" in x)
                 if rows:
                     log_func(_('html_fallback', len(rows)))
                     import re
                     def clean_html_text(text):
                         # Aggressively clean "E" prefix which often appears in HTML scraping
                         if not text: return text
                         return re.sub(r'^E(?=[A-Z])', '', text)

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

                from core.library import parse_playlist # Local import to avoid circular dep if any
                m3u_path = os.path.join(playlists_path, f"{pl_name}.m3u")
                
                # Check if file exists to compare
                old_songs = set()
                if os.path.exists(m3u_path):
                    old_songs = set(parse_playlist(m3u_path))
                
                new_songs = set(tracks)
                added = list(new_songs - old_songs)
                removed = list(old_songs - new_songs)
                
                if stats:
                    stats.playlist_changes[pl_name] = {'added': added, 'removed': removed}

                with open(m3u_path, 'w', encoding='utf-8') as f:
                    for track in tracks:
                        f.write(track + "\n")
                log_func(_('saved_tracks', len(tracks), os.path.basename(m3u_path)))
                if stats: stats.playlists_scanned += 1
            else:
                log_func(_('warn_no_tracks'))

        except Exception as e:
            log_func(_('scrape_error', e))
