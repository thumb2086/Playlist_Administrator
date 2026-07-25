"""
Debug: test SRT download for one specific file from the failing batch.
"""
import subprocess, os, sys

test_dir = r'C:\Users\CPXru\Music\Spotube\podcast_downloads\游庭皓的財經皓角'
cookie_file = r'C:\Users\CPXru\Desktop\thumb\大拇哥實驗室\cookies.txt'

files = sorted([f for f in os.listdir(test_dir) if f.endswith('.mp3')])

# Test file #230 
idx = 230
name = files[idx].replace('.mp3', '')
clean = name.replace('_', ' ').replace('\u3010', '').replace('\u3011', '').replace('[', '').replace(']', '')
query = f'{clean} 游庭皓的財經皓角'
print(f'File #{idx}: {files[idx]}')
print(f'Query: {query}')

# Step 1: Search
print(f'\n--- Step 1: Search YouTube ---')
r1 = subprocess.run(
    ['yt-dlp', '--cookies', cookie_file, f'ytsearch:{query}',
     '--skip-download', '--print', 'id'],
    capture_output=True, timeout=30, encoding='utf-8', errors='replace')
found = r1.stdout.strip()
print(f'rc: {r1.returncode}')
if found:
    print(f'FOUND: {found}')
else:
    print(f'NOT FOUND')
    print(f'stderr: {r1.stderr[:300]}')
    sys.exit(1)

# Step 2: Download with write-subs (NOT write-auto-subs)
print(f'\n--- Step 2: Download subs (write-subs) ---')
base = os.path.join(test_dir, 'debug_srt')
r2 = subprocess.run(
    ['yt-dlp', '--cookies', cookie_file,
     f'https://www.youtube.com/watch?v={found}',
     '--skip-download',
     '--write-subs',
     '--sub-langs', 'zh-TW',
     '--sub-format', 'srt',
     '--convert-subs', 'srt',
     '--output', base + '.%(ext)s',
     '--windows-filenames', '--no-warnings'],
    capture_output=True, timeout=30, encoding='utf-8', errors='replace')
print(f'rc: {r2.returncode}')
print(f'stdout: {r2.stdout[:200]}')
print(f'stderr: {r2.stderr[:500]}')

# List created files
for f in os.listdir(test_dir):
    if 'debug_srt' in f:
        print(f'  CREATED: {f} ({os.path.getsize(os.path.join(test_dir, f))} bytes)')

# Clean up
for f in os.listdir(test_dir):
    if 'debug_srt' in f:
        os.remove(os.path.join(test_dir, f))
