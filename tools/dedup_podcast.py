import os
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

podcast_dir = os.path.expanduser(r'~\Music\Spotube\podcast_downloads')

FIX = {
    '\uff5c': '_',  # 全形｜ → _
    '\uff08': '(',  # （ → (
    '\uff09': ')',  # ） → )
    '\uff0f': '_',  # ／ → _
    '\u4e28': '_',  # ∣ → _
}

seen = {}
renamed = 0
removed = 0

for root, dirs, files in os.walk(podcast_dir):
    for fname in files:
        name, ext = os.path.splitext(fname)
        new_name = name
        for k, v in FIX.items():
            new_name = new_name.replace(k, v)
        new_name = new_name.replace('<', '(').replace('>', ')')
        new_name = new_name.rstrip(' -')
        src = os.path.join(root, fname)
        dst = os.path.join(root, f'{new_name}{ext}')

        if new_name != name:
            if os.path.exists(dst):
                if os.path.getsize(src) == os.path.getsize(dst):
                    os.remove(src)
                    print(f'  DEL {fname}')
                    removed += 1
                else:
                    os.remove(src)
                    print(f'  DEL (dup) {fname}')
                    removed += 1
            else:
                os.rename(src, dst)
                print(f'  {fname}')
                print(f'→ {new_name}{ext}')
                renamed += 1
        else:
            # Check for case/normalized duplicates
            key = new_name.lower()
            if key in seen:
                keep = seen[key]
                if os.path.getsize(src) == os.path.getsize(keep):
                    os.remove(src)
                    print(f'  DEL dup {fname}')
                    removed += 1
                else:
                    os.remove(src)
                    print(f'  DEL dup (diff size) {fname}')
                    removed += 1
            else:
                seen[key] = src

print(f'\n✅ 重新命名 {renamed} 個，刪除 {removed} 個重複')
