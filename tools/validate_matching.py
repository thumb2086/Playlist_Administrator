"""
驗證歌曲匹配演算法的正確度。

資料來源（真實資料）：
- Playlists/*.m3u8  — Spotify 歌單導出，每行 #EXTINF 的 display + 指向 mp3 的相對路徑
  （路徑即「當時匹配到的正確檔案」= ground truth）
- 音樂庫 mp3 目錄 — 候選檔案

演算法比較：
  A. 現行全鏈路  — find_song_simple_match → find_song_exact_format → find_song_in_library
  B. difflib     — SequenceMatcher ratio 取最高分（完整字串）
  C. Spotube 式  — title/artist token 包含度加分（+3/+1），分數相同再比 ratio
  D. TokenRatio  — 查詢 token 覆蓋率 >= 門檻取最高

指標：
  hit@1     — 猜中正確檔案（top-1）
  miss      — 有正確檔案但猜錯
  correct   — 正確拒絕（檔案不存在且回 None）
  false_pos — 檔案不存在卻回傳某檔案
使用： python tools/validate_matching.py [--limit N] [--seed S] [--algo A,B,...]
"""
import os, re, sys, argparse, random
from difflib import SequenceMatcher

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))

from core.library import (
    LibraryIndexCache, build_library_index, build_metadata_index,
    find_song_simple_match, find_song_exact_format, find_song_in_library,
    get_normalized_tokens,
)

MUSIC_DIR = r'C:\Users\CPXru\Music\Spotube'
PLAYLISTS_DIR = os.path.join(MUSIC_DIR, 'Playlists')
MP3_DIR = os.path.join(MUSIC_DIR, 'mp3')


def load_tracks():
    """讀取所有 m3u8，回傳 [(display, title, artist, truth_path)]"""
    tracks = []
    for fn in sorted(os.listdir(PLAYLISTS_DIR)):
        if not fn.endswith('.m3u8'):
            continue
        with open(os.path.join(PLAYLISTS_DIR, fn), encoding='utf-8') as f:
            display = None
            for line in f:
                line = line.strip()
                if line.startswith('#EXTINF'):
                    display = line.split(',', 1)[1].strip() if ',' in line else ''
                elif not line.startswith('#') and line and display is not None:
                    rel = line.replace('\\', '/')
                    tracks.append((fn, display, rel))
                    display = None
    return tracks


def parse_title_artist(display):
    """'Title - Artist' 取最後一個 ' - ' 分段為 artist。"""
    if ' - ' not in display:
        return display.strip(), ''
    title, artist = display.rsplit(' - ', 1)
    return title.strip(), artist.strip()


def normalized_stem_tokens(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return tuple(get_normalized_tokens(stem))


def build_lib_indices(log=lambda m: None):
    return LibraryIndexCache.get_index(MUSIC_DIR, log)


# ---------- 演算法 C：Spotube 式加分 ----------
OFFICIAL_RE = re.compile(r'official\s(video|audio|music\svideo|lyric\svideo|visualizer)', re.I)

def spotube_style(query, title_tokens, artist_tokens, stems):
    """title token 全包含 +3，artist token 全包含 +1，official +1；tie-break 用 basename ratio。"""
    best = None
    best_score = (-1, -1.0)
    title_set = set(title_tokens)
    artist_set = set(artist_tokens)
    for base, full, toks in stems:
        score = 0
        if title_set and title_set.issubset(set(toks)):
            score += 3
        if artist_set and artist_set.issubset(set(toks)):
            score += 1
        if score == 0:
            continue
        if OFFICIAL_RE.search(query.lower()):
            score += 1
        ratio = SequenceMatcher(None, query.lower(), base.lower()).ratio()
        if (score, ratio) > best_score:
            best_score = (score, ratio)
            best = full
    if best is None or best_score[0] < 3:
        return None
    return best


# ---------- 演算法 B：difflib ----------
def difflib_best(query, stems, threshold=0.62):
    best, best_ratio = None, 0.0
    for base, full, toks in stems:
        r = SequenceMatcher(None, query.lower(), base.lower()).ratio()
        if r > best_ratio:
            best, best_ratio = full, r
    return best if best_ratio >= threshold else None


# ---------- 演算法 D：TokenRatio ----------
def token_ratio_best(query_tokens, stems, threshold=0.8):
    qset = set(query_tokens)
    if not qset:
        return None
    best, best_r = None, 0.0
    for base, full, toks in stems:
        overlap = len(qset & set(toks))
        r = overlap / len(qset)
        if r > best_r:
            best, best_r = full, r
    return best if best_r >= threshold else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=300, help='每支歌單抽樣上限（大資料 difflib 會慢）')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--algo', default='A,B,C,D', help='要執行的演算法，逗號分隔')
    ap.add_argument('--decoy', type=int, default=3,
                    help='每個查詢插入 N 個干擾檔名（同名變體版），考驗抗干擾（B/C/D 適用）')
    args = ap.parse_args()

    random.seed(args.seed)
    algos = [a.strip().upper() for a in args.algo.split(',')]

    log = lambda m: None
    lib_index = build_lib_indices(log)

    all_paths = sorted({p for paths in lib_index.values()
                        for p in (paths if isinstance(paths, list) else [paths])
                        if p.lower().endswith('.mp3')})
    stems = [(os.path.basename(p), p, normalized_stem_tokens(p)) for p in all_paths]
    print(f'音樂庫: {len(all_paths)} 個 mp3')

    mp3_dir_abs = os.path.abspath(MP3_DIR)
    tracks = load_tracks()
    print(f'歌單曲目: {len(tracks)} 筆（去重前）')

    # 抽樣：每支歌單至多 limit 筆，取前 limit（保持歌單順序）
    by_playlist = {}
    for fn, display, rel in tracks:
        by_playlist.setdefault(fn, []).append((display, rel))
    sample = []
    for fn, items in by_playlist.items():
        sample.extend(items[:args.limit])
    random.shuffle(sample)
    print(f'抽樣: {len(sample)} 筆\n')

    # 準備 metadata index（現行全鏈路需要）
    mp3_index = build_library_index(all_paths)
    metadata_index = build_metadata_index(all_paths)

    DECOY_SUFFIXES = ['(Remix)', '(Live)', '(Acoustic Version)', '(Inst.)', '(Nightcore)',
                      ' - Cover', ' (Official Music Video)', '(Sped Up)', ' (Karaoke)']

    def make_decoy(query, title, artist, i):
        """生成誤導干擾檔名：變體後綴 + 額外藝人。"""
        suffix = DECOY_SUFFIXES[i % len(DECOY_SUFFIXES)]
        extra = ['DJ Panda', 'Various Artists', 'KTV', 'OG Hustle']
        if artist:
            decoy = f'{title} {suffix} - {artist}, {extra[i % len(extra)]}.mp3'
        else:
            decoy = f'{title} {suffix}.mp3'
        return decoy, tuple(get_normalized_tokens(decoy))

    def run_algos(results, stems, display, title_tokens, artist_tokens, q_tokens):
        p = None
        if 'A' in algos:
            p = find_song_simple_match(display, 'mp3', lib_index)
            if not p:
                p = find_song_exact_format(display, 'mp3', lib_index)
            if not p:
                p = find_song_in_library(display, mp3_index, metadata_index=metadata_index)
            results['A'] = p
        if 'B' in algos:
            results['B'] = difflib_best(display, stems)
        if 'C' in algos:
            results['C'] = spotube_style(display, title_tokens, artist_tokens, stems)
        if 'D' in algos:
            results['D'] = token_ratio_best(q_tokens, stems)

    stats = {a: {'hit': 0, 'miss': 0, 'correct_reject': 0, 'false_pos': 0, 'n': 0} for a in algos}
    wrong_examples = {a: [] for a in algos}
    decoy_stats = {a: {'hit': 0, 'miss': 0, 'n': 0} for a in algos}
    decoy_wrong = {a: [] for a in algos}

    for display, rel in sample:
        title, artist = parse_title_artist(display)
        truth_stem = os.path.basename(rel)
        truth_toks = tuple(get_normalized_tokens(os.path.splitext(truth_stem)[0]))
        truth_full = os.path.normpath(os.path.join(PLAYLISTS_DIR, rel))
        truth_exists = os.path.exists(truth_full)

        q_tokens = tuple(get_normalized_tokens(display))
        t_tokens = tuple(get_normalized_tokens(title))
        a_tokens = tuple(get_normalized_tokens(artist))

        results = {}
        run_algos(results, stems, display, t_tokens, a_tokens, q_tokens)

        # ---- decoy 干擾輪：B/C/D 對「真實 + 干擾」候選集的表現 ----
        if args.decoy > 0:
            decoy_list = []
            for i in range(args.decoy):
                dname, dtoks = make_decoy(query=display, title=title, artist=artist, i=i)
                decoy_list.append((dname, dname, dtoks))
            # 干擾排最前面：考驗演算法不被「先遇到的變體版」帶偏
            decoy_stems = decoy_list + stems
            d_results = {}
            run_algos(d_results, decoy_stems, display, t_tokens, a_tokens, q_tokens)
            for a in algos:
                if a == 'A':
                    continue  # A 走磁碟索引，無法模擬干擾
                s = decoy_stats[a]
                s['n'] += 1
                pred = d_results.get(a)
                if pred is not None and os.path.basename(pred) in [d[0] for d in decoy_list]:
                    s['miss'] += 1
                    decoy_wrong[a].append((display, os.path.basename(pred)))
                else:
                    s['hit'] += 1

        for a, pred in results.items():
            s = stats[a]
            s['n'] += 1
            if not truth_exists:
                if pred is None:
                    s['correct_reject'] += 1
                else:
                    s['false_pos'] += 1
                    wrong_examples[a].append((display, '檔案不存在但匹配到', pred, truth_stem))
            else:
                pred_match = pred is not None and tuple(get_normalized_tokens(os.path.splitext(os.path.basename(pred))[0])) == truth_toks
                if pred is not None and not os.path.exists(pred):
                    pred_match = False
                if pred_match:
                    s['hit'] += 1
                else:
                    s['miss'] += 1
                    wrong_examples[a].append((display, pred, truth_stem))

    print('=' * 78)
    print(f"{'演算法':<10}{'n':>6}{'hit@1':>9}{'命中率':>9}{'miss':>7}{'正確拒絕':>9}{'誤報':>6}")
    print('-' * 78)
    for a in algos:
        s = stats[a]
        rate = s['hit'] / max(1, s['n']) * 100
        print(f"{a:<10}{s['n']:>6}{s['hit']:>9}{rate:>8.1f}%{s['miss']:>7}{s['correct_reject']:>9}{s['false_pos']:>6}")

    if args.decoy > 0:
        print('\n--- decoy 干擾測試（同名變體版誤導）---')
        print(f"{'演算法':<10}{'n':>6}{'抗干擾命中':>12}{'被誤導':>8}")
        print('-' * 42)
        for a in algos:
            if a == 'A':
                continue
            s = decoy_stats[a]
            rate = s['hit'] / max(1, s['n']) * 100
            print(f"{a:<10}{s['n']:>6}{rate:>11.1f}%{s['miss']:>8}")
        for a in algos:
            examples = decoy_wrong[a][:8]
            if not examples:
                continue
            print(f'\n[{a}] 被以下干擾誤導:')
            for q, d in examples:
                print(f'    {q}\n      誤選: {d}')

    print('\n--- 錯誤範例（每演算法前 10 筆）---')
    for a in algos:
        examples = wrong_examples[a][:10]
        if not examples:
            continue
        print(f'\n[{a}] {len(wrong_examples[a])} 筆錯誤，範例:')
        for ex in examples:
            if len(ex) == 3:
                q, pred, truth = ex
                print(f'  查詢: {q}\n    猜: {pred}\n    正解: {truth}')
            else:
                q, why, pred, truth = ex
                print(f'  查詢: {q} ({why})\n    猜: {pred}')


if __name__ == '__main__':
    main()