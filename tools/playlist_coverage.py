"""Playlist coverage audit: original Spotify playlists (snapshot_cache.json)
vs the downloaded mp3 library and the processed m3u8 playlists.

達成率 = 每張原始歌單裡有多少首歌在 mp3 庫中找得到。
"""
import glob
import json
import os
import re
import sys


def norm(s):
    return re.sub(r'[^\w\u4e00-\u9fff]+', '', s or '').lower()


def tokens(s):
    return {tkn.lower() for tkn in re.findall(r'[\w\u4e00-\u9fff]+', s or '')}


def jaccard_matches(name, mp3_map):
    a = tokens(name)
    if not a:
        return False
    ncand = mp3_map.get(norm(name))
    if ncand:
        return True
    # reversed name variant
    if ' - ' in name:
        parts = name.rsplit(' - ', 1)
        if len(parts) == 2:
            rev = parts[1] + ' - ' + parts[0]
            if mp3_map.get(norm(rev)):
                return True
    # token jaccard >= 0.7 on first 400 candidates
    for stem, toks in mp3_map.items():
        b = toks
        if not b:
            continue
        inter = len(a & b)
        if inter / len(a | b) >= 0.7:
            return True
    return False


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\CPXru\Music\Spotube'
    sn = json.load(open(os.path.join(base, 'snapshot_cache.json'), encoding='utf-8'))
    playlists = sn.get('playlists', {})
    mp3_dir = os.path.join(base, 'mp3')
    mp3_stems = {}
    for f in glob.glob(os.path.join(mp3_dir, '*.mp3')):
        stem = os.path.splitext(os.path.basename(f))[0]
        mp3_stems[norm(stem)] = tokens(stem)

    pl_dir = os.path.join(base, 'Playlists')
    processed = {}
    for f in glob.glob(os.path.join(pl_dir, '*.m3u8')):
        name = os.path.splitext(os.path.basename(f))[0]
        try:
            lines = [l.strip() for l in open(f, encoding='utf-8')
                     if l.strip() and not l.startswith('#')]
            processed[name] = [os.path.basename(l).rsplit('.', 1)[0] for l in lines]
        except Exception:
            processed[name] = []

    report = os.path.join(base, 'playlist_coverage_report.txt')
    rows = []
    rows.append('playlist | original | mp3 found | coverage % | processed-m3u8')
    total_orig = 0
    total_found = 0
    details = []
    for name, pl in playlists.items():
        tracks = pl.get('tracks', []) if isinstance(pl, dict) else pl
        found = sum(1 for t in tracks if jaccard_matches(t, mp3_stems))
        total_orig += len(tracks)
        total_found += found
        pct = found * 100 / len(tracks) if tracks else 0
        proc = len(processed.get(name, []))
        rows.append('%s | %d | %d | %.1f%% | %d' % (name, len(tracks), found, pct, proc))
        if found < len(tracks):
            missing = [t for t in tracks if not jaccard_matches(t, mp3_stems)]
            details.append('== %s (缺 %d): %s' % (name, len(missing), '; '.join(missing[:8])))
    rows.append('TOTAL | %d | %d | %.1f%%' % (total_orig, total_found,
                                              total_found * 100.0 / total_orig if total_orig else 0))
    with open(report, 'w', encoding='utf-8') as f:
        f.write('\n'.join(rows + [''] + details))
    print('\n'.join(rows[-1:]))
    print('report:', report)


if __name__ == '__main__':
    main()