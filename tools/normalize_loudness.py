"""
Batch normalize MP3 loudness to EBU R128 (-14 LUFS) using ffmpeg.
Multi-threaded for i9 processors.
"""
import os, sys, subprocess, shutil, json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

TARGET_I = -14
TARGET_TP = -1
TARGET_LRA = 7

ffmpeg_path = shutil.which('ffmpeg')
if not ffmpeg_path:
    print('ffmpeg not found')
    sys.exit(1)

lock = threading.Lock()
done = 0
failed = 0
total = 0

def normalize_one(mp3):
    global done, failed
    base, ext = os.path.splitext(mp3)
    tmp = base + '_tmp' + ext
    cmd = [ffmpeg_path, '-y', '-i', mp3,
           '-af', f'loudnorm=I={TARGET_I}:TP={TARGET_TP}:LRA={TARGET_LRA}',
           '-c:a', 'libmp3lame', '-q:a', '2',
           tmp]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=300,
                           encoding='utf-8', errors='replace')
        if r.returncode != 0 or not os.path.exists(tmp):
            with lock:
                failed += 1
            return False
        os.replace(tmp, mp3)
        with lock:
            done += 1
        return True
    except:
        with lock:
            failed += 1
        return False

def progress():
    while True:
        with lock:
            d, f = done, failed
        sys.stdout.write(f'\r  ✅ {d}  ❌ {f}  / {total}')
        sys.stdout.flush()
        if d + f >= total:
            break
        import time
        time.sleep(2)

def main():
    global total
    base = os.path.expanduser(r'~\Music\Spotube')
    dirs = [os.path.join(base, 'Music'), os.path.join(base, 'mp3')]
    all_mp3 = []
    for d in dirs:
        if os.path.exists(d):
            for root, _, files in os.walk(d):
                for f in files:
                    if f.lower().endswith('.mp3'):
                        all_mp3.append(os.path.join(root, f))
    total = len(all_mp3)
    if not total:
        print('No MP3 files found')
        return

    print(f'Total: {total} MP3 files')
    print(f'Target: {TARGET_I} LUFS')
    print(f'Workers: {os.cpu_count()} (full i9)')
    print(f'Starting...\n')

    import threading as t
    t.Thread(target=progress, daemon=True).start()

    with ThreadPoolExecutor(max_workers=os.cpu_count()) as pool:
        futures = [pool.submit(normalize_one, f) for f in all_mp3]
        for _ in as_completed(futures):
            pass

    print(f'\n\nDone: {done} OK, {failed} failed')

if __name__ == '__main__':
    main()
