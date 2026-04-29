#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(__file__))

base_path = 'C:\\Users\\user\\Music\\spotube'
print(f"Checking: {base_path}")
print(f"Exists: {os.path.exists(base_path)}")
print(f"Is dir: {os.path.isdir(base_path)}")

if os.path.exists(base_path):
    try:
        entries = os.listdir(base_path)
        print(f"Entries: {entries}")
        
        lower_entries = {e.lower() for e in entries}
        print(f"Lower entries: {lower_entries}")
        
        has_spotube = 'spotube' in lower_entries
        has_m4a_mp3 = {'m4a', 'mp3'} & lower_entries
        has_playlists = 'playlists' in lower_entries
        
        print(f"Has 'spotube': {has_spotube}")
        print(f"Has m4a/mp3: {has_m4a_mp3}")
        print(f"Has playlists: {has_playlists}")
        
        # Replicate the logic from _looks_like_music_root (updated)
        def _looks_like_music_root_local(path):
            if not path or not os.path.isdir(path):
                return False
            try:
                entries = os.listdir(path)
            except Exception:
                return False

            lower_entries = {e.lower() for e in entries}
            if 'spotube' in lower_entries:
                return True
            if {'m4a', 'mp3'} & lower_entries and 'playlists' in lower_entries:
                return True
            # If there's a playlists folder, consider it a music root
            if 'playlists' in lower_entries:
                return True

            for name in entries:
                if name.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm')):
                    return True
            return False
        
        looks_like_root = _looks_like_music_root_local(base_path)
        print(f"_looks_like_music_root result: {looks_like_root}")
        
        if not looks_like_root:
            library_root = os.path.join(base_path, 'Music')
            print(f"Would use library_path: {library_root}")
        else:
            library_root = base_path
            print(f"Would use library_path: {library_root}")
            
    except Exception as e:
        print(f"Error: {e}")
