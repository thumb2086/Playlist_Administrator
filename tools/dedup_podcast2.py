import os
import re
import sys
from collections import defaultdict

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

podcast_dir = os.path.expanduser(r'~\Music\Spotube\podcast_downloads')

# 1. Normalize separators: 3+ spaces → " - ", 2 spaces → " "
def normalize_sep(name):
    name = re.sub(r'  +', ' - ', name)
    name = re.sub(r'\s*-\s*', ' - ', name)
    name = name.rstrip(' -')
    return name

# 2. Build normalized index of all files
groups = defaultdict(list)  # norm_key → [(orig_path, size, stem)]

for root, dirs, files in os.walk(podcast_dir):
    for fname in files:
        if not fname.lower().endswith(('.mp3', '.txt', '.m4a', '.wav', '.flac')):
            continue
        stem, ext = os.path.splitext(fname)
        # Remove [xxxxx] YouTube IDs
        stem_clean = re.sub(r'\s*\[[\w-]{11}\]', '', stem)
        # Normalize separators
        stem_norm = normalize_sep(stem_clean)
        # Extract EP number
        ep_match = re.search(r'EP(\d+)', stem_norm)
        ep_num = ep_match.group(1).zfill(3) if ep_match else stem_norm
        # Key = EP number if found, else normalized stem lower
        key = ep_num
        path = os.path.join(root, fname)
        groups[key].append((path, os.path.getsize(path), stem_norm, ext))

# 3. Dedup within each EP group
renamed = 0
deleted = 0
for ep_num, entries in sorted(groups.items(), key=lambda x: x[0]):
    if len(entries) < 2:
        # Single entry: still normalize its name if needed
        path, size, stem_norm, ext = entries[0]
        new_name = f'{stem_norm}{ext}'
        new_path = os.path.join(os.path.dirname(path), new_name)
        if path != new_path and not os.path.exists(new_path):
            os.rename(path, new_path)
            print(f'  {os.path.basename(path)}')
            print(f'→ {new_name}')
            renamed += 1
        continue

    # Multiple entries: keep the longest stem, delete others
    entries.sort(key=lambda x: -len(x[2]))  # longest stem first
    keep_path, keep_size, keep_stem, keep_ext = entries[0]
    new_keep_name = f'{keep_stem}{keep_ext}'
    new_keep_path = os.path.join(os.path.dirname(keep_path), new_keep_name)

    for dup_path, dup_size, dup_stem, dup_ext in entries[1:]:
        # If same size and one is substring of other, delete shorter
        if dup_stem in keep_stem or keep_stem in dup_stem:
            os.remove(dup_path)
            print(f'  DELETE {os.path.basename(dup_path)}')
            deleted += 1
        elif dup_size == keep_size:
            os.remove(dup_path)
            print(f'  DELETE (same size) {os.path.basename(dup_path)}')
            deleted += 1

    # Rename survivor if needed
    if keep_path != new_keep_path and not os.path.exists(new_keep_path):
        os.rename(keep_path, new_keep_path)
        print(f'  RENAME {os.path.basename(keep_path)}')
        print(f'       → {new_keep_name}')
        renamed += 1

print(f'\n✅ {renamed} 個重新命名, {deleted} 個刪除')
