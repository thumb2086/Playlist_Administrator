import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

podcast_dir = os.path.expanduser(r'~\Music\Spotube\podcast_downloads')

deleted = 0
renamed = 0

# Collect all files by EP number
eps = {}
all_files = []
for root, dirs, files in os.walk(podcast_dir):
    for fname in files:
        if not fname.lower().endswith('.mp3'):
            continue
        path = os.path.join(root, fname)
        size = os.path.getsize(path)
        m = re.search(r'EP(\d+)', fname)
        ep = m.group(1) if m else None
        all_files.append((ep, path, size, fname))

# Group by EP number, handle dupes
by_ep = {}
for ep, path, size, fname in all_files:
    if ep is None:
        continue
    by_ep.setdefault(ep, []).append((path, size, fname))

for ep, entries in sorted(by_ep.items()):
    if len(entries) < 2:
        continue

    # Sort: prefer files WITHOUT fullwidth brackets () 【】, prefer longer names
    def score(e):
        fname = e[2]
        s = len(fname)
        if '（' in fname or '）' in fname: s -= 100
        if '【' in fname or '】' in fname: s -= 100
        # Simpler title = higher score if same EP
        return s

    entries.sort(key=score, reverse=True)
    keep = entries[0]

    for dup_path, dup_size, dup_name in entries[1:]:
        # If same size or one is substring of other, or fullwidth vs halfwidth difference
        try:
            os.remove(dup_path)
            print(f'  DELETE {dup_name}')
            deleted += 1
        except:
            pass

# Normalize any remaining fullwidth brackets to halfwidth
for root, dirs, files in os.walk(podcast_dir):
    for fname in files:
        name, ext = os.path.splitext(fname)
        new_name = name.replace('（', '(').replace('）', ')').replace('【', '[').replace('】', ']')
        new_name = new_name.replace('\u300a', '').replace('\u300b', '')
        new_name = re.sub(r'\s*\[\s*', ' [', new_name)
        new_name = re.sub(r'\s*\]\s*', '] ', new_name).strip()
        new_name = re.sub(r'\s{2,}', ' ', new_name)
        new_name = new_name.rstrip(' -')
        if new_name != name:
            src = os.path.join(root, fname)
            dst = os.path.join(root, f'{new_name}{ext}')
            if not os.path.exists(dst):
                os.rename(src, dst)
                print(f'  {fname}')
                print(f'→ {new_name}{ext}')
                renamed += 1

print(f'\n✅ 刪除 {deleted} 個重複, 重新命名 {renamed} 個')
