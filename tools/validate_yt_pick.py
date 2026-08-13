"""
與 Spotube 下載正確率對照驗證。

基準資料：
- Spotify 原始歌單（從 embed 頁面抓 entity.trackList）→ 「Spotify 曲目」
- Playlists/*.m3u8（pipeline 產物 = Spotube 已下載成功）→ ground truth「Spotube OK」

對每一首 Spotify 曲目執行與 downloader 相同的選片邏輯
（ytsearch6 + rank_yt_videos），統計：
  spotube_ok   : Spotube 已下載（出現在 m3u8）
  my_ok        : 我們選片 >= 3 分
  my_low       : 1~2 分（低信心仍下載）
  my_reject    : 0 分（正確拒絕）
 誤殺 = spotube_ok 但 my_reject（Spotube 有、我們拒絕 → 需要人工確認）
"""
import os
import re
import sys
import json
import time
import random

ROOT = r'C:\Users\CPXru\Desktop\thumb\program\Playlist_Administrator'
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

from core.downloader import rank_yt_videos
from core.library import get_normalized_tokens
import yt_dlp
import requests
from bs4 import BeautifulSoup

PLAYLISTS_DIR = r'C:\Users\CPXru\Music\Spotube\Playlists'
CACHE_PATH = os.path.join(ROOT, 'tools', '_yt_pick_cache.json')


def get_path(obj, keys):
    curr = obj
    for k in keys:
        if isinstance(curr, dict) and k in curr:
            curr = curr[k]
        else:
            return None
    return curr


def fetch_spotify_tracks(url):
    """從 embed 頁面抓曲目清單，回傳 [(title, artist)]（Spotify 原始資料）"""
    sp_id = url.split('?')[0].split('playlist/')[-1]
    embed_url = f"https://open.spotify.com/embed/playlist/{sp_id}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    r = requests.get(embed_url, headers=headers, timeout=15)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'html.parser')
    tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not tag:
        return []
    data = json.loads(tag.string)
    entity = get_path(data, ['props', 'pageProps', 'state', 'data', 'entity'])
    if not entity:
        return []
    track_list = (entity.get('trackList') or entity.get('topTracks') or
                  (entity.get('tracks') or {}).get('items') or
                  (entity.get('tracks') or {}).get('data'))
    out = []
    for item in (track_list or []):
        item = item or {}
        t = item.get('title') or item.get('name')
        if not t:
            continue
        artists = item.get('artists') or None
        if artists and isinstance(artists[0], dict):
            a = artists[0].get('name') or ''
        else:
            a = item.get('subtitle') or ''
            if a:
                a = a.split(',')[0].strip()
        if a and a not in t:
            out.append((t.strip(), a.strip()))
    return out


def load_m3u8_ok_set():
    """m3u8 內容 = Spotube 已下載成功的集合（display - 檔名）"""
    ok = set()
    for fn in os.listdir(PLAYLISTS_DIR):
        if not fn.endswith('.m3u8'):
            continue
        with open(os.path.join(PLAYLISTS_DIR, fn), encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('#EXTINF'):
                    content = line.split(',', 1)[1].strip() if ',' in line else ''
                    if content:
                        ok.add(content)
    return ok


def norm_key(title, artist):
    return tuple(get_normalized_tokens(f"{title} {artist}"))


def main():
    from utils.config import load_config
    cfg = load_config()
    urls = cfg.get('spotify_urls', [])
    names = cfg.get('url_names', {})

    ok_set_tokens = set()
    ok_set_raw = load_m3u8_ok_set()
    for raw in ok_set_raw:
        if ' - ' in raw:
            t, a = raw.rsplit(' - ', 1)
            ok_set_tokens.add(norm_key(t, a))

    print("抓取 Spotify 原始歌單...")
    all_tracks = []  # (playlist_name, title, artist)
    for url in urls:
        name = names.get(url, url)
        try:
            tracks = fetch_spotify_tracks(url)
        except Exception as e:
            print(f"  ❌ {name}: {e}")
            continue
        print(f"  {name}: {len(tracks)} 首")
        for t, a in tracks:
            all_tracks.append((name, t, a))

    print(f"\nSpotify 原始曲目: {len(all_tracks)} 首 (去重前)")
    seen = set()
    uniq = []
    for name, t, a in all_tracks:
        k = (name, t, a)
        if k not in seen:
            seen.add(k)
            uniq.append(k)
    print(f"去重後: {len(uniq)} 首")

    # cache
    cache = {}
    if os.path.exists(CACHE_PATH):
        try:
            cache = json.load(open(CACHE_PATH, encoding='utf-8'))
        except Exception:
            cache = {}

    opts = {'quiet': True, 'no_warnings': True, 'skip_download': True,
            'extract_flat': True, 'ignoreerrors': True, 'socket_timeout': 30}

    stats = {'spotube_ok': 0, 'my_ok': 0, 'my_low': 0, 'my_reject': 0,
             'false_kill': 0, 'n': 0}
    details = []

    with yt_dlp.YoutubeDL(opts) as ydl:
        for idx, (pl, title, artist) in enumerate(uniq, 1):
            key = norm_key(title, artist)
            sock = tuple(key)
            if str(sock) in cache:
                score = cache[str(sock)]
            else:
                try:
                    info = ydl.extract_info(f'ytsearch6:{title} {artist}', download=False)
                    entries = (info or {}).get('entries') or []
                except Exception:
                    entries = []
                best, score = rank_yt_videos(entries, title, artist)
                cache[str(sock)] = score
            spotube_has = sock in ok_set_tokens
            if score >= 3:
                my_state = 'ok'
                stats['my_ok'] += 1
            elif score > 0:
                my_state = 'low'
                stats['my_low'] += 1
            else:
                my_state = 'reject'
                stats['my_reject'] += 1
            stats['n'] += 1
            if spotube_has:
                stats['spotube_ok'] += 1
                if my_state == 'reject':
                    stats['false_kill'] += 1
                    details.append(('FALSE_KILL', pl, title, artist))
            else:
                if my_state == 'reject':
                    details.append(('BOTH_REJECT', pl, title, artist))
                elif my_state == 'ok':
                    details.append(('MY_ONLY', pl, title, artist))
            if idx % 25 == 0:
                print(f"  ...{idx}/{len(uniq)}  (reject={stats['my_reject']}, false_kill={stats['false_kill']})")
                json.dump(cache, open(CACHE_PATH, 'w', encoding='utf-8'), ensure_ascii=False)

    json.dump(cache, open(CACHE_PATH, 'w', encoding='utf-8'), ensure_ascii=False)

    n = max(1, stats['n'])
    print("\n" + "=" * 72)
    print(f"Spotify 曲目總數: {stats['n']}")
    print(f"Spotube OK (m3u8 有):       {stats['spotube_ok']}  ({stats['spotube_ok']/n*100:.1f}%)")
    print(f"我們選片 OK (>=3 分):       {stats['my_ok']}  ({stats['my_ok']/n*100:.1f}%)")
    print(f"我們選片 LOW (1~2 分):      {stats['my_low']}")
    print(f"我們拒絕 (0 分):            {stats['my_reject']}  ({stats['my_reject']/n*100:.1f}%)")
    print(f"誤殺 (Spotube有 但我們拒):  {stats['false_kill']}")
    print("=" * 72)

    fake = [d for d in details if d[0] == 'FALSE_KILL']
    both = [d for d in details if d[0] == 'BOTH_REJECT']
    mine = [d for d in details if d[0] == 'MY_ONLY']
    print(f"\n--- 誤殺清單 ({len(fake)}) ---")
    for _, pl, t, a in fake[:15]:
        print(f"  ❌ {t[:36]} - {a[:22]}  [{pl}]")
    print(f"\n--- 雙方都拒絕 ({len(both)})，前 10 筆 ---")
    for _, pl, t, a in both[:10]:
        print(f"  ⏭️ {t[:36]} - {a[:22]}  [{pl}]")


if __name__ == '__main__':
    main()