import os
import yt_dlp
import time
from utils.helpers import sanitize_filename
from core.library import find_song_in_library

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
        if "Extracting URL" in msg or "Downloading" in msg:
             # self.log_func(f"[ydl] {msg}") 
             pass
    def warning(self, msg):
        from utils.i18n import _
        self.check_stop()
        # Filter out noisy YouTube technical warnings
        if "formats have been skipped" in msg or "SABR streaming" in msg:
            return
        if "does not support cookies" in msg:
            return
        self.log_func(_('ytdlp_warn', msg))
    def error(self, msg):
        from utils.i18n import _
        self.check_stop()
        if "not a bot" in msg or "sign in to confirm" in msg:
             self.log_func(_('bot_detect'))
        elif "Task aborted by user" in msg:
             pass 
        else:
             self.log_func(_('dl_fail', msg))

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

    search_query = song_name.replace(',', ' ').replace('\xa0', ' ').strip()
    search_query = ' '.join(search_query.split()) # Normalize whitespace
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True, 
        'logger': YdlLogger(log_func, stats),
        'nocheckcertificate': True,
        'extractor_args': {
            'youtube': {
                'remote_components': 'ejs:github',
            }
        },
        'progress_hooks': [progress_hook],
    }
    
    # Check for cookies.txt
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cookies_path = os.path.join(script_dir, 'cookies.txt')
    if os.path.exists(cookies_path):
         from utils.i18n import _
         ydl_opts['cookiefile'] = cookies_path
         log_func(_('cookie_hint'))

    if audio_format == 'flac':
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'flac',
        }, {'key': 'FFmpegMetadata'}]
    else:
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }, {'key': 'FFmpegMetadata'}]

    try:
        from utils.i18n import _
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            log_func(_('searching', search_query))
            
            try:
                check_stop()
                info = ydl.extract_info(f"ytsearch1:{search_query}", download=True)
                if 'entries' in info and info['entries']:
                    info = info['entries'][0]
                elif 'entries' in info:
                    log_func(_('dl_fail', "No search results found."))
                    return None

            except TaskAbortedException:
                raise 
            except Exception as e:
                error_msg = str(e).lower()
                if "premieres in" in error_msg:
                    log_func(_('skip_premiere'))
                elif "416" in error_msg:
                    log_func(_('dl_fail', "HTTP 416: Corrupted partial file detected. Clearing and retrying next time."))
                    # Try to delete .part file if it exists
                    try:
                        part_file = ydl.prepare_filename(info) + ".part" if 'info' in locals() else None
                        if part_file and os.path.exists(part_file):
                            os.remove(part_file)
                    except: pass
                else:
                    log_func(_('dl_fail', e))
                return None

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
        log_func(_('dl_module_error', e))
        return None
