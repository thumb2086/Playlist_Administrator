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
        self.playlist_changes = {}  # {pl_name: {'added': [], 'removed': []}}
        self.stop_event = None # To be set by GUI

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
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                # Clean the line before adding
                cleaned_line = clean_line(line)
                songs.append(cleaned_line)
    return songs

def find_song_in_library(song_name, file_list):
    """
    Tries to find a file in the provided list that matches the song name.
    """
    def get_tokens(text):
        import re
        from zhconv import convert
        text = convert(text, 'zh-cn')
        text = re.sub(r"[\(\[【\)\]】]", " ", text)
        text = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)
        return [t.lower() for t in text.split() if t]

    query_tokens = get_tokens(song_name)
    if not query_tokens:
        return None
        
    for file_path in file_list:
        filename = os.path.basename(file_path)
        name_no_ext = os.path.splitext(filename)[0]
        file_tokens = get_tokens(name_no_ext)
        file_token_str = " ".join(file_tokens) 
        
        match_count = 0
        for q_token in query_tokens:
            if q_token in file_token_str: match_count += 1
        
        if match_count == len(query_tokens): return file_path
    
    return None

def update_library_logic(config, stats, log_func, progress_func=None, post_scrape_callback=None, post_download_callback=None):
    from core.spotify import scrape_via_spotify_embed
    from core.downloader import download_song
    
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
    log_func(_('indexed_songs', len(audio_files_cache)))

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

             existing_path = find_song_in_library(song_name, audio_files_cache)
             
             if existing_path:
                clean_name = sanitize_filename(song_name)
                ext = os.path.splitext(existing_path)[1]
                expected_filename = f"{clean_name}{ext}"
                expected_path = os.path.join(library_path, expected_filename)
                
                if os.path.basename(existing_path) != expected_filename:
                    if not os.path.exists(expected_path):
                        try:
                            os.rename(existing_path, expected_path)
                            log_func(_('rename_msg', os.path.basename(existing_path), expected_filename))
                            if existing_path in audio_files_cache: audio_files_cache.remove(existing_path)
                            audio_files_cache.append(expected_path)
                        except Exception as e:
                            log_func(_('rename_fail', e))
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
            
            res = download_song(song_name, library_path, audio_format, log_func, audio_files_cache, stats)
            if res and os.path.exists(res):
                stats.songs_downloaded.append(song_name)
                audio_files_cache.append(res)
                successful_downloads += 1
                
                if post_download_callback:
                    post_download_callback(audio_files_cache)

                if successful_downloads % 10 == 0:
                    log_func(_('dl_rest', successful_downloads))
                    time.sleep(15)
            
            current_dl += 1
            if progress_func: progress_func(current_dl, total_missing)
            
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
        # scan once
        search_pattern = os.path.join(library_path, "**", "*")
        all_files = glob.glob(search_pattern, recursive=True)
        audio_files_cache = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]

    for pl_file in playlists:
        songs = parse_playlist(pl_file)
        if not songs:
            report[pl_file] = (True, 0, 0)
            continue
            
        missing = 0
        for song_name in songs:
            if not find_song_in_library(song_name, audio_files_cache):
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
    total_size_bytes = sum(os.path.getsize(f) for f in audio_files)
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
    
    # Calculate savings
    # Average song size in library
    avg_size_bytes = (total_size_bytes / total_songs) if total_songs > 0 else 0
    duplicates_count = total_playlist_entries - unique_playlist_entries
    savings_mb = (duplicates_count * avg_size_bytes) / (1024 * 1024)
    
    return {
        'total_songs': total_songs,
        'total_size_mb': total_size_mb,
        'recent_5': recent_5,
        'total_playlist_entries': total_playlist_entries,
        'unique_playlist_entries': unique_playlist_entries,
        'duplicates_count': duplicates_count,
        'savings_mb': savings_mb
    }
