"""Batch native (yt-dlp) download of ALL original-playlist tracks missing
from the library, into a SEPARATE folder (native\\), then compute the real
match rate. Checkpointed: re-running skips already-downloaded files.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.downloader import download_song
from utils import config as uconfig

BASE = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\CPXru\Music\Spotube'
NATIVE_DIR = sys.argv[2] if len(sys.argv) > 2 else os.path.join(BASE, 'native')

# Point the data dir at the library root so spotify_cache metadata is found.
uconfig.CONFIG_DIR = BASE
uconfig.CONFIG_FILE = os.path.join(BASE, 'config.json')

LIMIT = int(os.environ.get('NATIVE_LIMIT', '0'))  # 0 = unlimited (or set for testing)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')


def main():
    os.makedirs(NATIVE_DIR, exist_ok=True)
    config = json.load(open(os.path.join(BASE, 'config.json'), encoding='utf-8'))
    config['library_path'] = NATIVE_DIR
    config['lyrics_path'] = os.path.join(NATIVE_DIR, 'Lyrics')

    sn = json.load(open(os.path.join(BASE, 'original_snapshot.json'), encoding='utf-8'))
    mp3_stems = set()
    if os.path.isdir(os.path.join(BASE, 'mp3')):
        mp3_stems = {os.path.splitext(f)[0]
                     for f in os.listdir(os.path.join(BASE, 'mp3'))}

    tasks = []
    for playlist, tracks in sn['playlists'].items():
        for t in tracks:
            if t not in tasks and t not in mp3_stems:
                tasks.append(t)
    if LIMIT:
        tasks = tasks[:LIMIT]

    report = os.path.join(BASE, 'native_download_report.txt')
    lines = open(report, 'a', encoding='utf-8') if os.path.exists(report) else open(report, 'w', encoding='utf-8')
    lines.write('== native batch start ==\n')

    results = {'ok': 0, 'fail': 0, 'skip': 0}
    total = len(tasks)
    for i, song in enumerate(tasks, 1):
        out_path = os.path.join(NATIVE_DIR, f'{song}.mp3')
        if os.path.exists(out_path) and os.path.getsize(out_path) > 20000:
            results['skip'] += 1
            print(f'[{i}/{total}] skip  {song}', flush=True)
            continue

        logs = []

        def log_func(msg):
            logs.append(str(msg))

        try:
            path = download_song(song, NATIVE_DIR, 'mp3', log_func,
                                 file_list=[], config=config)
            if path and os.path.exists(path):
                results['ok'] += 1
                lines.write(f'OK  {song}\n')
                lines.flush()
                print(f'[{i}/{total}] OK    {song}', flush=True)
            else:
                results['fail'] += 1
                tail = ' | '.join(logs[-3:])[-200:]
                lines.write(f'FAIL {song} :: {tail}\n')
                lines.flush()
                print(f'[{i}/{total}] FAIL  {song} :: {tail}', flush=True)
        except Exception as e:
            results['fail'] += 1
            lines.write(f'ERROR {song} :: {e}\n')
            lines.flush()
            print(f'[{i}/{total}] ERROR {song} :: {e}', flush=True)

    lines.write('== done: %s ==\n' % results)
    lines.close()
    print('BATCH DONE: %s' % results, flush=True)


if __name__ == '__main__':
    main()