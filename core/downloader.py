import os
import re
import logging
import subprocess
from pathlib import Path
import yt_dlp
from utils.helpers import sanitize_filename, download_image
from core.library import find_song_in_library
from core.dab_downloader import create_dab_downloader
from core.metadata_enricher import create_metadata_enricher # Added import
from mutagen.flac import FLAC, Picture
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TRCK, TCON, APIC
from mutagen.mp4 import MP4, MP4Cover
from mutagen.easyid3 import EasyID3

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
        if "PO Token" in msg or "po_token" in msg:
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

def _resolve_spotdl_executable(raw_path):
    """Resolve spotDL executable path for current platform."""
    candidate = Path(raw_path)
    if os.name == 'nt':
        if candidate.suffix.lower() != '.exe':
            candidate = candidate.with_suffix('.exe')
    return candidate

def _extract_spotdl_output_path(stdout_text):
    """
    Extract downloaded file path from spotDL stdout.
    Supports lines like:
      - Downloaded to /path/to/file.mp3
      - Downloaded to C:\\path\\file.mp3
    """
    if not stdout_text:
        return None

    for raw_line in stdout_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        lower_line = line.lower()
        if "downloaded to " in lower_line:
            marker_index = lower_line.rfind("downloaded to ")
            maybe_path = line[marker_index + len("downloaded to "):].strip().strip('"')
            if maybe_path:
                return Path(maybe_path)

        if (line.endswith(".mp3") or line.endswith(".m4a") or
                line.endswith(".opus") or line.endswith(".flac") or
                line.endswith(".wav")):
            return Path(line.strip('"'))

    return None

def download_with_spotdl(spotify_url: str, output_template: str, config: dict) -> Path | None:
    """
    Download a Spotify track URL via spotDL standalone executable.

    Returns:
        Path | None: Downloaded file path if successful, otherwise None.
    """
    spotdl_path = _resolve_spotdl_executable(config.get("spotdl_path", "bin/spotdl.exe"))
    ffmpeg_path = Path(config.get("ffmpeg_path", "bin/ffmpeg.exe"))
    output_format = config.get("format", "mp3")
    overwrite_mode = config.get("overwrite", "skip")
    bitrate = config.get("bitrate")
    timeout = int(config.get("timeout", 600))

    cmd = [
        str(spotdl_path),
        "download",
        spotify_url,
        "--output", output_template,
        "--format", output_format,
        "--overwrite", overwrite_mode,
        "--preload",
        "--ffmpeg", str(ffmpeg_path),
    ]

    if bitrate:
        cmd.extend(["--bitrate", str(bitrate)])

    logging.info("spotDL command: %s", " ".join(cmd))
    print(f"[spotDL] Start download: {spotify_url}")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        err_msg = f"spotDL timeout after {timeout}s: {spotify_url}"
        logging.error(err_msg)
        print(f"[spotDL] ERROR: {err_msg}")
        return None
    except Exception as exc:
        err_msg = f"spotDL invocation failed: {exc}"
        logging.error(err_msg)
        print(f"[spotDL] ERROR: {err_msg}")
        return None

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    if proc.returncode != 0:
        err_msg = f"spotDL failed (code={proc.returncode}): {stderr or stdout}"
        logging.error(err_msg)
        print(f"[spotDL] ERROR: {err_msg}")
        return None

    parsed_path = _extract_spotdl_output_path(stdout)
    if parsed_path:
        if not parsed_path.is_absolute():
            parsed_path = (Path.cwd() / parsed_path).resolve()
        if parsed_path.exists():
            logging.info("spotDL success: %s", parsed_path)
            print(f"[spotDL] Downloaded: {parsed_path}")
            return parsed_path

    output_parent = Path(output_template).parent
    if output_parent.exists():
        candidates = list(output_parent.glob(f"*.{output_format}"))
        if candidates:
            latest_file = max(candidates, key=lambda p: p.stat().st_mtime)
            logging.info("spotDL success (fallback path): %s", latest_file)
            print(f"[spotDL] Downloaded (fallback): {latest_file}")
            return latest_file

    logging.error("spotDL succeeded but output file path could not be resolved.")
    print("[spotDL] ERROR: Download finished but file path not found.")
    return None

def add_metadata_to_file(file_path, info, song_name, log_func, config=None, enrich_metadata=False):
    """Add metadata to downloaded audio file"""
    try:
        if enrich_metadata and config:
            # Use metadata enricher for more detailed metadata
            try:
                enricher = create_metadata_enricher(config)
                # Assuming enricher.enrich_file can take a song name and file path
                # It should then find and apply metadata from external sources (e.g., MusicBrainz)
                log_func(f"  ✨ [Metadata Enriching] {song_name}...")
                success = enricher.enrich_file_metadata(file_path, song_name, log_func)
                enricher.cleanup() # Clean up any session/cache
                if success:
                    log_func(f"  ✅ [Metadata Enriched] {song_name}")
                    return success
                else:
                    log_func(f"  ⚠️ [Metadata Enricher] Failed to enrich {song_name}, falling back to basic metadata.")
            except Exception as e:
                log_func(f"  ⚠️ [Metadata Enricher Error] {str(e)}, falling back to basic metadata.")

        # Fallback to basic metadata from yt-dlp info
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # Extract metadata from YouTube info
        title = info.get('title', '')
        artist = info.get('uploader', '')
        album = info.get('album', '')
        duration = info.get('duration', 0)
        upload_date = info.get('upload_date', '')
        description = info.get('description', '')
        thumbnail_url = info.get('thumbnail', '')
        
        # Try to extract artist and title from song_name if not available
        if not artist or not title:
            if ' - ' in song_name:
                parts = song_name.split(' - ', 1)
                if len(parts) == 2:
                    if not artist:
                        artist = parts[0].strip()
                    if not title:
                        title = parts[1].strip()
            else:
                if not title:
                    title = song_name
        
        # Format upload date as year
        year = upload_date[:4] if upload_date and len(upload_date) >= 4 else ''
        
        # Extract genre from description or tags
        genre = ''
        if info.get('tags'):
            genre_tags = [tag for tag in info['tags'] if 'music' in tag.lower() or 'genre' in tag.lower()]
            if genre_tags:
                genre = genre_tags[0]
                
        # --- NEW: Check for cached Spotify metadata to override yt-dlp ---
        try:
            from utils.config import CONFIG_DIR
            from utils.helpers import sanitize_filename
            import json
            
            clean_filename = sanitize_filename(song_name)
            cache_dir = os.path.join(CONFIG_DIR, 'spotify_cache')
            meta_file = os.path.join(cache_dir, f"{clean_filename}.json")
            
            if os.path.exists(meta_file):
                with open(meta_file, 'r', encoding='utf-8') as mf:
                    cached_meta = json.load(mf)
                    
                if cached_meta:
                    title = cached_meta.get('title', title)
                    artist = cached_meta.get('artist', artist)
                    if cached_meta.get('album'):
                        album = cached_meta['album']
                    
                    date = cached_meta.get('release_date', '')
                    if date:
                        year = str(date)[:4]
                        
                    cover_url = cached_meta.get('cover_url')
                    if cover_url:
                        thumbnail_url = cover_url
                        
                    log_func(f"  ✨ [Spotify Cache] Using rich metadata and cover for {title}")
        except Exception as cache_e:
            log_func(f"  ⚠️ [Cache Error] Failed to read Spotify cache: {cache_e}")
        # --- END NEW ---
        
        if file_ext == '.flac':
            # Handle FLAC files
            audio = FLAC(file_path)
            if title:
                audio['TITLE'] = title
            if artist:
                audio['ARTIST'] = artist
            if album:
                audio['ALBUM'] = album
            if year:
                audio['DATE'] = year
            if genre:
                audio['GENRE'] = genre
            if duration:
                audio['LENGTH'] = str(duration)
            
            # Add source information
            audio['SOURCE'] = 'YouTube'
            audio['COMMENT'] = f'Downloaded via playlist-admin'
            
            # Add artwork
            if thumbnail_url:
                artwork_data = download_image(thumbnail_url)
                if artwork_data:
                    picture = Picture()
                    picture.data = artwork_data
                    picture.type = 3
                    picture.mime = 'image/jpeg'
                    audio.add_picture(picture)
            
            audio.save()
            
        elif file_ext in ['.mp3', '.mp2', '.mp1']:
            # Handle MP3 files
            try:
                audio = EasyID3(file_path)
            except:
                audio = ID3(file_path)
            
            if title:
                if isinstance(audio, EasyID3):
                    audio['title'] = title
                else:
                    audio.add(TIT2(encoding=3, text=title))
            
            if artist:
                if isinstance(audio, EasyID3):
                    audio['artist'] = artist
                else:
                    audio.add(TPE1(encoding=3, text=artist))
            
            if album:
                if isinstance(audio, EasyID3):
                    audio['album'] = album
                else:
                    audio.add(TALB(encoding=3, text=album))
            
            if year:
                if isinstance(audio, EasyID3):
                    audio['date'] = year
                else:
                    audio.add(TDRC(encoding=3, text=year))
            
            if genre:
                if isinstance(audio, EasyID3):
                    audio['genre'] = genre
                else:
                    audio.add(TCON(encoding=3, text=genre))
            
            # Add artwork
            if thumbnail_url:
                artwork_data = download_image(thumbnail_url)
                if artwork_data:
                    if isinstance(audio, EasyID3):
                        audio = ID3(file_path)
                    audio.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=artwork_data))
            
            audio.save()
            
        elif file_ext in ['.m4a', '.mp4']:
            # Handle M4A/MP4 files
            audio = MP4(file_path)
            
            if title:
                audio['\xa9nam'] = title
            if artist:
                audio['\xa9ART'] = artist
            if album:
                audio['\xa9alb'] = album
            if year:
                audio['\xa9day'] = year
            if genre:
                audio['\xa9gen'] = genre
            
            # Add artwork
            if thumbnail_url:
                artwork_data = download_image(thumbnail_url)
                if artwork_data:
                    audio['covr'] = [MP4Cover(artwork_data, imageformat=MP4Cover.FORMAT_JPEG)]
            
            audio.save()
        
        log_func(f"  🏷️ [Metadata Added] {title}")
        return file_path
        
    except Exception as e:
        log_func(f"  ⚠️ [Metadata Error] {str(e)}")
        return None

def download_lyrics(song_name, output_path, log_func, failed_cache=None):
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
        
        # Check if this song is in failed cache
        if failed_cache and song_name in failed_cache:
            log_func(f"  ℹ️ [Lyrics Skipped] {song_name} (previously failed)")
            return False
        
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
            req = urllib.request.Request(url, headers={'User-Agent': 'playlist-admin/2.0'})
            
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

        max_retries = 1  # Only try once
        
        for attempt in range(max_retries):
            try:
                # No progressive delay for single attempt
                # No retry messages for single attempt

                for idx, query in enumerate(search_queries):
                    # Reduce timeout slightly on retries to fail fast and try next
                    lrc_text = fetch_lrc(query, timeout=10 + attempt * 5)
                    
                    if lrc_text:
                        # CONVERT TO TRADITIONAL CHINESE
                        lrc_text = convert(lrc_text, 'zh-tw')
                        
                        os.makedirs(os.path.dirname(output_path), exist_ok=True)
                        with open(output_path, "w", encoding="utf-8") as f:
                            f.write(lrc_text)
                        return True
                    
                    # Small delay between query variations to be nice to API
                    time.sleep(0.5)
                
                # If we get here, no lyrics found for any query in this attempt
                # Since we only try once, add to failed cache and return False
                if failed_cache is not None:
                    failed_cache[song_name] = True
                log_func(f"  ℹ️ [Lrclib Not Found] {song_name}")
                return False
                    
            except Exception as e:
                error_msg = str(e).lower()
                is_net_error = any(k in error_msg for k in ['timeout', 'timed out', 'reset', 'aborted', 'eof', 'ssl'])
                
                if is_net_error:
                    # Add to failed cache for network errors too
                    if failed_cache is not None:
                        failed_cache[song_name] = True
                    log_func(f"  🔌 [Network Failed] {song_name}: {error_msg[:50]}")
                    return False
                else:
                    # Add to failed cache for other errors too
                    if failed_cache is not None:
                        failed_cache[song_name] = True
                    log_func(f"  ❌ [Lyrics Error] {song_name}: {str(e)[:50]}")
                    return False

    except Exception as e:
        log_func(f"  ❌ [Lyrics Critical] {song_name}: {str(e)[:100]}")
        return False
    return False

def download_song(song_name, library_path, audio_format, log_func, file_list, stats=None, speed_display_callback=None, progress_callback=None, current_dl=0, use_dab_lossless=False, use_dab_metadata=False, dab_credentials=None, config=None, artist_hint=None):
    """Downloads song in specified format (mp3 or flac)"""
    
    # Create a simple failed lyrics cache for this session
    lyrics_failed_cache = {}
    
    # If DAB Music is requested and credentials are provided AND asking for FLAC
    if use_dab_lossless and dab_credentials and audio_format == 'flac':
        try:
            # Extract artist name for better matching context
            # Priority: 1. artist_hint, 2. extraction from song_name
            actual_artist_hint = artist_hint
            if not actual_artist_hint and ' - ' in song_name:
                parts = song_name.split(' - ', 1)
                if len(parts) == 2:
                    actual_artist_hint = parts[0].strip()

            dab_downloader = create_dab_downloader(dab_credentials['email'], dab_credentials['password'])
            success = dab_downloader.download_song(
                song_name, library_path, log_func, file_list, stats, 
                progress_callback, current_dl, actual_artist_hint, config
            )
            dab_downloader.logout()
            if success:
                # DAB downloader should return the actual path
                # If it returned True but no path, try to find the file
                if isinstance(success, str):
                    # success is actually the file path
                    final_path = success
                else:
                    # success is True, need to find the file
                    import glob
                    lossless_dir = os.path.join(library_path, "Lossless")
                    if os.path.exists(lossless_dir):
                        # Look for recently downloaded FLAC files
                        flac_files = glob.glob(os.path.join(lossless_dir, "*.flac"))
                        if flac_files:
                            # Get the most recently modified file
                            final_path = max(flac_files, key=os.path.getmtime)
                            log_func(f"  ✅ [DAB Found File] {os.path.basename(final_path)}")
                        else:
                            log_func(f"  ⚠️ [DAB Success but File Not Found] No FLAC files found.")
                            return None
                    else:
                        log_func(f"  ⚠️ [DAB Success but File Not Found] Lossless directory not found.")
                        return None
                
                # Verify the file exists
                if os.path.exists(final_path):
                    # Enriched metadata if requested
                    if use_dab_metadata and config:
                        log_func(f"  ✨ [DAB Download Success] Attempting metadata enrichment for {song_name}")
                        try:
                            # Re-extract/use artist hint if needed for enrichment
                            if not actual_artist_hint and ' - ' in song_name:
                                parts = song_name.split(' - ', 1)
                                if len(parts) == 2:
                                    actual_artist_hint = parts[0].strip()
                                    
                            enricher = create_metadata_enricher(config)
                            enricher.enrich_file_metadata(final_path, song_name, log_func, actual_artist_hint)
                            log_func(f"  ✅ [Metadata Enriched] {song_name}")
                            enricher.cleanup()
                        except Exception as e:
                            log_func(f"  ⚠️ [DAB Metadata Enricher Error] {str(e)}")
                    return final_path
                else:
                    log_func(f"  ⚠️ [DAB Success but File Not Found] {final_path}")
                    return None
            else:
                log_func(f"  ❌ [FLAC Unavailable] {song_name} - DAB Music 無此歌曲的無損版本")
                log_func(f"  ⚠️ [跳過] 無損音檔僅提供於 DAB Music，不降級到 YouTube")
                return None  # 真正的 FLAC 失敗，不 fallback
        except Exception as e:
            log_func(f"  ❌ [DAB Error] {song_name}: {str(e)}")
            log_func(f"  ⚠️ [跳過] DAB Music 服務異常，無法取得無損音檔")
            return None  # 真正的 FLAC 失敗，不 fallback
    
    # 如果是 FLAC 但沒有 DAB Music，直接返回 None
    if audio_format == 'flac' and not use_dab_lossless:
        log_func(f"  ❌ [FLAC Disabled] {song_name} - FLAC 需要啟用 DAB Music")
        return None
    
    # Use the requested format directly
    effective_audio_format = audio_format
    
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
        # Add more frequent checks during download
        if d.get('status') == 'downloading':
            check_stop()  # Check again during download
        # --- DIAGNOSTIC LOG ---
        if not isinstance(d, dict):
            log_func(f"[DIAGNOSTIC] progress_hook received non-dict: type={type(d)}, content={d}")
            return
        # --- END DIAGNOSTIC ---
        
        if d['status'] == 'downloading':
            current_time = time.time()
            
            # Get progress data
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            speed = d.get('speed', 0)
            eta = d.get('eta', 0)
            
            # Calculate current percentage
            current_pct = (downloaded / total * 100) if total > 0 else 0
            
            # Update speed tracking for smoothing
            current_time = time.time()
            if speed and speed > 0:
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
                    elif speed and speed > 0 and total > downloaded:
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
                    progress_callback(current_dl, total, eta_seconds if eta_seconds and eta_seconds > 0 else None)
                
        elif d['status'] == 'finished':
            log_func("  ✅ Download complete, converting...")
    
    # Check if we already have it - use prefer_flac logic when downloading FLAC
    if effective_audio_format == 'flac':
        from core.library import find_song_prefer_flac
        existing = find_song_prefer_flac(song_name, file_list)
        if existing and existing.lower().endswith('.flac'):
            log_func(f"  ✅ [Already Exists] {song_name} (FLAC)")
            return existing
        # If existing is not FLAC, we'll continue to download FLAC even if MP3 exists
    else:
        existing = find_song_in_library(song_name, file_list)
        if existing:
            ext = os.path.splitext(existing)[1].lower().replace('.', '')
            if ext == effective_audio_format:
                log_func(f"  ✅ [Already Exists] {song_name} ({effective_audio_format.upper()})")
                return existing

    clean_name = sanitize_filename(song_name)
    out_template = os.path.join(library_path, f"{clean_name}.%(ext)s")
    
    # Clean up any partial downloads from previous attempts, especially for FLAC
    if effective_audio_format == 'flac':
        import glob
        for ext in ['*.mp4.part', '*.webm.part', '*.m4a.part', '*.part']:
            pattern = os.path.join(library_path, f"{clean_name}.{ext}")
            for part_file in glob.glob(pattern):
                try:
                    os.remove(part_file)
                    log_func(f"  🧹 [Cleaned] Removed partial file: {os.path.basename(part_file)}")
                except Exception as e:
                    log_func(f"  ⚠️ [Cleanup Error] Could not remove {part_file}: {str(e)}")

    # Configure yt-dlp options with PO Token bypass
    if effective_audio_format == 'flac':
        # For FLAC, prioritize audio-only formats to avoid video downloads
        format_string = 'bestaudio[acodec=flac]/bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/ba'
    else:
        # Original format for other formats
        format_string = 'ba/b'  # bestaudio/best - 允許降級到影片再轉檔
    
    ydl_opts = {
        'format': format_string,
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True,
        'extract_audio': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': effective_audio_format,
            'preferredquality': '0' if effective_audio_format == 'flac' else '320',
        }],
        'logger': YdlLogger(log_func, stats),
        'progress_hooks': [progress_hook],
        'keepvideo': False,
        'windowsfilenames': True,
        'restrictfilenames': False,
        # 加入繞過 PO Token 限制的關鍵設定
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'web'],  # 使用多個客戶端繞過限制
                'player_skip': ['webpage'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        },
        'socket_timeout': 60,
        'retries': 3,
        'fragment_retries': 10,
        'skip_unavailable_fragments': True,
        'ignoreerrors': True,
        'no_check_certificates': True,
    }
    
    # Add cookies if available (optional - not required)
    # cookies_path = 'cookies.txt'
    # if os.path.exists(cookies_path):
    #     ydl_opts['cookiefile'] = cookies_path

    # Generate search candidates
    candidates = []
    
    # helper to clean query aggressively
    def clean_query_text(text):
        suffixes = [
            r'\s*\(.*?\)', r'\s*\[.*?\]', r'\s*【.*?】', 
            r'\s*-?\s*Official\s*Video', r'\s*-?\s*Music\s*Video', 
            r'\s*-?\s*TV\s*Version', r'\s*-?\s*MV', r'\s*-?\s*Lyrics',
            r'\s*-?\s*HD', r'\s*-?\s*4K',
            r'\s*-?\s*八大.*?$',  # Strip long TV show descriptions common in user's errors
            r'\s*-?\s*綜合台.*?$',  # Chinese TV station suffixes
            r'\s*-?\s*戲劇台.*?$',  # Chinese drama channel suffixes
            r'\s*-?\s*雙頻道.*?$',  # Dual channel mentions
            r'\s*-?\s*熱播.*?$',  # Hot/broadcast mentions
            r'\s*-?\s*韓劇.*?$',  # Korean drama mentions
            r'\s*-?\s*片頭曲.*?$',  # Opening theme
            r'\s*-?\s*片尾曲.*?$',  # Ending theme
        ]
        q = text
        for s in suffixes:
            q = re.sub(s, '', q, flags=re.IGNORECASE)
        return q.replace(',', ' ').replace('\xa0', ' ').strip()

    # 1. Base clean query
    base_query = clean_query_text(song_name)
    base_query = ' '.join(base_query.split())
    
    # 2. Artist + Title (intelligent split)
    if ' - ' in base_query:
        parts = base_query.split(' - ')
        if len(parts) >= 2:
            artist = parts[0].strip()
            title = parts[1].strip()
            c_at = f"{artist} {title}"
            c_at = ' '.join(c_at.split())
            if c_at and c_at not in candidates:
                candidates.append(c_at)
    
    if base_query not in candidates:
        candidates.append(base_query)
        
    # Limit search query length to avoid issues
    for i in range(len(candidates)):
        if len(candidates[i]) > 60:
            candidates[i] = ' '.join(candidates[i].split()[:8])
    
    # 3. Add common search terms for better relevance
    title_lower = base_query.lower()
    if any(keyword in title_lower for keyword in ['twice', 'blackpink', 'bts', 'seventeen', 'ive', 'nct', 'stray', 'enhypen', 'ateez', 'lisa', 'newjeans', 'tomorrow x together']):
        c5 = base_query + " official mv"
        if len(c5) <= 60 and c5 not in candidates:
            candidates.append(c5)

    from utils.i18n import _
    
    log_func(f"🔍 [Debug] Generated {len(candidates)} search candidates:")
    for i, candidate in enumerate(candidates):
        log_func(f"🔍 [Debug]   {i+1}. '{candidate}' (length: {len(candidate)})")
    
    all_candidates_failed = True  # Track if all candidates fail
    
    for idx, current_query in enumerate(candidates):
        is_last_candidate = (idx == len(candidates) - 1)
        
        # Check for cancellation before each candidate
        check_stop()
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                # Check for cancellation before each attempt
                check_stop()
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    if attempt == 0:
                        if idx == 0:
                            log_func(_('searching', current_query))
                        else:
                            if is_last_candidate and attempt == max_retries - 1:
                                log_func(f"⚠️ {_('dl_fail', 'No results')}. Trying: {current_query}...")
                            else:
                                log_func(_('searching', current_query))
                    
                    check_stop()
                    
                    info = None
                    download_success = False
                    
                    # 階段1: 嘗試標準高品質下載
                    try:
                        info = ydl.extract_info(f"ytsearch1:{current_query}", download=True)
                        download_success = True
                    except yt_dlp.utils.DownloadError as de:
                        error_msg = str(de).lower()
                        
                        # 階段2: 針對格式錯誤的fallback
                        if 'requested format is not available' in error_msg or 'po token' in error_msg:
                            if effective_audio_format == 'flac':
                                # For FLAC, try audio-only formats first
                                log_func(f"⚠️ [FLAC Format Error] 嘗試其他音頻格式: {current_query}")
                                fallback_opts = {
                                    'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
                                    'outtmpl': out_template,
                                    'quiet': True,
                                    'no_warnings': True,
                                    'extract_audio': True,
                                    'postprocessors': [{
                                        'key': 'FFmpegExtractAudio',
                                        'preferredcodec': 'flac',
                                        'preferredquality': '0',
                                    }],
                                    'logger': YdlLogger(log_func, stats),
                                    'progress_hooks': [progress_hook],
                                    'keepvideo': False,
                                    'windowsfilenames': True,
                                    'restrictfilenames': False,
                                    'socket_timeout': 60,
                                    'retries': 3,
                                    'ignoreerrors': True,
                                    'extractor_args': {
                                        'youtube': {
                                            'player_client': ['ios', 'web', 'android'],
                                            'player_skip': ['webpage', 'configs'],
                                        }
                                    },
                                    'http_headers': {
                                        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
                                    },
                                }
                            else:
                                # Original fallback for non-FLAC formats
                                log_func(f"⚠️ [Format Error] 嘗試更寬鬆格式: {current_query}")
                                fallback_opts = {
                                    'format': 'worstvideo[ext=mp4]+worstaudio/best',
                                    'outtmpl': out_template,
                                    'quiet': True,
                                    'no_warnings': True,
                                    'extract_audio': True,
                                    'postprocessors': [{
                                        'key': 'FFmpegExtractAudio',
                                        'preferredcodec': effective_audio_format,
                                        'preferredquality': '0' if effective_audio_format == 'flac' else '320',
                                    }],
                                    'logger': YdlLogger(log_func, stats),
                                    'progress_hooks': [progress_hook],
                                    'keepvideo': False,
                                    'windowsfilenames': True,
                                    'restrictfilenames': False,
                                    'socket_timeout': 60,
                                    'retries': 3,
                                    'ignoreerrors': True,
                                    'extractor_args': {
                                        'youtube': {
                                            'player_client': ['ios', 'web', 'android'],
                                            'player_skip': ['webpage', 'configs'],
                                        }
                                    },
                                    'http_headers': {
                                        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
                                    },
                                }
                            
                            try:
                                with yt_dlp.YoutubeDL(fallback_opts) as fydl:
                                    info = fydl.extract_info(f"ytsearch1:{current_query}", download=True)
                                    download_success = True
                                    log_func(f"✅ [Fallback Success] 使用寬鬆格式下載: {current_query}")
                            except Exception as fallback_error:
                                log_func(f"⚠️ [Fallback Failed] {current_query}: {str(fallback_error)[:100]}")
                                
                                # 階段3: 最終fallback - 使用任何可用格式
                                if effective_audio_format == 'flac':
                                    log_func(f"🔄 [FLAC Final Attempt] 嘗試任何音頻格式: {current_query}")
                                    final_opts = {
                                        'format': 'bestaudio/best',  # 只使用音頻格式
                                        'outtmpl': out_template,
                                        'quiet': True,
                                        'no_warnings': True,
                                        'extract_audio': True,
                                        'postprocessors': [{
                                            'key': 'FFmpegExtractAudio',
                                            'preferredcodec': 'flac',
                                            'preferredquality': '0',
                                        }],
                                        'logger': YdlLogger(log_func, stats),
                                        'progress_hooks': [progress_hook],
                                        'keepvideo': False,
                                        'windowsfilenames': True,
                                        'restrictfilenames': False,
                                        'socket_timeout': 120,
                                        'retries': 5,
                                        'ignoreerrors': True,
                                        'extractor_args': {
                                            'youtube': {
                                                'player_client': ['tv_embed', 'web', 'ios'],
                                                'player_skip': ['webpage', 'configs', 'js'],
                                            }
                                        },
                                        'http_headers': {
                                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                                            'Referer': 'https://www.youtube.com/',
                                        },
                                    }
                                else:
                                    # Original final fallback for non-FLAC
                                    log_func(f"🔄 [Final Attempt] 嘗試任何可用格式: {current_query}")
                                    final_opts = {
                                        'format': 'best[height<=360]/best',  # 限制畫質避免過大檔案
                                        'outtmpl': out_template,
                                        'quiet': True,
                                        'no_warnings': True,
                                        'extract_audio': True,
                                        'postprocessors': [{
                                            'key': 'FFmpegExtractAudio',
                                            'preferredcodec': effective_audio_format,
                                            'preferredquality': '192',  # 降低品質要求
                                        }],
                                        'logger': YdlLogger(log_func, stats),
                                        'progress_hooks': [progress_hook],
                                        'keepvideo': False,
                                        'windowsfilenames': True,
                                        'restrictfilenames': False,
                                        'socket_timeout': 120,  # 增加timeout
                                        'retries': 5,  # 增加重試次數
                                        'ignoreerrors': True,
                                        'extractor_args': {
                                            'youtube': {
                                                'player_client': ['tv_embed', 'web', 'ios'],  # 嘗試TV嵌入
                                                'player_skip': ['webpage', 'configs', 'js'],
                                            }
                                        },
                                        'http_headers': {
                                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                                            'Referer': 'https://www.youtube.com/',
                                        },
                                    }
                                
                                try:
                                    with yt_dlp.YoutubeDL(final_opts) as fydl:
                                        info = fydl.extract_info(f"ytsearch1:{current_query}", download=True)
                                        download_success = True
                                        log_func(f"✅ [Final Success] 使用基本格式下載: {current_query}")
                                except Exception as final_error:
                                    log_func(f"❌ [All Attempts Failed] {current_query}: {str(final_error)[:100]}")
                                    raise de
                        else:
                            # 非格式相關錯誤，直接拋出
                            raise de
                    except Exception as e:
                        if not download_success:
                            raise e

                    if not info:
                        log_func(f"⚠️ [No Info] {current_query}: No video information found")
                        break

                    # Check if info is a dictionary and has expected keys
                    if not isinstance(info, dict):
                        log_func(f"  [Invalid Info] {current_query}: Info is not a dictionary")
                        break

                    if 'entries' in info and info['entries']:
                        log_func(f" [Debug] Found {len(info['entries'])} entries for '{current_query}'")
                        for i, entry in enumerate(info['entries']):
                            if entry:
                                log_func(f" [Debug] Entry {i}: {entry.get('title', 'No title')} - {entry.get('id', 'No ID')}")
                            else:
                                log_func(f" [Debug] Entry {i}: None")
                        info = info['entries'][0]
                        if not info:
                            log_func(f"  [Empty Entry] {current_query}: First entry is None")
                            # Break to try next candidate
                            break
                    elif 'entries' in info:
                        # Empty entries = No results
                        log_func(f" [Debug] No entries found for '{current_query}'")
                        log_func(f" [Debug] Info keys: {list(info.keys()) if isinstance(info, dict) else 'Not a dict'}")
                        # Break inner retry loop to try next candidate
                        break 
                    else:
                        log_func(f" [Debug] Direct video info for '{current_query}'")
                        log_func(f" [Debug] Video title: {info.get('title', 'No title') if isinstance(info, dict) else 'Not a dict'}")

                    # Check if info is valid before proceeding
                    if not info:
                        log_func(f"  [Invalid Info] {current_query}: Info is None or invalid")
                        break

                    try:
                        filename = ydl.prepare_filename(info)
                    except Exception as e:
                        log_func(f"  [Filename Error] {current_query}: Cannot prepare filename - {str(e)}")
                        break
                    base, ext = os.path.splitext(filename)
                    final_path = base + "." + effective_audio_format
                    
                    if os.path.exists(final_path):
                        log_func(f" -> {os.path.basename(final_path)}")
                        # Add metadata
                        new_path = add_metadata_to_file(final_path, info, song_name, log_func, config, use_dab_metadata)
                        
                        # Auto-rename file based on metadata if metadata was added successfully
                        if new_path:
                            # Update final_path if changed
                            if os.path.exists(new_path):
                                final_path = new_path
                                
                            try:
                                from core.file_renamer import create_file_renamer
                                renamer = create_file_renamer(library_path, log_func)
                                rename_result = renamer.rename_file(final_path, dry_run=False)
                                if rename_result['success'] and rename_result['new_path'] != final_path:
                                    log_func(f"  🔄 [Auto Renamed] {os.path.basename(rename_result['new_path'])}")
                                    final_path = rename_result['new_path']
                            except Exception as e:
                                log_func(f"  ⚠️ [Auto Rename Failed] {str(e)}")
                        
                        # Download lyrics
                        from utils.config import get_lyrics_file_path
                        lrc_path = get_lyrics_file_path(config, final_path)
                        if not os.path.exists(lrc_path) and config and config.get('enable_retroactive_lyrics', False):
                            download_lyrics(song_name, lrc_path, log_func, lyrics_failed_cache)
                        return final_path
                    
                    if os.path.exists(filename):
                        log_func(f" -> {os.path.basename(filename)}")
                        # Add metadata
                        new_path = add_metadata_to_file(filename, info, song_name, log_func, config, use_dab_metadata)
                        
                        # Auto-rename file based on metadata if metadata was added successfully
                        if new_path:
                            # Update filename if changed
                            if os.path.exists(new_path):
                                filename = new_path
                                
                            try:
                                from core.file_renamer import create_file_renamer
                                renamer = create_file_renamer(library_path, log_func)
                                rename_result = renamer.rename_file(filename, dry_run=False)
                                if rename_result['success'] and rename_result['new_path'] != filename:
                                    log_func(f"  🔄 [Auto Renamed] {os.path.basename(rename_result['new_path'])}")
                                    filename = rename_result['new_path']
                            except Exception as e:
                                log_func(f"  ⚠️ [Auto Rename Failed] {str(e)}")
                        
                        # Download lyrics
                        from utils.config import get_lyrics_file_path
                        lrc_path = get_lyrics_file_path(config, filename)
                        if not os.path.exists(lrc_path) and config and config.get('enable_retroactive_lyrics', False):
                            download_lyrics(song_name, lrc_path, log_func, lyrics_failed_cache)
                        all_candidates_failed = False  # Mark as successful
                        return filename
                    
                    # Download lyrics for final_path even if it doesn't exist yet (it will be created by PP)
                    from utils.config import get_lyrics_file_path
                    lrc_path = get_lyrics_file_path(config, final_path)
                    if not os.path.exists(lrc_path) and config and config.get('enable_retroactive_lyrics', False):
                        download_lyrics(song_name, lrc_path, log_func, lyrics_failed_cache)
                    
                    # Add metadata after download is complete
                    if os.path.exists(final_path):
                        new_path = add_metadata_to_file(final_path, info, song_name, log_func, config, use_dab_metadata)
                        
                        # Auto-rename file based on metadata if metadata was added successfully
                        if new_path:
                            # Update final_path if changed
                            if os.path.exists(new_path):
                                final_path = new_path
                                
                            try:
                                from core.file_renamer import create_file_renamer
                                renamer = create_file_renamer(library_path, log_func)
                                rename_result = renamer.rename_file(final_path, dry_run=False)
                                if rename_result['success'] and rename_result['new_path'] != final_path:
                                    log_func(f"  🔄 [Auto Renamed] {os.path.basename(rename_result['new_path'])}")
                                    final_path = rename_result['new_path']
                            except Exception as e:
                                log_func(f"  ⚠️ [Auto Rename Failed] {str(e)}")
                    
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
        if effective_audio_format == 'flac':
            log_func(f"❌ [無損音檔取得失敗] {song_name}")
            log_func(f"   💡 說明：此歌曲在 DAB Music 中沒有無損版本")
            log_func(f"   🎯 建議：如需下載此歌曲，請改用 MP3 格式")
        else:
            log_func(f"❌ {_('dl_fail', 'All search attempts failed')}")
        
    return None
