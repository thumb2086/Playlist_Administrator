import os
import re
import yt_dlp
from utils.helpers import sanitize_filename
from core.library import find_song_in_library

def strip_ansi(text):
    """Removes ANSI escape sequences from strings"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

class YdlLogger:
    def __init__(self, log_func, stats=None):
        from utils.i18n import _
        self.log_func = log_func
        self.stats = stats
    def check_stop(self):
        if self.stats and self.stats.stop_event and self.stats.stop_event.is_set():
            raise TaskAbortedException("Task aborted by user")
    def debug(self, msg):
        self.check_stop()
    def warning(self, msg):
        from utils.i18n import _
        self.check_stop()
        if "formats have been skipped" in msg or "SABR streaming" in msg:
            return
        if "does not support cookies" in msg:
            return
        self.log_func(_('ytdlp_warn', strip_ansi(msg)))
    def error(self, msg):
        from utils.i18n import _
        self.check_stop()
        clean_msg = strip_ansi(msg)
        if "not a bot" in clean_msg or "sign in to confirm" in clean_msg:
             self.log_func(_('bot_detect'))
        elif "Task aborted by user" in clean_msg:
             pass 
        else:
             self.log_func(_('dl_fail', clean_msg))

class TaskAbortedException(Exception):
    pass

def download_song(song_name, library_path, audio_format, log_func, file_list, stats=None):
    """Downloads song in specified format (mp3 or flac)"""
    
    def check_stop():
        if stats and stats.stop_event and stats.stop_event.is_set():
            raise TaskAbortedException("Task aborted by user")

    def progress_hook(d):
        check_stop()
    
    # Check if we already have it
    existing = find_song_in_library(song_name, file_list)
    if existing:
        ext = os.path.splitext(existing)[1].lower().replace('.', '')
        if ext == audio_format:
            return existing

    clean_name = sanitize_filename(song_name)
    out_template = os.path.join(library_path, f"{clean_name}.%(ext)s")

    # Generate search candidates
    candidates = []
    # 1. Base clean query
    base_query = song_name.replace(',', ' ').replace('\xa0', ' ').strip()
    base_query = ' '.join(base_query.split())
    candidates.append(base_query)
    
    # 2. Replace dash with space
    if ' - ' in base_query:
        c2 = base_query.replace(' - ', ' ')
        if c2 not in candidates: candidates.append(c2)
        
    # 3. Title only (Last resort)
    if ' - ' in song_name: # Use original name to find split
        parts = song_name.rsplit(' - ', 1)
        if len(parts) > 1:
            c3 = parts[1].strip()
            # Clean it too
            c3 = c3.replace(',', ' ').replace('\xa0', ' ').strip()
            c3 = ' '.join(c3.split())
            if c3 and c3 not in candidates:
                candidates.append(c3)

    from utils.i18n import _
    
    for idx, current_query in enumerate(candidates):
        is_last_candidate = (idx == len(candidates) - 1)
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    if attempt == 0:
                        if idx == 0:
                            log_func(_('searching', current_query))
                        else:
                            log_func(f"⚠️ {_('dl_fail', 'No results')}. Retrying with: {current_query}...")
                    
                    check_stop()
                    # Use 'detailed' to catch 416 better? No, standard is fine.
                    try:
                        info = ydl.extract_info(f"ytsearch1:{current_query}", download=True)
                    except yt_dlp.utils.DownloadError as de:
                         # Re-raise if it's 416 or other critical errors to be caught below
                         raise de
                    except Exception as e:
                         # Fallback for generic
                         raise e

                    if 'entries' in info and info['entries']:
                        info = info['entries'][0]
                    elif 'entries' in info:
                        # Empty entries = No results
                        # Break inner retry loop to try next candidate
                        break 
                    else:
                        pass

                    filename = ydl.prepare_filename(info)
                    base, ext = os.path.splitext(filename)
                    final_path = base + "." + audio_format
                    
                    if os.path.exists(final_path):
                        log_func(f" -> {os.path.basename(final_path)}")
                        return final_path
                    
                    if os.path.exists(filename):
                        log_func(f" -> {os.path.basename(filename)}")
                        return filename
                    
                    return final_path

            except TaskAbortedException:
                return None
            except Exception as e:
                error_msg = strip_ansi(str(e)).lower()
                if "premieres in" in error_msg:
                    log_func(_('skip_premiere'))
                    return None
                elif "416" in error_msg:
                    log_func(_('dl_fail', "HTTP 416: Corrupted partial file detected. Clearing for retry."))
                    try:
                        part_pattern = os.path.join(library_path, f"{clean_name}.*")
                        import glob
                        for f in glob.glob(part_pattern):
                            if f.endswith('.part'):
                                os.remove(f)
                    except: pass
                    
                    if attempt < max_retries - 1:
                        log_func("Retrying download...")
                        continue # Retry same candidate
                    else:
                        # If 416 persists, maybe try next candidate? 
                        # Unlikely to help if it's the same video, but if next candidate finds diff video it might.
                        break 
                elif "sign in" in error_msg or "bot" in error_msg:
                    log_func(_('bot_detect'))
                    return None # Stop trying if bot detected
                else:
                    # If it's the last candidate and last retry, log error
                    if is_last_candidate and attempt == max_retries-1:
                        log_func(_('dl_fail', strip_ansi(str(e))))
                    # Otherwise silently fail to let next candidate try
                    break 
        
        # If we reached here, it means this candidate failed (break or exhausted retries)
        # Loop continues to next candidate
        
    return None
