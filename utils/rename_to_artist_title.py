import os
import glob
import sys
from pathlib import Path

# Ensure we can import from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.config import load_config
from utils.helpers import sanitize_filename

try:
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3
    from mutagen.easyid3 import EasyID3
    from mutagen.mp4 import MP4
except ImportError as e:
    print(f"Error importing mutagen: {e}")
    # print("Error: mutagen library is not installed. Please run: pip install mutagen")
    sys.exit(1)

def get_metadata(file_path):
    """Extracts Artist and Title from file metadata."""
    artist = None
    title = None
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == '.flac':
            audio = FLAC(file_path)
            artist = audio.get('ARTIST', [None])[0]
            title = audio.get('TITLE', [None])[0]
        elif ext in ['.mp3', '.mp2', '.mp1']:
            try:
                audio = EasyID3(file_path)
                artist = audio.get('artist', [None])[0]
                title = audio.get('title', [None])[0]
            except:
                audio = ID3(file_path)
                if 'TPE1' in audio: artist = str(audio['TPE1'])
                if 'TIT2' in audio: title = str(audio['TIT2'])
        elif ext in ['.m4a', '.mp4']:
            audio = MP4(file_path)
            artist = audio.get('\xa9ART', [None])[0]
            title = audio.get('\xa9nam', [None])[0]
    except Exception as e:
        pass

    return artist, title

def rename_files(library_path, dry_run=True):
    print(f"Scanning library: {library_path}")
    print(f"Mode: {'DRY RUN (Simulation)' if dry_run else 'EXECUTION (Real Changes)'}")
    print("-" * 50)

    search_pattern = os.path.join(library_path, "**", "*")
    all_files = glob.glob(search_pattern, recursive=True)
    audio_files = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav'))]

    renamed_count = 0
    skipped_count = 0
    error_count = 0

    for file_path in audio_files:
        try:
            filename = os.path.basename(file_path)
            
            # Check if likely already "Artist - Title" (contains hyphen)
            # But we double check metadata to be sure it matches preferred format
            
            artist, title = get_metadata(file_path)

            if not artist or not title:
                # print(f"[SKIP] No Metadata: {filename}")
                skipped_count += 1
                continue

            # Cleanup Artist (take first if multiple)
            if isinstance(artist, list): artist = artist[0]
            if '/' in artist: artist = artist.split('/')[0]
            if ';' in artist: artist = artist.split(';')[0]
            
            # Construct new name
            clean_artist = sanitize_filename(artist.strip())
            clean_title = sanitize_filename(title.strip())
            ext = os.path.splitext(filename)[1]
            
            new_name = f"{clean_artist} - {clean_title}{ext}"
            
            # Check if rename is needed
            if filename != new_name:
                dir_path = os.path.dirname(file_path)
                new_path = os.path.join(dir_path, new_name)

                if os.path.exists(new_path):
                    print(f"[SKIP] Target exists: {filename} -> {new_name}")
                    skipped_count += 1
                    continue

                if dry_run:
                    print(f"[RENAME] {filename} -> {new_name}")
                else:
                    try:
                        os.rename(file_path, new_path)
                        print(f"[OK] {filename} -> {new_name}")
                    except Exception as e:
                        print(f"[ERROR] Failed to rename {filename}: {e}")
                        error_count += 1
                        continue
                
                renamed_count += 1
            else:
                # print(f"[OK] Already correct: {filename}")
                pass

        except Exception as e:
            print(f"[ERROR] processing {file_path}: {e}")
            error_count += 1

    print("-" * 50)
    print(f"Finished.")
    print(f"Renamed: {renamed_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Errors: {error_count}")

if __name__ == "__main__":
    config = load_config()
    library_path = config.get('library_path')
    
    if not library_path or not os.path.exists(library_path):
        print("Error: Library path not found in config.")
        sys.exit(1)

    # Check for argument
    dry_run = True
    if len(sys.argv) > 1 and sys.argv[1] == '--run':
        dry_run = False
        
    rename_files(library_path, dry_run=dry_run)
