#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(__file__))

from core.library import _resolve_spotube_paths

config = {
    'library_path': 'C:\\Users\\user\\Music\\spotube',
    'spotube_m4a_subfolder': 'm4a',
    'spotube_mp3_subfolder': 'mp3'
}

m4a_path, mp3_path = _resolve_spotube_paths(config)
print(f'M4A Path: {m4a_path}')
print(f'MP3 Path: {mp3_path}')
