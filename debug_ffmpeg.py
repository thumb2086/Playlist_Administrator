#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.dirname(__file__))

from core.audio_converter import convert_audio_file
from core.ffmpeg_installer import get_ffmpeg_path

# Test with one M4A file
m4a_file = r"C:\Users\user\Music\spotube\m4a\一萬公里外的你 - Juice Boy.m4a"
mp3_file = r"C:\Users\user\Music\spotube\mp3\一萬公里外的你 - Juice Boy.mp3"

print(f"M4A file: {m4a_file}")
print(f"M4A exists: {os.path.exists(m4a_file)}")
print(f"MP3 file: {mp3_file}")
print(f"MP3 exists: {os.path.exists(mp3_file)}")

# Get FFmpeg path
config = {'ffmpeg_path': 'bin/ffmpeg.exe'}
ffmpeg_path = get_ffmpeg_path(config)
print(f"FFmpeg path: {ffmpeg_path}")
print(f"FFmpeg exists: {os.path.exists(ffmpeg_path)}")

# Create MP3 directory if it doesn't exist
os.makedirs(os.path.dirname(mp3_file), exist_ok=True)

# Test conversion
def log_func(msg):
    print(msg)

print("\n=== Testing conversion ===")
success = convert_audio_file(m4a_file, mp3_file, 'mp3', log_func)
print(f"Conversion result: {success}")
