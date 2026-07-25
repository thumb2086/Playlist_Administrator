import os
import re
import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

podcast_dir = os.path.expanduser(r'~\Music\Spotube\podcast_downloads')

# Fix cases where legit hyphens were turned into " - "
fixed = 0
for root, dirs, files in os.walk(podcast_dir):
    for fname in files:
        name, ext = os.path.splitext(fname)
        # Fix common known patterns
        new_name = name
        new_name = re.sub(r'GPT - (\d)', r'GPT-\1', new_name)
        new_name = re.sub(r'GPT - (\d)\.(\d)', r'GPT-\1.\2', new_name)
        new_name = re.sub(r'(\w) - mini\b', r'\1-mini', new_name)
        new_name = re.sub(r'\bo3 - mini\b', 'o3-mini', new_name)
        new_name = re.sub(r'DeepSeek - V(\d)', r'DeepSeek-V\1', new_name)
        new_name = re.sub(r' -  - ', ' -- ', new_name)
        # General: undo word - number → word-number if both sides are short
        new_name = re.sub(r'\b([A-Za-z]{1,5}) - (\d[\w.]*)\b', r'\1-\2', new_name)
        new_name = new_name.rstrip(' -')
        if new_name != name:
            src = os.path.join(root, fname)
            dst = os.path.join(root, f'{new_name}{ext}')
            if not os.path.exists(dst):
                os.rename(src, dst)
                print(f'  {fname} → {new_name}{ext}')
                fixed += 1

print(f'\n✅ 修正 {fixed} 個')
