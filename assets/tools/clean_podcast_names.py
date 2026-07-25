import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

podcast_dir = os.path.expanduser(r'~\Music\Spotube\podcast_downloads')

if not os.path.exists(podcast_dir):
    print(f'目錄不存在: {podcast_dir}')
    exit(1)

count = 0
for root, dirs, files in os.walk(podcast_dir):
    for fname in files:
        name, ext = os.path.splitext(fname)
        # Remove [xxxxx] (YouTube ID) patterns
        new_name = re.sub(r'\s*\[[\w-]{11}\]', '', name)
        # Also remove trailing spaces/dashes
        new_name = new_name.rstrip(' -')
        if new_name == name:
            continue
        src = os.path.join(root, fname)
        dst = os.path.join(root, f'{new_name}{ext}')
        # Avoid overwriting existing files
        if os.path.exists(dst):
            print(f'⚠️ 跳過（已存在）: {fname}')
            continue
        os.rename(src, dst)
        try:
            print(f'  {fname}')
            print(f'→ {new_name}{ext}')
        except UnicodeEncodeError:
            print(f'  [OK] → {new_name}{ext}')
        count += 1

print(f'\n✅ 處理完成，共修改 {count} 個檔案')
