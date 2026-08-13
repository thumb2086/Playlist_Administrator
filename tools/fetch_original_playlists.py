"""Fetch ORIGINAL Spotify playlists (embed API) into a standalone snapshot.

Does NOT touch the processed playlists in Playlists\\ — writes to
Playlists_Original\\ + original_snapshot.json so coverage can be audited
against the true Spotify track lists.
"""
import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')


def get_path(obj, keys):
    cur = obj
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None
    return cur


def clean_artist(name):
    if not name:
        return name
    return re.sub(r'^E(?=[A-Z\u4e00-\u9fff\u3040-\u30ff])', '', name)


def first_image(obj, keys):
    imgs = get_path(obj, keys)
    if isinstance(imgs, list) and imgs:
        first = imgs[0]
        if isinstance(first, dict) and first.get('url'):
            return first['url']
        if isinstance(first, dict):
            sources = first.get('sources')
            if sources:
                return sources[0].get('url')
    if isinstance(imgs, dict) and imgs.get('sources'):
        return imgs['sources'][0].get('url')
    return None


def fetch_playlist(sp_url, cache_dir, timeout=30):
    sp_id = sp_url.split('?')[0].split('playlist/')[-1]
    embed_url = f'https://open.spotify.com/embed/playlist/{sp_id}'
    resp = requests.get(embed_url, headers={
        'User-Agent': UA,
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8',
        'Accept': 'text/html,*/*;q=0.8',
    }, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    tag = soup.find('script', {'id': '__NEXT_DATA__'})
    if not tag:
        return None, None
    data = json.loads(tag.string)
    entity = get_path(data, ['props', 'pageProps', 'state', 'data', 'entity'])
    if not entity:
        return None, None
    name = entity.get('name')
    track_list = entity.get('trackList') or entity.get('topTracks') or \
        (entity.get('tracks') and entity.get('tracks').get('items')) or \
        (entity.get('tracks') and entity.get('tracks').get('data'))
    out = []
    for item in (track_list or []):
        track = item.get('track', item)
        title = track.get('name') or track.get('title')
        artists = track.get('artists', [])
        artist = clean_artist(artists[0].get('name')) if artists else \
            clean_artist(track.get('subtitle'))
        if title:
            full = f'{title} - {artist}' if artist else title
            out.append(full)
            # Write spotify_cache so the native downloader can tag + cover the file.
            try:
                meta = {
                    'title': title,
                    'artist': artist or '',
                    'album': get_path(track, ['album', 'name']) or
                             (entity.get('name') if entity.get('type') == 'album' else ''),
                    'release_date': get_path(track, ['album', 'release_date']) or '',
                    'cover_url': first_image(track, ['album', 'images']) or
                                 first_image(track, ['visualIdentity', 'image']) or
                                 first_image(track, ['coverArt', 'image']),
                }
                if meta.get('cover_url'):
                    os.makedirs(cache_dir, exist_ok=True)
                    clean = re.sub(r'[<>:"/\\|?*]', '_', full).strip('. -')
                    with open(os.path.join(cache_dir, f'{clean}.json'), 'w', encoding='utf-8') as mf:
                        json.dump(meta, mf, ensure_ascii=False)
            except Exception:
                pass
    return name, out


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\CPXru\Music\Spotube'
    config = json.load(open(os.path.join(base, 'config.json'), encoding='utf-8'))
    urls = config.get('spotify_urls', [])
    url_names = config.get('url_names', {})
    if sys.stdout.encoding and 'utf' not in sys.stdout.encoding.lower():
        sys.stdout.reconfigure(encoding='utf-8')

    snapshot = {'version': '2.0-original', 'playlists': {}}
    out_dir = os.path.join(base, 'Playlists_Original')
    cache_dir = os.path.join(base, 'spotify_cache')
    os.makedirs(out_dir, exist_ok=True)
    ok = fail = 0
    for i, url in enumerate(urls):
        try:
            print(f'[{i + 1}/{len(urls)}] fetching {url}', flush=True)
            name, tracks = fetch_playlist(url, cache_dir)
            if not tracks:
                print(f'  !! no tracks for {url}')
                fail += 1
                continue
            disp = name or url_names.get(url, url)
            snapshot['playlists'][disp] = tracks
            with open(os.path.join(out_dir, f'{disp}.txt'), 'w', encoding='utf-8') as f:
                f.write('\n'.join(tracks))
            print(f'  -> {disp}: {len(tracks)} tracks')
            ok += 1
        except Exception as e:
            print(f'  !! {url}: {e}')
            fail += 1
        time.sleep(0.4)

    snap_path = os.path.join(base, 'original_snapshot.json')
    with open(snap_path, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, ensure_ascii=False)
    print(f'DONE ok={ok} fail={fail} -> {snap_path}')


if __name__ == '__main__':
    main()