import os
import glob
import time
import shutil
import random
from utils.helpers import sanitize_filename, normalize_name
from utils.config import ensure_dirs

class UpdateStats:
    def __init__(self):
        self.playlists_scanned = 0
        self.songs_downloaded = []
        self.playlist_changes = {}
        self.playlist_updates = {}
        self.stop_event = None

def parse_playlist(file_path):
    songs = []
    if os.path.exists(file_path):
        import re
        def clean_line(text):
            # Aggressively clean "E" prefix if followed by Uppercase (Explicit tag artifact)
            # e.g. "EYosebe" -> "Yosebe"
            # Since m3u lines are "Artist - Title", we only target the start
            return re.sub(r'^E(?=[A-Z])', '', text)

        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            # Check if this is a proper M3U file with header
            is_m3u = False
            if lines and lines[0].strip() == '#EXTM3U':
                is_m3u = True
            
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                
                if not line:
                    i += 1
                    continue
                    
                # Skip M3U headers and metadata lines
                if line.startswith('#'):
                    if is_m3u and line.startswith('#EXTINF'):
                        # This is an EXTINF line, the next line should be the actual path/name
                        i += 1
                        if i < len(lines):
                            next_line = lines[i].strip()
                            if next_line and not next_line.startswith('#'):
                                # Clean the line before adding
                                cleaned_line = clean_line(next_line)
                                songs.append(cleaned_line)
                    # Skip all other comment/header lines
                    i += 1
                    continue
                    
                # For non-M3U files or files without proper format, treat as simple song list
                if not is_m3u:
                    # Clean the line before adding
                    cleaned_line = clean_line(line)
                    songs.append(cleaned_line)
                
                i += 1
    return songs

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

def update_library_logic(config, stats, log_func, progress_func=None, post_scrape_callback=None, post_download_callback=None, speed_display_callback=None):
    from core.spotify import scrape_via_spotify_embed
    from core.downloader import download_song
    import time
    
    # 1. Scrape First
    scrape_via_spotify_embed(config, stats, log_func)
    
    if post_scrape_callback:
        post_scrape_callback()

    # 2. Process Playlists
    playlists_path = config['playlists_path']
    library_path = config['library_path']
    audio_format = config.get('audio_format', 'mp3')
    
    files = glob.glob(os.path.join(playlists_path, "*.m3u")) + \
            glob.glob(os.path.join(playlists_path, "*.txt"))
            
    from utils.i18n import _
            
    if not files:
        log_func(_('no_pl_files'))
        return

    log_func(_('scanning_lib'))
    search_pattern = os.path.join(library_path, "**", "*")
    all_files = glob.glob(search_pattern, recursive=True)
    audio_files_cache = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]
    
    # Build the library index for fast lookups
    log_func(_('building_index'))
    library_index = build_library_index(audio_files_cache)
    log_func(_('indexed_songs', len(audio_files_cache)))  # Show total files, not unique songs

    # PHASE 1: Identify Missing Songs & Renaming
    log_func(_('analyzing_missing', len(files)))
    songs_to_download = [] # List of {'name': s, 'playlist': pl}
    
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
             
             if existing_path:
                 # Renaming logic can be simplified or removed if filenames are consistent
                 pass # Assuming filenames are now managed correctly upon download
             else:
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
        
        for item in songs_to_download:
            song_name = item['name']
            pl_name = item['playlist']
            remaining = total_missing - (current_dl + 1)
            
            if stats and stats.stop_event and stats.stop_event.is_set():
                 log_func(_('task_stopped'))
                 return

            if hasattr(stats, 'pause_event') and stats.pause_event:
                 stats.pause_event.wait()
                 
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
            
            res = download_song(song_name, library_path, audio_format, log_func, audio_files_cache, stats, None, song_progress_callback, current_dl)
            if res and os.path.exists(res):
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
            
            if current_dl < total_missing:  
                delay = random.uniform(3, 8)
                time.sleep(delay)
    else:
        log_func(_('lib_up_to_date'))
        if progress_func: progress_func(100, 100) 

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
        for song_name in songs:
            src = find_song_in_library(song_name, audio_files_cache)
            if src and os.path.exists(src):
                try:
                    shutil.copy2(src, dest_folder)
                    count += 1
                except Exception as e:
                    log_func(_('copy_error', e))
        
        log_func(_('exported_count', count, len(songs)))
        
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
    audio_files_sorted = sorted(audio_files, key=lambda x: os.path.getmtime(x), reverse=True)
    recent_5 = []
    for f in audio_files_sorted[:5]:
        mtime = os.path.getmtime(f)
        import datetime
        date_str = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')
        recent_5.append((os.path.basename(f), date_str))
        
    # 2. Duplicate/Savings Stats
    pl_files = glob.glob(os.path.join(playlists_path, "*.m3u")) + \
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
