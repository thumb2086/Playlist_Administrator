"""Probe: would the NATIVE matcher recover tracks Spotube failed on?

Samples missing tracks from PIP-processed playlists (Daily Mix / Release
Radar / hits / Kpop 2026), runs the same ytsearch6 + rank_yt_videos stage
the native downloader uses, and reports the predicted outcome.
"""
import glob
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import yt_dlp

from core.downloader import rank_yt_videos

SEARCH_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'skip_download': True,
    'extract_flat': True,
    'socket_timeout': 60,
    'retries': 2,
    'ignoreerrors': True,
}


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\CPXru\Music\Spotube'
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')

    sn = json.load(open(os.path.join(base, 'original_snapshot.json'), encoding='utf-8'))
    mp3_by_stem = {os.path.splitext(os.path.basename(f))[0]
                   for f in glob.glob(os.path.join(base, 'mp3', '*.mp3'))}
    processed = {os.path.splitext(os.path.basename(f))[0]
                 for f in glob.glob(os.path.join(base, 'Playlists', '*.m3u8'))}

    missing = []
    for name, tracks in sn['playlists'].items():
        if name not in processed:
            continue  # only playlists PIP actually ran = real Spotube failures
        for t in tracks:
            if t not in mp3_by_stem:
                missing.append(t)

    random.seed(20260813)
    sample = random.sample(missing, min(n, len(missing)))
    report = os.path.join(base, 'native_probe_report.txt')
    lines = ['spotube_FAILED tracks: %d, sampled: %d' % (len(missing), len(sample))]
    ok = low = denied = err = 0
    for song in sample:
        title, artist = song, ''
        if ' - ' in song:
            t, a = song.rsplit(' - ', 1)
            if len(t.strip()) and len(a.strip()):
                title, artist = t.strip(), a.strip()
        try:
            with yt_dlp.YoutubeDL(SEARCH_OPTS) as sdl:
                info = sdl.extract_info('ytsearch6:%s' % song, download=False)
            entries = (info or {}).get('entries') or []
            best, score = rank_yt_videos(entries, title, artist)
            picked = (best or {}).get('title', '')[:60] if best else '(none)'
            if score >= 3:
                verdict, ok = '下載成功(預測)', ok + 1
            elif score >= 2:
                verdict, low = '低信心仍會嘗試', low + 1
            elif score == 0:
                verdict, denied = '拒載(0分)', denied + 1
            else:
                verdict, low = '低信心仍會嘗試', low + 1
            lines.append('[%s] %s | score=%d | %s' % (verdict, song, score, picked))
        except Exception as e:
            err += 1
            lines.append('[錯誤] %s | %s' % (song, str(e)[:80]))

    lines.append('SUMMARY: ok=%d low=%d denied=%d error=%d' % (ok, low, denied, err))
    with open(report, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('spotube-failed total: %d' % len(missing))
    print('SUMMARY: ok(>=3)=%d low(>=2)=%d denied(<2)=%d error=%d' % (ok, low, denied, err))
    print('report:', report)


if __name__ == '__main__':
    main()