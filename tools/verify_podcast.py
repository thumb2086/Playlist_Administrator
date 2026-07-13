import os, re, sys
from collections import defaultdict

if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')

d = os.path.expanduser(r'~\Music\Spotube\podcast_downloads')

for name in sorted(os.listdir(d)):
    p = os.path.join(d, name)
    if not os.path.isdir(p): continue
    files = [f for f in os.listdir(p) if f.endswith('.mp3')]
    if not files: continue
    print(f'\n=== {name} ({len(files)} files) ===')

    # Group by EP number
    eps = defaultdict(list)
    others = []
    for f in sorted(files):
        m = re.search(r'EP(\d+)', f)
        if m:
            eps[int(m.group(1))].append(f)
        else:
            others.append(f)

    # Check for gaps in EP sequence
    if eps:
        nums = sorted(eps.keys())
        expected = list(range(nums[0], nums[-1] + 1))
        missing = sorted(set(expected) - set(nums))
        if missing:
            print(f'  ⚠️ 缺少集數: {missing}')

    # Check for duplicates (multiple files with same EP)
    if eps:
        dupes = {k: v for k, v in eps.items() if len(v) > 1}
        if dupes:
            print(f'  ❌ 重複 EP:')
            for ep, fs in sorted(dupes.items()):
                for f in fs:
                    print(f'      EP{ep:03d} → {f}')
        else:
            print(f'  ✅ EP{min(eps.keys()):03d}~EP{max(eps.keys()):03d} 均無重複')

    if others:
        print(f'  其他: {len(others)} 集')
        for f in others:
            print(f'      {f}')

print('\n✅ 檢查完成')
