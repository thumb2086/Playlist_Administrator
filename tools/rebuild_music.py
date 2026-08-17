"""FULL REBUILD of the music library: clears music\\ and re-downloads every
track from the Spotify snapshot as mp3 VBR 0 (yt-dlp native). Podcasts and
playlist m3u8 are NOT touched here (pipeline re-scrapes later).

Usage: python tools/rebuild_music.py [base] [music_dir]
Checkpointed: re-running skips already-downloaded files.
"""
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.downloader import download_song
from utils import config as uconfig

BASE = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\CPXru\Music\playlist-admin'
MUSIC_DIR = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, 'music')
SNAPSHOT = os.path.join(BASE, 'cache', 'spotify', 'original_snapshot.json')

uconfig.CONFIG_DIR = BASE
uconfig.CONFIG_FILE = os.path.join(BASE, 'config.json')

LIMIT = int(os.environ.get('REBUILD_LIMIT', '0'))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def main():
    # 1. Clear the music dir (full rebuild).
    print('== FULL MUSIC REBUILD ==', flush=True)
    if os.path.isdir(MUSIC_DIR):
        n = len([f for f in os.listdir(MUSIC_DIR) if f.lower().endswith('.mp3')])
        print(f'clearing {n} existing files from {MUSIC_DIR}', flush=True)
        for f in os.listdir(MUSIC_DIR):
            p = os.path.join(MUSIC_DIR, f)
            try:
                if os.path.isfile(p):
                    os.remove(p)
                else:
                    shutil.rmtree(p)
            except Exception as e:
                print(f'  skip {f}: {e}', flush=True)
    os.makedirs(MUSIC_DIR, exist_ok=True)

    config = json.load(open(os.path.join(BASE, 'config.json'), encoding='utf-8'))
    config['library_path'] = MUSIC_DIR
    config['lyrics_path'] = os.path.join(MUSIC_DIR, 'Lyrics')

    sn = json.load(open(SNAPSHOT, encoding='utf-8'))
    tasks = []
    for playlist, tracks in sn['playlists'].items():
        for t in tracks:
            if t not in tasks:
                tasks.append(t)
    if LIMIT:
        tasks = tasks[:LIMIT]
    print(f'total tracks to download: {len(tasks)}', flush=True)

    # Checkpoint: resume from already-downloaded files.
    existing = {os.path.splitext(f)[0].lower()
                for f in os.listdir(MUSIC_DIR) if f.lower().endswith('.mp3')}

    ok = fail = skip = 0
    t0 = time.time()
    report = os.path.join(BASE, 'logs', 'music_rebuild_report.txt')
    os.makedirs(os.path.dirname(report), exist_ok=True)
    lines = open(report, 'a', encoding='utf-8')
    lines.write('== music rebuild start ==\n')

    for i, song in enumerate(tasks, 1):
        stem = os.path.splitext(song)[0].lower()
        if stem in existing:
            skip += 1
            continue
        print(f'[{i}/{len(tasks)}] {song}', flush=True)
        try:
            result = download_song(song, MUSIC_DIR, 'mp3',
                                   lambda m: None, file_list=[], config=config)
            if result and os.path.exists(result):
                ok += 1
                lines.write(f'OK\t{song}\n')
            else:
                fail += 1
                lines.write(f'FAIL\t{song}\n')
        except Exception as e:
            fail += 1
            lines.write(f'ERR\t{song}\t{repr(e)[:120]}\n')
        if i % 10 == 0:
            el = time.time() - t0
            rate = i / el * 60 if el > 0 else 0
            print(f'  ... {i}/{len(tasks)} ok={ok} fail={fail} skip={skip} '
                  f'({rate:.1f}/min)', flush=True)
            lines.flush()

    el = time.time() - t0
    print(f'== DONE ok={ok} fail={fail} skip={skip} in {el/60:.1f} min ==', flush=True)
    lines.write(f'== done ok={ok} fail={fail} skip={skip} ==\n')
    lines.close()


if __name__ == '__main__':
    main()