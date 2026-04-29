"""
Audio Converter Utility
Handles conversion between different audio formats (MP3, FLAC, etc.)
"""

import os
import subprocess
import tempfile
from pathlib import Path


def _metadata_match_key(value):
    import re
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(value or "").lower())


def _migrate_m4a_metadata_to_mp3(m4a_path, mp3_path, log_func=None):
    """
    Migrate metadata from M4A to MP3 using mutagen.
    This is necessary because ffmpeg -map_metadata doesn't properly convert MP4 tags to ID3 tags.
    """
    try:
        from mutagen.mp4 import MP4
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TDRC, TCON, APIC, COMM
        
        # Read M4A metadata
        m4a = MP4(m4a_path)
        mp3 = MP3(mp3_path)
        
        # Ensure MP3 has ID3 tags
        if mp3.tags is None:
            mp3.add_tags()
        
        # Map MP4 tags to ID3 tags
        # \xa9nam = title, \xa9ART = artist, \xa9alb = album, \xa9day = date/year, \xa9gen = genre
        tag_mapping = {
            '\xa9nam': ('TIT2', TIT2),      # Title
            '\xa9ART': ('TPE1', TPE1),      # Artist
            '\xa9alb': ('TALB', TALB),      # Album
            '\xa9day': ('TDRC', TDRC),      # Date/Year
            '\xa9gen': ('TCON', TCON),      # Genre
        }
        
        for m4a_tag, (id3_name, id3_class) in tag_mapping.items():
            if m4a_tag in m4a and m4a[m4a_tag]:
                value = m4a[m4a_tag][0] if isinstance(m4a[m4a_tag], list) else m4a[m4a_tag]
                if value:
                    mp3.tags[id3_name] = id3_class(encoding=3, text=str(value))
                    if log_func:
                        log_func(f"    📝 Migrated {m4a_tag}: {value}")
        
        # Handle album artist (aART in MP4 -> TPE2 in ID3)
        if 'aART' in m4a and m4a['aART']:
            album_artist = m4a['aART'][0] if isinstance(m4a['aART'], list) else m4a['aART']
            if album_artist:
                mp3.tags['TPE2'] = TPE2(encoding=3, text=str(album_artist))
        
        # Handle cover art (covr in MP4 -> APIC in ID3)
        if 'covr' in m4a and m4a['covr']:
            cover_data = m4a['covr'][0]
            if cover_data:
                mp3.tags['APIC'] = APIC(
                    encoding=0, 
                    mime='image/jpeg', 
                    type=3,  # Front cover
                    desc='Cover', 
                    data=cover_data
                )
                if log_func:
                    log_func(f"    🖼️ Migrated album cover")
        
        # Add comment to indicate source
        mp3.tags['COMM'] = COMM(encoding=3, lang='eng', desc='Source', text='Converted from M4A by Playlist Administrator')
        
        mp3.save()
        
        if log_func:
            log_func(f"    ✅ Metadata migrated successfully")
        return True
        
    except Exception as e:
        if log_func:
            log_func(f"    ⚠️ Metadata migration failed: {str(e)}")
        return False


def _enrich_metadata_from_spotify_cache(file_path, log_func=None):
    """
    Enrich file metadata from Spotify cache (if available).
    This updates English artist names to Chinese and adds cover art.
    """
    try:
        import json
        from utils.config import CONFIG_DIR
        from utils.helpers import sanitize_filename
        from mutagen.easyid3 import EasyID3
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, APIC
        
        # Get filename without extension for cache lookup
        base_name = Path(file_path).stem
        cache_dir = os.path.join(CONFIG_DIR, 'spotify_cache')
        
        if not os.path.exists(cache_dir):
            return False
        
        # Try to find matching cache file
        cache_file = os.path.join(cache_dir, f"{sanitize_filename(base_name)}.json")
        
        if not os.path.exists(cache_file):
            # Try fuzzy match with all cache files
            for cf in os.listdir(cache_dir):
                if cf.endswith('.json'):
                    cf_path = os.path.join(cache_dir, cf)
                    try:
                        with open(cf_path, 'r', encoding='utf-8') as f:
                            cached = json.load(f)
                        # Check if title matches
                        if cached.get('title') and base_name.lower().replace(' ', '') in cached['title'].lower().replace(' ', ''):
                            cache_file = cf_path
                            break
                    except:
                        continue
        
        if not os.path.exists(cache_file):
            return False
        
        # Load Spotify metadata
        with open(cache_file, 'r', encoding='utf-8') as f:
            spotify_meta = json.load(f)
        
        if not spotify_meta:
            return False

        try:
            current_easy = EasyID3(file_path)
            current_title = current_easy.get('title', [None])[0]
        except Exception:
            current_title = None

        spotify_title = spotify_meta.get('title')
        if current_title and spotify_title:
            current_key = _metadata_match_key(current_title)
            spotify_key = _metadata_match_key(spotify_title)
            if current_key and spotify_key and current_key != spotify_key:
                if log_func:
                    log_func(
                        "    ⚠️ Spotify cache title mismatch; skipped enrichment "
                        f"({current_title} != {spotify_title})"
                    )
                return False
        
        # Apply to MP3
        mp3 = MP3(file_path)
        if mp3.tags is None:
            mp3.add_tags()
        
        updated = False
        
        # Update title (prefer Spotify Chinese title)
        if spotify_meta.get('title'):
            mp3.tags['TIT2'] = TIT2(encoding=3, text=spotify_meta['title'])
            updated = True
            if log_func:
                log_func(f"    📝 Updated title: {spotify_meta['title']}")
        
        # Update artist (prefer Spotify Chinese artist name)
        if spotify_meta.get('artist'):
            mp3.tags['TPE1'] = TPE1(encoding=3, text=spotify_meta['artist'])
            updated = True
            if log_func:
                log_func(f"    🎤 Updated artist: {spotify_meta['artist']}")
        
        # Update album
        if spotify_meta.get('album'):
            mp3.tags['TALB'] = TALB(encoding=3, text=spotify_meta['album'])
            updated = True
        
        # Update year from release_date
        if spotify_meta.get('release_date'):
            year = spotify_meta['release_date'][:4] if len(spotify_meta['release_date']) >= 4 else spotify_meta['release_date']
            mp3.tags['TDRC'] = TDRC(encoding=3, text=year)
            updated = True
        
        # Download and add cover art if available
        if spotify_meta.get('cover_url'):
            try:
                from utils.helpers import download_image
                cover_data = download_image(spotify_meta['cover_url'])
                if cover_data:
                    mp3.tags['APIC'] = APIC(
                        encoding=0,
                        mime='image/jpeg',
                        type=3,
                        desc='Cover',
                        data=cover_data
                    )
                    updated = True
                    if log_func:
                        log_func(f"    🖼️ Added cover art from Spotify")
            except Exception as e:
                if log_func:
                    log_func(f"    ⚠️ Failed to download cover art: {e}")
        
        if updated:
            mp3.save()
            if log_func:
                log_func(f"    ✨ Metadata enriched from Spotify cache")
        
        return updated
        
    except Exception as e:
        if log_func:
            log_func(f"    ⚠️ Spotify enrichment failed: {str(e)}")
        return False

def convert_audio_file(input_path, output_path, target_format, log_func=None, ffmpeg_path=None):
    """
    Convert audio file to target format using ffmpeg
    
    Args:
        input_path: Path to input audio file
        output_path: Path for output audio file
        target_format: Target format ('mp3' or 'flac')
        log_func: Optional logging function
        ffmpeg_path: Path to ffmpeg executable (optional, defaults to 'ffmpeg')
    
    Args:
        input_path: Path to input audio file
        output_path: Path for output audio file
        target_format: Target format ('mp3' or 'flac')
        log_func: Optional logging function
    
    Returns:
        bool: True if conversion successful, False otherwise
    """
    try:
        # Check if input file exists
        if not os.path.exists(input_path):
            if log_func:
                log_func(f"  ❌ Input file not found: {input_path}")
            return False
        
        # Get input file extension
        input_ext = Path(input_path).suffix.lower()
        output_ext = Path(output_path).suffix.lower()
        
        # If already in target format, just copy
        if input_ext == f".{target_format}":
            import shutil
            shutil.copy2(input_path, output_path)
            if log_func:
                log_func(f"  📋 Copied (already {target_format.upper()}): {os.path.basename(input_path)}")
            return True
        
        # Prepare ffmpeg command
        # Use provided ffmpeg_path or default to 'ffmpeg'
        ffmpeg_cmd = ffmpeg_path if ffmpeg_path else 'ffmpeg'
        
        if target_format == 'mp3':
            # High quality MP3 conversion with metadata preservation
            cmd = [
                ffmpeg_cmd, '-y',  # Overwrite output files
                '-i', input_path,
                '-map_metadata', '0',  # Copy metadata from input
                '-codec:a', 'libmp3lame',
                '-qscale:a', '0',  # Highest quality VBR
                '-ar', '44100',    # Sample rate
                output_path
            ]
        elif target_format == 'flac':
            # Lossless FLAC conversion with metadata preservation
            cmd = [
                ffmpeg_cmd, '-y',
                '-i', input_path,
                '-map_metadata', '0',  # Copy metadata from input
                '-codec:a', 'flac',
                '-compression_level', '8',  # Good compression
                output_path
            ]
        else:
            if log_func:
                log_func(f"  ❌ Unsupported target format: {target_format}")
            return False
        
        # Run conversion
        if log_func:
            log_func(f"  🔄 Converting to {target_format.upper()}: {os.path.basename(input_path)}")
        
        creationflags = 0
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NO_WINDOW

        # Fix encoding issues on Windows with Chinese filenames
        if os.name == 'nt':
            # On Windows, don't use text mode to avoid encoding issues
            result = subprocess.run(
                cmd,
                capture_output=True,
                creationflags=creationflags,
                timeout=300  # 5 minute timeout per file
            )
            # Decode output manually with error handling
            try:
                stdout = result.stdout.decode('utf-8', errors='replace')
                stderr = result.stderr.decode('utf-8', errors='replace')
            except:
                stdout = str(result.stdout)
                stderr = str(result.stderr)
        else:
            # On Unix systems, use text mode
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=300  # 5 minute timeout per file
            )
            stdout = result.stdout
            stderr = result.stderr
        
        if result.returncode == 0:
            if log_func:
                log_func(f"  ✅ Converted: {os.path.basename(input_path)} → {os.path.basename(output_path)}")
            
            # M4A to MP3: Migrate metadata using mutagen (ffmpeg -map_metadata doesn't work well)
            if input_ext == '.m4a' and target_format == 'mp3':
                if log_func:
                    log_func(f"  🔄 Migrating metadata from M4A...")
                _migrate_m4a_metadata_to_mp3(input_path, output_path, log_func)
                
                # Also enrich from Spotify cache for better metadata (Chinese artist names, etc.)
                if log_func:
                    log_func(f"  🔄 Enriching from Spotify cache...")
                _enrich_metadata_from_spotify_cache(output_path, log_func)
            
            return True
        else:
            if log_func:
                log_func(f"  ❌ Conversion failed: {os.path.basename(input_path)}")
                log_func(f"     Error: {stderr.strip()}")
            return False
            
    except subprocess.TimeoutExpired:
        if log_func:
            log_func(f"  ⏱️ Conversion timeout: {os.path.basename(input_path)}")
        return False
    except Exception as e:
        if log_func:
            log_func(f"  ❌ Conversion error: {os.path.basename(input_path)} - {str(e)}")
        return False

def convert_audio_if_needed(input_path, target_format, log_func=None):
    """
    Convert audio file if it's not already in target format
    
    Args:
        input_path: Path to input audio file
        target_format: Target format ('mp3', 'flac', or 'original')
        log_func: Optional logging function
    
    Returns:
        str: Path to the file in target format (original or converted)
        bool: True if conversion was performed, False if original was used
    """
    if target_format == 'original':
        return input_path, False
    
    input_ext = Path(input_path).suffix.lower()
    target_ext = f".{target_format}"
    
    # If already in target format, return original
    if input_ext == target_ext:
        return input_path, False
    
    # Create temporary output path
    temp_dir = tempfile.gettempdir()
    base_name = Path(input_path).stem
    output_path = os.path.join(temp_dir, f"{base_name}{target_ext}")
    
    # Perform conversion
    success = convert_audio_file(input_path, output_path, target_format, log_func)
    
    if success:
        return output_path, True
    else:
        # If conversion fails, return original
        if log_func:
            log_func(f"  ⚠️ Using original file due to conversion failure: {os.path.basename(input_path)}")
        return input_path, False

def check_ffmpeg_available():
    """Check if ffmpeg is available in the system"""
    try:
        creationflags = 0
        if os.name == 'nt':
            creationflags = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=10, creationflags=creationflags)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

def get_audio_format(file_path):
    """Get the audio format of a file"""
    ext = Path(file_path).suffix.lower()
    format_map = {
        '.mp3': 'mp3',
        '.flac': 'flac',
        '.m4a': 'm4a',
        '.wav': 'wav',
        '.webm': 'webm'
    }
    return format_map.get(ext, 'unknown')
