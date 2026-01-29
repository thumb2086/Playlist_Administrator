import os
import glob
import time
import shutil
import random
import requests
from bs4 import BeautifulSoup
from utils.helpers import sanitize_filename, normalize_name
from utils.config import ensure_dirs
from core.spotify import get_spotify_name

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
            subprocess.run(["powershell", "-Command", cmd], capture_output=True, check=False)
        except: pass

def get_normalized_tokens(text):
    import re
    from zhconv import convert

    # 1. Convert to lowercase
    text = str(text).lower()
    
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
    except:
        # If conversion fails, keep original text
        pass

    # 2.5 Remove "E" prefix artifact (common in Spotify scrapes)
    # e.g. "EYosebe", "E王ADEN"
    text = re.sub(r'^e(?=[a-z\u4e00-\u9fff\u3040-\u30ff])', '', text)

    # 3. Standardize artist separators and common terms to spaces
    # Handles 'feat.', 'ft.', 'vs', 'vs.', '&', ',', ' x '
    text = re.sub(r'\s*(feat|ft|vs)\.?\s*|\s*[&,x]\s*', ' ', text)

    # 4. Remove content in brackets (e.g., (Live), [Remix], 【MV】)
    # Also removes the brackets themselves
    text = re.sub(r"[\(\[【][^\)\]】]*[\)\]】]", " ", text)

    # 5. Replace all non-alphanumeric characters (excluding Chinese and Japanese) with spaces
    # This will also handle underscores and other symbols
    # Include Japanese Hiragana (\u3040-\u309f) and Katakana (\u30a0-\u30ff)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+", " ", text)

    # 6. Split into tokens, remove empty strings, and sort
    return sorted([t for t in text.split() if t])

def build_library_index(audio_files):
    index = {}
    for file_path in audio_files:
        filename = os.path.basename(file_path)
        name_no_ext = os.path.splitext(filename)[0]
        # The key is a tuple of sorted tokens, making it order-independent
        tokens_tuple = tuple(get_normalized_tokens(name_no_ext))
        if tokens_tuple:
            index[tokens_tuple] = file_path
    return index

def find_song_in_library(song_name, library_source):
    """ Tries to find a song using either a pre-built library index (dict) or a file list (list). """
    query_tokens = tuple(get_normalized_tokens(song_name))
    if not query_tokens:
        return None
    
    # Check if library_source is a dictionary (index) or list (file list)
    if isinstance(library_source, dict):
        # Fast O(1) lookup using the index
        return library_source.get(query_tokens)
    elif isinstance(library_source, list):
        # Fallback to O(n) search for backward compatibility with downloader.py
        for file_path in library_source:
            filename = os.path.basename(file_path)
            name_no_ext = os.path.splitext(filename)[0]
            file_tokens = tuple(get_normalized_tokens(name_no_ext))
            if file_tokens == query_tokens:
                return file_path
        return None
    else:
        # Unsupported type
        return None

def rename_explicit_files(library_path, log_func):
    """ Renames files starting with 'E' prefix and standardizes all filenames to be safe for players """
    import re
    from utils.helpers import sanitize_filename
    search_pattern = os.path.join(library_path, "**", "*")
    all_files = glob.glob(search_pattern, recursive=True)
    count = 0
    from utils.i18n import _
    
    for f in all_files:
        if not os.path.isfile(f): continue
        dir_name = os.path.dirname(f)
        old_filename = os.path.basename(f)
        
        # 1. Strip 'E' prefix artifact
        clean_name = old_filename
        if re.match(r'^E[A-Z\u4e00-\u9fff\u3040-\u30ff]', old_filename):
            clean_name = old_filename[1:]
            
        # 2. Aggressively sanitize the rest (fix \xa0, etc)
        name_only, ext = os.path.splitext(clean_name)
        safe_name = sanitize_filename(name_only) + ext
        
        if safe_name != old_filename:
            new_path = os.path.join(dir_name, safe_name)
            if not os.path.exists(new_path):
                try:
                    os.rename(f, new_path)
                    count += 1
                except: pass
            else:
                # If safe version exists, delete the artifact one
                try:
                    os.remove(f)
                    count += 1
                except: pass
    if count > 0:
        log_func(_('organized_files', count))
    return count

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
    for pl_file in all_playlist_files:
        base = os.path.basename(pl_file)
        # Skip the unsorted/single tracks playlists themselves
        if any(x in base for x in ["_未分類", "_Unsorted", "Single Tracks", "單曲"]): continue
        songs_in_playlists.update(parse_playlist(pl_file))
    
    # Build tokens for comparison
    playlist_tokens = set()
    for s in songs_in_playlists:
        t = tuple(get_normalized_tokens(s))
        if t: playlist_tokens.add(t)
        
    # 2. Identify orphan files in Music root and subdirectories
    search_pattern = os.path.join(library_path, "**", "*")
    all_library_files = [os.path.normpath(f) for f in glob.glob(search_pattern, recursive=True) if os.path.isfile(f)]
    
    orphans = []
    for f in all_library_files:
        # ROBUST CHECK: skip if file is actually inside the _Unsorted directory
        if f.lower().startswith(unsorted_dir_norm): continue
        if os.path.basename(f).startswith('.'): continue
        if not f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm')): continue
        
        filename_no_ext = os.path.splitext(os.path.basename(f))[0]
        file_tokens = tuple(get_normalized_tokens(filename_no_ext))
        
        if file_tokens not in playlist_tokens:
            orphans.append(f)
            
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
                    except:
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

def update_library_logic(config, stats, log_func, progress_func=None, post_scrape_callback=None, post_download_callback=None, speed_display_callback=None):
    from core.spotify import scrape_via_spotify_embed
    from core.downloader import download_song
    import time
            
    # 0. Initialize
    library_path = config['library_path']
    playlists_path = config['playlists_path']
    audio_format = config.get('audio_format', 'mp3')
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
    # 1.2 Clean up 'E' prefixes and fix sanitization mismatch
    rename_explicit_files(library_path, log_func)

    # 2. Scrape Spotify (Update local tracklists from URL)
    scrape_via_spotify_embed(config, stats, log_func)
    if post_scrape_callback:
        post_scrape_callback()

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
    
    songs_to_download = [] # List of {'name': s, 'playlist': pl}
    songs_missing_lyrics = [] # List of (song_name, existing_path)
    
    # Pre-scan existing files for missing lyrics
    for audio_path in audio_files_cache:
        lrc_path = os.path.splitext(audio_path)[0] + ".lrc"
        if not os.path.exists(lrc_path):
            # Extract song name from filename
            song_name = os.path.splitext(os.path.basename(audio_path))[0]
            songs_missing_lyrics.append((song_name, audio_path))

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

             existing_path = find_song_in_library(song_name, library_index)
             if not existing_path:
                 # Check if already in list to avoid duplicates across diff playlists
                 if not any(d['name'] == song_name for d in songs_to_download):
                     songs_to_download.append({'name': song_name, 'playlist': pl_name})

    total_missing = len(songs_to_download)
    log_func(_('stats_complete', total_missing))
    
    if progress_func: progress_func(0, total_missing)
    
    # PHASE 2: Download
    if total_missing > 0:
        log_func(_('dl_start'))
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
                elif current > 0 and total_downloaded_time > 0:
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
                    overall_eta = "即將完成" if current > 0 else None
                
                progress_func(current, total, overall_eta)
            else:
                progress_func(0, total, None)
        
        # Initialize song status tracking for downloads
        download_status = {}
        for i, item in enumerate(songs_to_download):
            song_name = item['name']
            download_status[i] = {
                'name': song_name,
                'status': '⏳ 等待中',
                'order': i + 1
            }
            # Initialize song status in UI
            if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
                stats.app.update_song_status(i, '⏳ 等待中', song_name)

        for i, item in enumerate(songs_to_download):
            song_name = item['name']
            pl_name = item['playlist']
            remaining = total_missing - (current_dl + 1)
            
            if stats and stats.stop_event and stats.stop_event.is_set():
                 log_func(_('task_stopped'))
                 return

            if hasattr(stats, 'pause_event') and stats.pause_event:
                 stats.pause_event.wait()
            
            # Update status to downloading
            if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
                stats.app.update_song_status(i, '🔽 下載中', song_name)
                 
            # Check if log_func supports immediate parameter
            if hasattr(log_func, '__code__') and 'immediate' in log_func.__code__.co_varnames:
                log_func(_('dl_progress', current_dl+1, total_missing, remaining, pl_name, song_name), immediate=True)
            else:
                log_func(_('dl_progress', current_dl+1, total_missing, remaining, pl_name, song_name))
            
            # Create a progress callback for this song
            song_start_time = time.time()
            def song_progress_callback(current, total, eta=None):
                # Update overall progress with current song progress
                # Use current_dl + (current/total) to show progress within current song
                if total > 0:
                    song_progress = current / total
                    overall_progress = current_dl + song_progress
                else:
                    overall_progress = current_dl
                
                # Calculate overall ETA for the entire task
                if total_downloaded_time > 0 and current_dl > 0:
                    avg_time_per_song = total_downloaded_time / current_dl
                    remaining_songs = total_missing - current_dl
                    eta_seconds = remaining_songs * avg_time_per_song
                    # Ensure eta_seconds is numeric
                    try:
                        eta_seconds = float(eta_seconds)
                    except (ValueError, TypeError):
                        eta_seconds = None
                    progress_with_overall_eta(overall_progress, total_missing, eta_seconds)
                else:
                    # For first song, try to use current song's ETA as rough estimate
                    if eta and isinstance(eta, (int, float)) and eta > 0:
                        # Rough estimate: current song ETA * remaining songs
                        remaining_songs = total_missing - current_dl
                        overall_eta = eta * remaining_songs
                        progress_with_overall_eta(overall_progress, total_missing, overall_eta)
                    elif total > 0 and current > 0:
                        # If we have current song progress, estimate based on current song's progress rate
                        song_progress_ratio = current / total
                        if song_progress_ratio > 0:
                            # Estimate total time for current song based on elapsed time and progress
                            elapsed_time = time.time() - song_start_time
                            estimated_total_song_time = elapsed_time / song_progress_ratio
                            remaining_song_time = estimated_total_song_time - elapsed_time
                            # Rough estimate: remaining time for current song + time for remaining songs
                            remaining_songs = total_missing - current_dl - 1  # Exclude current song
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
            
            res = download_song(song_name, library_path, audio_format, log_func, audio_files_cache, stats, None, song_progress_callback, current_dl, use_dab_lossless, use_dab_metadata, dab_credentials, config)
            if res and os.path.exists(res):
                # Update status to success
                if hasattr(stats, 'app') and hasattr(stats.app, 'update_song_status'):
                    stats.app.update_song_status(i, '✅ 完成', song_name)
                
                # Track time spent on this song
                song_end_time = time.time()
                song_duration = song_end_time - song_start_time
                total_downloaded_time += song_duration
                
                stats.songs_downloaded.append(song_name)
                # Track which playlist this song was updated for
                if pl_name not in stats.playlist_updates:
                    stats.playlist_updates[pl_name] = []
                stats.playlist_updates[pl_name].append(song_name)
                audio_files_cache.append(res)
                successful_downloads += 1
                
                if post_download_callback:
                    post_download_callback(audio_files_cache)

                if successful_downloads % 10 == 0:
                    log_func(_('dl_rest', successful_downloads))
                    time.sleep(15)
            else:
                # Update status to failed
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
        
    # PHASE 3: Retroactive Lyrics Download (Only run if enabled and there are existing songs missing lyrics)
    if songs_missing_lyrics and config.get('enable_retroactive_lyrics', True):
        from core.downloader import download_lyrics
        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import json
        import hashlib
        
        log_func(_('retroactive_lyrics', len(songs_missing_lyrics)))
        total_lyrics_to_fetch = len(songs_missing_lyrics)
        lyrics_fetched_count = 0
        consecutive_failures = 0
        max_consecutive_failures = 10  # Skip to next phase after too many failures
        
        # Load failed lyrics cache
        failed_cache_file = os.path.join(config.get('base_path', ''), 'data', 'failed_lyrics.json')
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
                
                # Show simple progress every 50 songs
                if completed_count % 50 == 0 or completed_count == total_lyrics_to_fetch:
                    log_func(f"� 歌詞下載進度: {completed_count}/{total_lyrics_to_fetch} (成功: {lyrics_fetched_count})")
        
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
    elif songs_missing_lyrics and not config.get('enable_retroactive_lyrics', True):
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
                    percentage = (current / total) * 100 if total > 0 else 0
                    progress_func(percentage, 100)
            
            enriched_count = enricher.enrich_library_metadata(library_path, log_func, metadata_progress)
            enricher.cleanup()
            
            if enriched_count > 0:
                log_func(f'🎉 Enriched metadata for {enriched_count} files')
            else:
                log_func('ℹ️ No files needed metadata enrichment')
                
        except Exception as e:
            log_func(f'⚠️ Metadata enrichment failed: {str(e)}')
    
    log_func(_('update_complete'))

def get_playlist_completeness_report(playlists, library_path, audio_files_cache=None):
    """Returns a dict {pl_file: (is_complete, missing_count, total_count)}"""
    report = {}
    
    if audio_files_cache is None:
        search_pattern = os.path.join(library_path, "**", "*")
        all_files = glob.glob(search_pattern, recursive=True)
        audio_files_cache = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]

    # Build index for this report
    library_index = build_library_index(audio_files_cache)

    for pl_file in playlists:
        songs = parse_playlist(pl_file)
        if not songs:
            report[pl_file] = (True, 0, 0)
            continue
            
        missing = 0
        for song_name in songs:
            if not find_song_in_library(song_name, library_index):
                missing += 1
        
        report[pl_file] = (missing == 0, missing, len(songs))
    
    return report

def export_usb_logic(config, selected_playlists, log_func):
    from utils.i18n import _
    log_func(_('export_start'))
    export_path = config['export_path']
    library_path = config['library_path']
    
    # Define sub-export paths for different qualities
    export_path_flac = os.path.join(export_path, "FLAC_Quality")
    export_path_mp3 = os.path.join(export_path, "MP3_Quality")
    
    # Cleanup main export directory
    if os.path.exists(export_path):
        shutil.rmtree(export_path)
        time.sleep(0.5)
    os.makedirs(export_path_flac, exist_ok=True)
    os.makedirs(export_path_mp3, exist_ok=True)
    
    if not selected_playlists:
        log_func(_('no_pl_selected'))
        return

    search_pattern = os.path.join(library_path, "**", "*")
    all_files = glob.glob(search_pattern, recursive=True)
    
    # Group audio files by quality
    audio_files_flac = [f for f in all_files if f.lower().endswith('.flac')]
    audio_files_mp3 = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.wav', '.webm'))]

    for pl_file in selected_playlists:
        if not os.path.exists(pl_file): continue
        
        pl_name = os.path.splitext(os.path.basename(pl_file))[0]
        songs = parse_playlist(pl_file)
        log_func(_('exporting_pl', pl_name))
        
        # Create playlist subfolders in both quality directories
        dest_flac = os.path.join(export_path_flac, pl_name)
        dest_mp3 = os.path.join(export_path_mp3, pl_name)
        
        count_flac = 0
        count_mp3 = 0
        
        for song_name in songs:
            # 1. Try to find FLAC version first
            src_flac = find_song_in_library(song_name, audio_files_flac)
            if src_flac and os.path.exists(src_flac):
                os.makedirs(dest_flac, exist_ok=True)
                shutil.copy2(src_flac, dest_flac)
                count_flac += 1
            
            # 2. Try to find MP3/Standard version
            src_mp3 = find_song_in_library(song_name, audio_files_mp3)
            if src_mp3 and os.path.exists(src_mp3):
                os.makedirs(dest_mp3, exist_ok=True)
                shutil.copy2(src_mp3, dest_mp3)
                count_mp3 += 1
        
        log_func(f" -> {pl_name}: 匯出 {count_flac} 首 FLAC, {count_mp3} 首 MP3")
        
    log_func(_('export_done_open'))
    abs_export_path = os.path.abspath(export_path)
    if os.path.exists(abs_export_path):
        # On Linux, os.startfile doesn't exist. Use xdg-open or similar
        try:
            if os.name == 'nt':
                os.startfile(abs_export_path)
            else:
                import subprocess
                subprocess.run(['xdg-open', abs_export_path], check=False)
        except:
            log_func(f"請手動開啟資料夾: {abs_export_path}")
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
    
    total_songs = len(audio_files)
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
        
    # 2. Duplicate/Savings Stats
    pl_files = glob.glob(os.path.join(playlists_path, "*.m3u8")) + \
               glob.glob(os.path.join(playlists_path, "*.m3u")) + \
               glob.glob(os.path.join(playlists_path, "*.txt"))
    
    all_pl_songs = []
    unique_pl_songs = set()
    for pl_file in pl_files:
        songs = parse_playlist(pl_file)
        all_pl_songs.extend(songs)
        for s in songs: unique_pl_songs.add(s)
    
    total_playlist_entries = len(all_pl_songs)
    unique_playlist_entries = len(unique_pl_songs)
    
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
    # add (occurrences - 1) * file_size
    actual_savings_bytes = 0
    for tokens_tuple, occurrences in song_occurrences.items():
        if occurrences > 1 and tokens_tuple in song_to_files:
            # Find the first existing file for this song
            for file_path in song_to_files[tokens_tuple]:
                if os.path.exists(file_path):
                    try:
                        file_size = os.path.getsize(file_path)
                        # Add file size for each duplicate occurrence (occurrences - 1)
                        actual_savings_bytes += (occurrences - 1) * file_size
                        break  # Only use the first file found
                    except (OSError, IOError):
                        continue
    
    savings_mb = actual_savings_bytes / (1024 * 1024)
    
    return {
        'total_songs': total_songs,
        'total_size_mb': total_size_mb,
        'recent_5': recent_5,
        'total_playlist_entries': total_playlist_entries,
        'unique_playlist_entries': unique_playlist_entries,
        'duplicates_count': duplicates_count,
        'savings_mb': savings_mb
    }
