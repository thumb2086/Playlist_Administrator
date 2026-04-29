#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(__file__))

# Import the module directly
import utils.config

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
        
        # Check the actual function
        looks_like_root = utils.config._looks_like_music_root(base_path)
        print(f"_looks_like_music_root result: {looks_like_root}")
        
        if not looks_like_root:
            library_root = os.path.join(base_path, 'Music')
            print(f"Would use library_path: {library_root}")
        else:
            library_root = base_path
            print(f"Would use library_path: {library_root}")
            
    except Exception as e:
        print(f"Error: {e}")
