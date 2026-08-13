"""Embed album covers into MP3s missing APIC.

Sources, in order:
1. Same-stem M4A file in the m4a folder (Spotube downloads carry covr).
2. iTunes Search API (title + artist from the filename).
"""
import glob
import json
import os
import re
import sys
import urllib.parse
import urllib.request

from mutagen.id3 import APIC, ID3
from mutagen.mp4 import MP4


def stem_of(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def covr_from_m4a(m4a_dir: str, stem: str):
    p = os.path.join(m4a_dir, stem + '.m4a')
    if not os.path.exists(p):
        return None
    try:
        tag = MP4(p)
        if 'covr' in tag and tag['covr']:
            return bytes(tag['covr'][0])
    except Exception:
        pass
    return None


def itunes_cover(stem: str):
    parts = [s.strip() for s in stem.split(' - ')]
    title = parts[0]
    artist = ' - '.join(parts[1:]) if len(parts) > 1 else ''
    if not title:
        return None
    term = f'{title} {artist}'.strip()
    url = ('https://itunes.apple.com/search?term='
           + urllib.parse.quote(term) + '&entity=song&limit=10')
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read().decode('utf-8'))
    except Exception:
        return None
    results = data.get('results') or []
    if not results:
        return None
    q = {t.lower() for t in re.findall(r'[\w\u4e00-\u9fff]+', title)}
    best_url = None
    best_score = 0.0
    for row in results:
        tname = (row.get('trackName') or '').lower()
        aname = (row.get('artistName') or '').lower()
        score = 0.0
        if q:
            hit = sum(1 for tok in q if tok in tname)
            score = hit / len(q)
        al = artist.lower()
        if al and (al == aname or al in aname or aname in al):
            score += 0.3
        u = row.get('artworkUrl100') or ''
        if u and score > best_score:
            best_score = score
            best_url = u.replace('100x100bb', '600x600bb')
    if best_score < 0.4 or not best_url:
        return None
    try:
        with urllib.request.urlopen(best_url, timeout=20) as r:
            data = r.read()
        return data if data else None
    except Exception:
        return None


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\CPXru\Music\Spotube'
    mp3_dir = os.path.join(root, 'mp3')
    m4a_dir = os.path.join(root, 'm4a')
    if not os.path.isdir(mp3_dir):
        print(f'mp3 dir not found: {mp3_dir}')
        sys.exit(1)

    fixed = 0
    already = 0
    failed = []
    files = glob.glob(os.path.join(mp3_dir, '*.mp3'))
    for f in files:
        stem = stem_of(f)
        try:
            tag = ID3(f)
        except Exception:
            tag = ID3()
        if any(k.startswith('APIC') for k in tag.keys()):
            already += 1
            continue
        data = covr_from_m4a(m4a_dir, stem) or itunes_cover(stem)
        if not data:
            failed.append(os.path.basename(f))
            continue
        try:
            tag.add(APIC(encoding=3, mime='image/jpeg', type=3, data=data))
            tag.save(f)
            fixed += 1
        except Exception as e:
            failed.append(os.path.basename(f))
    report = os.path.join(root, 'covers_embed_report.txt')
    with open(report, 'w', encoding='utf-8') as rp:
        rp.write('embedded=%d already=%d failed=%d total=%d\n' % (fixed, already, len(failed), len(files)))
        for f in failed:
            rp.write('no cover: %s\n' % f)
    print('embedded=%d already=%d failed=%d total=%d' % (fixed, already, len(failed), len(files)))
    print('report:', report)


if __name__ == '__main__':
    main()
