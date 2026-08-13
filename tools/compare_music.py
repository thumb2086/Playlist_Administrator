"""Compare the user's downloads: mp3 (pipeline output) vs m4a (Spotube original).

Finds: missing conversions, orphans, duration mismatches (wrong song matched),
tiny/suspicious files, and reports bitrate/size stats.
"""
import glob
import os
import sys

from mutagen import File

PY3 = sys.version_info[:2] >= (3, 8)


def info_of(path):
    try:
        m = File(path)
        if m is None:
            return None, None, None
        return m.info.length, m.info.bitrate, os.path.getsize(path)
    except Exception:
        return None, None, None


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\CPXru\Music\Spotube'
    m4a_dir = os.path.join(root, 'm4a')
    mp3_dir = os.path.join(root, 'mp3')
    report = os.path.join(root, 'music_compare_report.txt')
    lines = []

    def out(msg):
        lines.append(msg)

    if not os.path.isdir(m4a_dir) and not os.path.isdir(mp3_dir):
        print('no m4a/mp3 dirs at', root)
        sys.exit(1)

    def stem(f):
        return os.path.splitext(os.path.basename(f))[0]

    m4a = {stem(f): f for f in glob.glob(os.path.join(m4a_dir, '*.m4a'))}
    mp3 = {stem(f): f for f in glob.glob(os.path.join(mp3_dir, '*.mp3'))}

    out('== music compare report ==')
    out('m4a total: %d, mp3 total: %d' % (len(m4a), len(mp3)))

    both = sorted(set(m4a) & set(mp3))
    only_m4a = sorted(set(m4a) - set(mp3))
    only_mp3 = sorted(set(mp3) - set(m4a))

    out('\n[1] no mp3 conversion (only m4a): %d' % len(only_m4a))
    for s in only_m4a[:30]:
        out('  ' + s)
    if len(only_m4a) > 30:
        out('  ... and %d more' % (len(only_m4a) - 30))

    out('\n[2] mp3 without source m4a (orphan/direct): %d' % len(only_mp3))
    for s in only_mp3[:30]:
        out('  ' + s)
    if len(only_mp3) > 30:
        out('  ... and %d more' % (len(only_mp3) - 30))

    out('\n[3] duration mismatch (>3s) between m4a and mp3:')
    mismatch = []
    bad_dur = 0
    for s in both:
        l1, _, _ = info_of(m4a[s])
        l2, _, _ = info_of(mp3[s])
        if l1 and l2 and abs(l1 - l2) > 3.0:
            mismatch.append((s, l1, l2))
    for s, l1, l2 in mismatch[:40]:
        out('  %s: m4a=%.0fs mp3=%.0fs' % (s, l1, l2))
    if not mismatch:
        out('  none')
    out('  (mismatched: %d)' % len(mismatch))

    out('\n[4] suspicious mp3 (tiny / very short):')
    tiny = 0
    for s in both:
        l, br, size = info_of(mp3[s])
        if size is None:
            continue
        if size < 100 * 1024 or (l and l < 30):
            out('  %s: size=%.0fKB dur=%.0fs' % (s, size / 1024, l or 0))
            tiny += 1
    if not tiny:
        out('  none')
    out('  (suspicious: %d)' % tiny)

    out('\n[5] format stats (both):')
    brs = []
    bits = 0
    for s in both:
        _, br, _ = info_of(mp3[s])
        if br:
            brs.append(br)
    out('  mp3 avg bitrate: %.0f kbps (n=%d)' % (sum(brs) / 8000 / len(brs) if brs else 0, len(brs)))
    for s in both:
        _, br, _ = info_of(m4a[s])
        if br:
            brs.append(br)
    out('  combined bitrate sample logged')

    with open(report, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('report written:', report)
    print('summary: both=%d only_m4a=%d only_mp3=%d dur_mismatch=%d tiny=%d' % (
        len(both), len(only_m4a), len(only_mp3), len(mismatch), tiny))


if __name__ == '__main__':
    main()