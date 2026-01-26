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

def download_lyrics(song_name, output_path, log_func):
    """Downloads synced lyrics (.lrc) for a song using direct Lrclib API with Traditional Chinese conversion"""
    try:
        import urllib.request
        import urllib.parse
        import json
        import time
        import random
        import re
        from zhconv import convert
        import ssl
        
        # Advanced cleaning: Remove common suffixes that confuse lyrics search
        clean_query = song_name
        suffixes = [
            r'\s*\(.*?\)', r'\s*\[.*?\]', r'\s*【.*?】', 
            r'\s*-?\s*Official\s*Video', r'\s*-?\s*Music\s*Video', 
            r'\s*-?\s*TV\s*Version', r'\s*-?\s*MV', r'\s*-?\s*Lyrics',
            r'\s*-?\s*HD', r'\s*-?\s*4K'
        ]
        for s in suffixes:
            clean_query = re.sub(s, '', clean_query, flags=re.IGNORECASE)
        clean_query = clean_query.strip()
        
        # Generate multiple search queries for better coverage
        search_queries = [clean_query]
        
        # REMOVED: Splitting by ' - ' and searching for parts caused incorrect matches 
        # (e.g. searching for title only can return a completely different song)
        
        alt_query = re.sub(r'[^\w\s]', ' ', clean_query)
        alt_query = re.sub(r'\s+', ' ', alt_query).strip()
        if alt_query != clean_query:
            search_queries.append(alt_query)
        
        # Direct API function
        def fetch_lrc(query, timeout=10):
            url = f"https://lrclib.net/api/search?q={urllib.parse.quote(query)}"
            req = urllib.request.Request(url, headers={'User-Agent': 'PlaylistAdministrator/2.0'})
            
            # Create a custom context to ignore SSL verification if needed (though API usually fine)
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
                data = json.loads(response.read().decode('utf-8'))
                if not isinstance(data, list):
                    return None
                    
                # Pick best match: prefer synced lyrics
                best_match = None
                for track in data:
                    if track.get('syncedLyrics'):
                        best_match = track['syncedLyrics']
                        break
                    if not best_match and track.get('plainLyrics'):
                        best_match = track['plainLyrics']
                        
                return best_match

        max_retries = 3
        
        for attempt in range(max_retries):
            try:
                # Progressive delay
                if attempt > 0:
                    backoff = (2 ** attempt) + random.uniform(1, 3)
                    log_func(f"  ⚠️ [Network] {song_name} - Retrying in {backoff:.1f}s...")
                    time.sleep(backoff)

                for idx, query in enumerate(search_queries):
                    # Reduce timeout slightly on retries to fail fast and try next
                    lrc_text = fetch_lrc(query, timeout=10 + attempt * 5)
                    
                    if lrc_text:
                        # CONVERT TO TRADITIONAL CHINESE
                        lrc_text = convert(lrc_text, 'zh-tw')
                        
                        with open(output_path, "w", encoding="utf-8") as f:
                            f.write(lrc_text)
                        return True
                    
                    # Small delay between query variations to be nice to API
                    time.sleep(0.5)
                
                # If we get here, no lyrics found for any query in this attempt
                # If it's the last attempt, we failed
                if attempt == max_retries - 1:
                    log_func(f"  ℹ️ [Lrclib Not Found] {song_name}")
                    return False
                    
            except Exception as e:
                error_msg = str(e).lower()
                is_net_error = any(k in error_msg for k in ['timeout', 'timed out', 'reset', 'aborted', 'eof', 'ssl'])
                
                if is_net_error:
                    if attempt == max_retries - 1:
                        log_func(f"  🔌 [Network Failed] {song_name}: {error_msg[:50]}")
                    continue
                else:
                    log_func(f"  ❌ [Lyrics Error] {song_name}: {str(e)[:50]}")
                    return False

    except Exception as e:
        log_func(f"  ❌ [Lyrics Critical] {song_name}: {str(e)[:100]}")
        return False
    return False

def download_song(song_name, library_path, audio_format, log_func, file_list, stats=None, speed_display_callback=None, progress_callback=None, current_dl=0):
    """Downloads song in specified format (mp3 or flac)"""
    
    # Progress tracking state
    import time
    last_progress_time = [0]  # Use list to allow modification in nested function
    last_progress_pct = [0]
    last_speed_time = [0]  # Track last speed calculation
    last_speed_value = [0]   # Track last speed for smoothing

    def check_stop():
        if stats and getattr(stats, 'stop_event', None) and stats.stop_event.is_set():
            raise TaskAbortedException("Task aborted by user")

    def progress_hook(d):
        check_stop()
        # --- DIAGNOSTIC LOG ---
        if not isinstance(d, dict):
            log_func(f"[DIAGNOSTIC] progress_hook received non-dict: type={type(d)}, content={d}")
            return
        # --- END DIAGNOSTIC ---
        
        if d['status'] == 'downloading':
            current_time = time.time()
            
            # Get progress data
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)
            
            # Calculate current percentage
            current_pct = (downloaded / total * 100) if total > 0 else 0
            
            # Update speed tracking for smoothing
            current_time = time.time()
            if speed > 0:
                last_speed_time[0] = current_time
                last_speed_value[0] = speed
            
            # Only log if: 2+ seconds passed OR 10%+ progress made
            time_elapsed = current_time - last_progress_time[0]
            pct_change = abs(current_pct - last_progress_pct[0])
            
            if time_elapsed >= 2 or pct_change >= 10:
                # Format speed with better handling
                if speed and speed > 0:
                    if speed >= 1024 * 1024:
                        speed_str = f"{speed / (1024 * 1024):.2f} MB/s"
                    elif speed >= 1024:
                        speed_str = f"{speed / 1024:.1f} KB/s"
                    else:
                        speed_str = f"{speed:.0f} B/s"
                else:
                    speed_str = "等待中..."
                
                # Update speed display if callback provided
                if speed_display_callback:
                    speed_display_callback(speed_str)
                
                # Format progress
                if total > 0:
                    pct = (downloaded / total) * 100
                    mb_downloaded = downloaded / (1024 * 1024)
                    mb_total = total / (1024 * 1024)
                    
                    # Enhanced ETA calculation
                    eta_str = ""
                    eta_seconds = 0
                    # Ensure eta is numeric before comparison
                    try:
                        eta_numeric = float(eta) if eta else 0
                    except (ValueError, TypeError):
                        eta_numeric = 0
                    
                    if eta_numeric > 0:
                        # Use yt-dlp ETA if available
                        eta_min = eta_numeric // 60
                        eta_sec = eta_numeric % 60
                        eta_str = f"{int(eta_min)}:{int(eta_sec):02d}"
                        eta_seconds = eta_numeric
                    elif speed > 0 and total > downloaded:
                        # Calculate ETA based on current speed
                        remaining_bytes = total - downloaded
                        eta_seconds = remaining_bytes / speed
                        if eta_seconds > 0:
                            eta_min = int(eta_seconds // 60)
                            eta_sec = int(eta_seconds % 60)
                            eta_str = f"{eta_min}:{eta_sec:02d}"
                        else:
                            eta_str = "即將完成"
                    else:
                        eta_str = "計算中..."
                    
                    log_func(f"  ⬇️ {pct:.1f}% | {mb_downloaded:.1f}/{mb_total:.1f} MB | {speed_str} | ETA {eta_str}")
                else:
                    mb_downloaded = downloaded / (1024 * 1024)
                    log_func(f"  ⬇️ {mb_downloaded:.1f} MB | {speed_str}")
                
                # Update tracking state
                last_progress_time[0] = current_time
                last_progress_pct[0] = current_pct
                
                # Call progress callback if provided
                if progress_callback:
                    progress_callback(current_dl, total, eta_seconds if eta_seconds > 0 else None)
                
        elif d['status'] == 'finished':
            log_func("  ✅ Download complete, converting...")
    
    # Check if we already have it
    existing = find_song_in_library(song_name, file_list)
    if existing:
        ext = os.path.splitext(existing)[1].lower().replace('.', '')
        if ext == audio_format:
            return existing

    clean_name = sanitize_filename(song_name)
    out_template = os.path.join(library_path, f"{clean_name}.%(ext)s")

    # Configure yt-dlp options
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True,
        'extract_audio': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': audio_format,
            'preferredquality': '0' if audio_format == 'flac' else '320',
        }],
        'logger': YdlLogger(log_func, stats),
        'progress_hooks': [progress_hook],
        'keepvideo': False,
        'windowsfilenames': True,
        'restrictfilenames': False,
    }
    
    # Add cookies if available
    cookies_path = 'cookies.txt'
    if os.path.exists(cookies_path):
        ydl_opts['cookiefile'] = cookies_path

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
    
    # 3. Artist + Title (without dash) for better matching
    if ' - ' in song_name:
        parts = song_name.split(' - ', 1)
        if len(parts) == 2:
            artist = parts[0].strip().replace(',', ' ').replace('\xa0', ' ')
            title = parts[1].strip().replace(',', ' ').replace('\xa0', ' ')
            # Artist Title (no dash)
            c4 = f"{artist} {title}"
            c4 = ' '.join(c4.split())
            if c4 and c4 not in candidates:
                candidates.append(c4)
        
    # 4. Title only (Last resort)
    if ' - ' in song_name: # Use original name to find split
        parts = song_name.rsplit(' - ', 1)
        if len(parts) > 1:
            c3 = parts[1].strip()
            # Clean it too
            c3 = c3.replace(',', ' ').replace('\xa0', ' ').strip()
            c3 = ' '.join(c3.split())
            if c3 and c3 not in candidates:
                candidates.append(c3)
    
    # 5. Add common K-pop search terms
    title_lower = base_query.lower()
    if any(keyword in title_lower for keyword in ['twice', 'blackpink', 'bts', 'seventeen', 'ive', 'nct', 'stray', 'enhypen', 'ateez', 'lisa', 'newjeans', 'tomorrow x together']):
        # Try with "official" or "mv" for K-pop songs
        c5 = base_query + " official mv"
        if c5 not in candidates:
            candidates.append(c5)
        c6 = base_query + " music video"
        if c6 not in candidates:
            candidates.append(c6)
    
    # 6. Handle songs with parentheses - try without parentheses content
    if '(' in base_query and ')' in base_query:
        # Remove content in parentheses for cleaner search
        base_no_parens = re.sub(r'\s*\([^)]*\)', '', base_query).strip()
        if base_no_parens and base_no_parens not in candidates:
            candidates.append(base_no_parens)
        
        # Also try with just the main part + "official mv"
        if base_no_parens:
            c7 = base_no_parens + " official mv"
            if c7 not in candidates:
                candidates.append(c7)
    
    # 7. For songs with special characters, try simplified version
    simplified = re.sub(r'[^\w\s\-]', ' ', base_query)
    simplified = ' '.join(simplified.split())
    if simplified and simplified != base_query and simplified not in candidates:
        candidates.append(simplified)
    
    # 8. Try shortened versions for very long titles
    if len(base_query) > 50:
        # Try just first few words
        words = base_query.split()
        if len(words) > 4:
            shortened = ' '.join(words[:4])
            if shortened not in candidates:
                candidates.append(shortened)
    
    # 9. Try keyword-based search for complex titles
    if 'BOUNCY' in base_query:
        candidates.append('ATEEZ BOUNCY')
        candidates.append('ATEEZ BOUNCY official mv')
    if 'HOT CHILLI PEPPERS' in base_query:
        candidates.append('ATEEZ HOT CHILLI PEPPERS')
    
    # 10. For Japanese versions, try without "Japanese Ver."
    if 'Japanese Ver.' in base_query:
        base_no_jp = base_query.replace('Japanese Ver.', '').strip()
        if base_no_jp not in candidates:
            candidates.append(base_no_jp)
            candidates.append(base_no_jp + ' japanese version')
            candidates.append(base_no_jp + ' jp ver')

    from utils.i18n import _
    
    all_candidates_failed = True  # Track if all candidates fail
    
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
                            # Only show "No results" warning if this is the last attempt of all candidates
                            if is_last_candidate and attempt == max_retries - 1:
                                log_func(f"⚠️ {_('dl_fail', 'No results')}. Trying: {current_query}...")
                            else:
                                log_func(_('searching', current_query))
                    
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
                        # Download lyrics
                        lrc_path = os.path.splitext(final_path)[0] + ".lrc"
                        if not os.path.exists(lrc_path):
                            download_lyrics(song_name, lrc_path, log_func)
                        return final_path
                    
                    if os.path.exists(filename):
                        log_func(f" -> {os.path.basename(filename)}")
                        # Download lyrics
                        lrc_path = os.path.splitext(filename)[0] + ".lrc"
                        if not os.path.exists(lrc_path):
                            download_lyrics(song_name, lrc_path, log_func)
                        all_candidates_failed = False  # Mark as successful
                        return filename
                    
                    # Download lyrics for final_path even if it doesn't exist yet (it will be created by PP)
                    lrc_path = os.path.splitext(final_path)[0] + ".lrc"
                    if not os.path.exists(lrc_path):
                        download_lyrics(song_name, lrc_path, log_func)
                    
                    all_candidates_failed = False  # Mark as successful
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
                elif "403" in error_msg or "forbidden" in error_msg:
                    log_func(_('dl_fail', "HTTP 403: Access forbidden. Trying next search..."))
                    # Add a small delay before trying next candidate
                    import time
                    time.sleep(1)
                    # Break to try next candidate immediately
                    break
                elif "sign in" in error_msg or "bot" in error_msg:
                    log_func(_('bot_detect'))
                    return None # Stop trying if bot detected
                else:
                    # If it's the last candidate, log error before giving up
                    if is_last_candidate:
                        log_func(_('dl_fail', strip_ansi(str(e))))
                    # Otherwise silently fail to let next candidate try
                    break 
        
        # If we reached here, it means this candidate failed (break or exhausted retries)
        # Loop continues to next candidate
        
    # If all candidates failed, show final warning
    if all_candidates_failed:
        log_func(f"❌ {_('dl_fail', 'All search attempts failed')}")
        
    return None
