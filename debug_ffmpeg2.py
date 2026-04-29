#!/usr/bin/env python3
import sys
import os
import subprocess
sys.path.append(os.path.dirname(__file__))

# Test FFmpeg directly with Chinese filename
m4a_file = r"C:\Users\user\Music\spotube\m4a\一萬公里外的你 - Juice Boy.m4a"
mp3_file = r"C:\Users\user\Desktop\Playlist_Administrator\test_output.mp3"

print(f"M4A file: {m4a_file}")
print(f"M4A exists: {os.path.exists(m4a_file)}")
print(f"M4A bytes: {m4a_file.encode('utf-8')}")

# Get FFmpeg path
ffmpeg_path = r"C:\Users\user\Desktop\Playlist_Administrator\bin\ffmpeg.exe"
print(f"FFmpeg path: {ffmpeg_path}")
print(f"FFmpeg exists: {os.path.exists(ffmpeg_path)}")

# Test FFmpeg command
cmd = [
    ffmpeg_path,
    '-i', m4a_file,
    '-acodec', 'mp3',
    '-ab', '192k',
    mp3_file
]

print(f"\n=== FFmpeg command ===")
print(f"Command: {' '.join(cmd)}")

try:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    print(f"Return code: {result.returncode}")
    print(f"Stdout: {result.stdout}")
    print(f"Stderr: {result.stderr}")
except Exception as e:
    print(f"Error: {e}")
