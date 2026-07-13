"""
Scan all M4A and MP3 files in the music library and measure their integrated LUFS.
Caches results to m4a_lufs_cache.json and mp3_lufs_cache.json.
Multi-threaded for i9 processors.
"""
import os, sys, subprocess, shutil, json, glob, atexit
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
sys.stderr.reconfigure(encoding='utf-8', line_buffering=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ == '__main__':
    try:
        from utils.config import load_config, get_data_file
    except Exception as e:
        print(f'Import error: {e}', flush=True)
        sys.exit(1)

ffmpeg_path = shutil.which('ffmpeg')
if not ffmpeg_path:
    print('ffmpeg not found')
    sys.exit(1)

try:
    config = load_config()
except Exception as e:
    print(f'load_config error: {e}', flush=True)
    sys.exit(1)

library_path = config.get('library_path', '')
if not library_path:
    print('library_path not configured')
    sys.exit(1)

lock = threading.Lock()
_save_callbacks = []

def _atexit_save():
    for cb in _save_callbacks:
        try: cb()
        except: pass
atexit.register(_atexit_save)

def measure_one(path, library_path, cache_dict):
    rel_path = os.path.relpath(path, library_path)
    cmd = [ffmpeg_path, '-i', path,
           '-af', 'loudnorm=print_format=json',
           '-f', 'null', 'NUL', '-hide_banner', '-y']
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=120,
                           encoding='utf-8', errors='replace')
        out = r.stderr
        json_start = out.rfind('{')
        if json_start >= 0:
            try:
                data, _ = json.JSONDecoder().raw_decode(out[json_start:])
                input_i = data.get('input_i')
                if input_i is not None:
                    with lock:
                        cache_dict[rel_path] = float(input_i)
                    return True
            except:
                pass
        else:
            pass
    except:
        pass
    return False

def process_format(fmt):
    from utils.config import get_data_file
    cache_file = get_data_file(f'{fmt}_lufs_cache.json')
    data_dir = os.path.dirname(cache_file)
    os.makedirs(data_dir, exist_ok=True)
    cache_file = os.path.join(data_dir, f'{fmt}_lufs_cache.json')

    cache = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache = json.load(f)
        except:
            cache = {}

    all_files = glob.glob(os.path.join(library_path, '**', f'*.{fmt}'), recursive=True)
    to_measure = [f for f in all_files if f not in cache]
    print(f'[{fmt.upper()}] {len(all_files)} files, {len(cache)} cached, {len(to_measure)} to measure')

    if not to_measure:
        return

    done = 0
    total = len(to_measure)

    def save_cache():
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())

    _save_callbacks.append(save_cache)

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(measure_one, f, library_path, cache): f for f in to_measure}
        for fut in as_completed(futures):
            done += 1
            if done % 25 == 0 or done == total:
                print(f'\r[{fmt.upper()}] {done}/{total} ({done/total*100:.0f}%)', end='', flush=True)
            if done % 25 == 0:
                save_cache()

    print()
    save_cache()
    print(f'[{fmt.upper()}] Saved {len(cache)} measurements to {cache_file}')

# Run both formats in parallel
with ThreadPoolExecutor(max_workers=2) as pool:
    f1 = pool.submit(process_format, 'm4a')
    f2 = pool.submit(process_format, 'mp3')
    f1.result()
    f2.result()

print('All done')
