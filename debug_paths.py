#!/usr/bin/env python3
import sys
import os
import json
sys.path.append(os.path.dirname(__file__))

# Load actual config
with open('C:/Users/user/Music/spotube/config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

print("=== CONFIG ANALYSIS ===")
print(f"library_path: {config.get('library_path')}")
print(f"base_path: {config.get('base_path')}")
print(f"spotube_m4a_subfolder: {config.get('spotube_m4a_subfolder')}")
print(f"spotube_mp3_subfolder: {config.get('spotube_mp3_subfolder')}")

from core.library import _resolve_spotube_paths
m4a_path, mp3_path = _resolve_spotube_paths(config)
print(f"\n=== RESOLVED PATHS ===")
print(f"M4A Path: {m4a_path}")
print(f"MP3 Path: {mp3_path}")

# Check if paths exist
print(f"\n=== PATH EXISTENCE ===")
print(f"M4A exists: {os.path.exists(m4a_path)}")
print(f"MP3 exists: {os.path.exists(mp3_path)}")

# Check actual library path
library_path = config.get('library_path')
print(f"\n=== LIBRARY PATH ANALYSIS ===")
print(f"Library path: {library_path}")
print(f"Library exists: {os.path.exists(library_path)}")

# Check if there's a Music subfolder
music_subfolder = os.path.join(library_path, 'Music')
print(f"Music subfolder: {music_subfolder}")
print(f"Music subfolder exists: {os.path.exists(music_subfolder)}")
