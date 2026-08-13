"""Native matcher vs Spotube picks on the ORIGINAL Spotify playlists.

Part A: coverage of the native matcher (core.library.find_song_in_library)
Part B: for tracks both matchers resolved, audit the two picked files'
        audio content, ID3 metadata and embedded cover, with the m4a
        (Spotube's actual download) as ground truth.
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from mutagen import File as MFile
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3

from core.library import build_metadata_index, find_song_in_library

EXT_AUDIO = ('.mp3', '.m4a', '.flac')


def audit(path):
    """(duration, bitrate, title, artist, album, cover_bytes)"""
    dur = br = None
    title = artist = album = None
    cover = 0
    try:
        m = MFile(path)
        if m and m.info:
            dur = m.info.length
            br = m.info.bitrate
    except Exception:
        pass
    try:
        if path.lower().endswith('.mp3'):
            t = EasyID3(path)
            title = t.get('title', [None])[0]
            artist = t.get('artist', [None])[0]
            album = t.get('album', [None])[0]
            try:
                apic = ID3(path)
                for key in apic:
                    if key.startswith('APIC'):
                        cover = len(apic[key].data)
                        break
            except Exception:
                pass
        elif path.lower().endswith('.m4a'):
            from mutagen.mp4 import MP4
            t = MP4(path)
            title = t.get('\xa9nam', [None])[0]
            artist = t.get('\xa9ART', [None])[0]
            album = t.get('\xa9alb', [None])[0]
            cover = len(bytes(t['covr'][0])) if t.get('covr') else 0
    except Exception:
        pass
    return dur, br, title, artist, album, cover


def short(s, n=22):
    s = s or ''
    return s if len(s) <= n else s[:n - 1] + '…'


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\CPXru\Music\Spotube'
    sn = json.load(open(os.path.join(base, 'original_snapshot.json'), encoding='utf-8'))
    playlists = sn.get('playlists', {})

    mp3_files = glob.glob(os.path.join(base, 'mp3', '*.mp3'))
    mp3_by_stem = {os.path.splitext(os.path.basename(f))[0]: f for f in mp3_files}
    m4a_by_stem = {os.path.splitext(os.path.basename(f))[0]: f
                   for f in glob.glob(os.path.join(base, 'm4a', '*.m4a'))}
    print('building metadata index (%d mp3)...' % len(mp3_files), flush=True)
    meta_index = build_metadata_index(mp3_files)

    report = os.path.join(base, 'native_vs_spotube_report.txt')
    lines = []
    out = lines.append

    out('== native matcher vs Spotube — original playlists ==')
    out('library mp3: %d' % len(mp3_files))

    rows = ['playlist | original | native_found | coverage %']
    total_orig = total_found = 0
    audits = []
    not_found = []

    for name, tracks in playlists.items():
        found = 0
        for t in tracks:
            spotube_mp3 = mp3_by_stem.get(t)
            if not find_song_in_library(t, mp3_files, metadata_index=meta_index):
                not_found.append((name, t))
                continue
            found += 1
            native_mp3 = find_song_in_library(t, mp3_files, metadata_index=meta_index)
            if spotube_mp3 and native_mp3 and os.path.normpath(spotube_mp3) != os.path.normpath(native_mp3):
                audits.append((name, t, spotube_mp3, native_mp3))
        total_orig += len(tracks)
        total_found += found
        pct = found * 100 / len(tracks) if tracks else 0
        rows.append('%s | %d | %d | %.1f%%' % (name, len(tracks), found, pct))

    rows.append('TOTAL | %d | %d | %.1f%%' % (
        total_orig, total_found, total_found * 100.0 / total_orig if total_orig else 0))
    out('\n'.join(rows))

    out('\n== Part B: picks differ (native != spotube file) ==')
    out('total audit cases: %d' % len(audits))
    out('track | spotube-dur | native-dur | m4a-dur(truth) | utf | SP:title/artist | NS:title/artist | cover SP/NAT')
    closer_n = closer_s = 0
    for name, t, sp, nat in audits:
        truth = m4a_by_stem.get(t)
        sd, sb, st, sa, sal, sc = audit(sp)
        nd, nb, nt, na, nal, nc = audit(nat)
        td = None
        if truth:
            td = MFile(truth).info.length if MFile(truth) and MFile(truth).info else None
        tag = ''
        if sd and nd and td:
            if abs(sd - td) < abs(nd - td):
                closer_s += 1
                tag = 'S'
            else:
                closer_n += 1
                tag = 'N'
        out('%s | %.0f | %.0f | %s | %s | %s/%s | %s/%s | %d/%d' % (
            short(t, 26), sd or -1, nd or -1,
            ('%.0f' % td) if td else '-',
            tag,
            short(st), short(sa), short(nt), short(na), sc, nc))

    out('\ncloser to m4a truth: spotube=%d native=%d' % (closer_s, closer_n))

    out('\n== original tracks native did NOT find (%d) ==' % len(not_found))
    for name, t in not_found[:60]:
        out('  [%s] %s' % (short(name, 18), t))

    with open(report, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('TOTAL coverage: %d/%d (%.1f%%)' % (
        total_found, total_orig, total_found * 100.0 / total_orig if total_orig else 0))
    print('differ-picks audited: %d (closer: spotube=%d native=%d)' % (
        len(audits), closer_s, closer_n))
    print('not found by native: %d' % len(not_found))
    print('report:', report)


if __name__ == '__main__':
    main()