"""
Transcribe podcast episodes that don't have SRT or TXT yet.
Uses Groq Whisper API via the existing bridge script.
"""
import subprocess, json, os, sys, time

KEYS_STR = os.environ.get('GROQ_API_KEY', '')
if not KEYS_STR:
    env_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(env_file):
        for line in open(env_file, encoding='utf-8'):
            if line.startswith('GROQ_API_KEY='):
                KEYS_STR = line.strip().split('=', 1)[1]

lib = r'C:\Users\CPXru\Music\Spotube'
pod_dir = os.path.join(lib, 'podcast_downloads', '游庭皓的財經皓角')
cache_file = os.path.join(lib, 'podcast_processed_cache.json')

bridge = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      'tools', 'flutter_download_bridge.py')

cache = {}
if os.path.exists(cache_file):
    with open(cache_file, encoding='utf-8') as f:
        cache = json.load(f)

files = []
for f in sorted(os.listdir(pod_dir)):
    if not f.endswith('.mp3'):
        continue
    base = f.replace('.mp3', '')
    srt = os.path.join(pod_dir, base + '.srt')
    txt = os.path.join(pod_dir, base + '.txt')
    if not os.path.exists(srt) and not os.path.exists(txt):
        files.append(os.path.join(pod_dir, f))

print(f'Need Groq: {len(files)} files')

for i, fp in enumerate(files):
    name = os.path.basename(fp)
    txt_path = fp.replace('.mp3', '.txt')
    print(f'[{i+1}/{len(files)}] {name[:70]}')
    sys.stdout.flush()

    r = subprocess.run(
        ['python', bridge, 'groq-transcribe', fp, KEYS_STR, 'whisper-large-v3', 'zh'],
        capture_output=True, timeout=600, encoding='utf-8', errors='replace')

    text = None
    for line in (r.stdout or '').split('\n'):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            if data.get('type') == 'transcription':
                text = data.get('text', '')
            elif data.get('type') == 'error':
                print(f'  ERROR: {data.get("message", "")[:100]}')
        except json.JSONDecodeError:
            pass

    if text:
        with open(txt_path, 'w', encoding='utf-8') as tf:
            tf.write(text)
        ep_title = name.replace('.mp3', '')
        for ckey in cache:
            if ckey.endswith(ep_title):
                cache[ckey]['txt'] = True
                break
        with open(cache_file, 'w', encoding='utf-8') as cf:
            json.dump(cache, cf, ensure_ascii=False, indent=2)
        print(f'  ✅ ({len(text)} chars)')
    else:
        print(f'  ❌ No transcription')
        err = (r.stderr or '')[:200]
        if err:
            print(f'  stderr: {err}')

    if i < len(files) - 1:
        time.sleep(1)

print('Done')