import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterable

import requests
from bs4 import BeautifulSoup
from zhconv import convert


DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}


@dataclass
class PlaylistFetchResult:
    source: str
    url: str
    playlist_name: str | None
    tracks: list[str]
    status_code: int | None = None
    error: str | None = None


def spotify_type_and_id(sp_url: str) -> tuple[str, str]:
    clean_url = sp_url.split("?", 1)[0].strip().rstrip("/")
    for type_path in ("playlist", "album", "artist", "track"):
        marker = f"{type_path}/"
        if marker in clean_url:
            return type_path, clean_url.split(marker, 1)[1].split("/", 1)[0]
    return "playlist", clean_url


def embed_url_for(sp_url: str) -> str:
    type_path, sp_id = spotify_type_and_id(sp_url)
    return f"https://open.spotify.com/embed/{type_path}/{sp_id}"


def _get_path(obj: Any, keys: Iterable[str]) -> Any:
    curr = obj
    for key in keys:
        if isinstance(curr, dict) and key in curr:
            curr = curr[key]
        else:
            return None
    return curr


def _clean_artist_name(name: str | None) -> str | None:
    if not name:
        return name
    return re.sub(r"^E(?=[A-Z\u4e00-\u9fff\u3040-\u30ff])", "", name).strip()


def _artist_from_track(track: dict[str, Any]) -> str | None:
    artists = track.get("artists")
    if isinstance(artists, list) and artists:
        names = []
        for artist in artists:
            if isinstance(artist, dict):
                name = artist.get("name") or artist.get("title")
            else:
                name = str(artist)
            if name:
                names.append(_clean_artist_name(name))
        return ", ".join(name for name in names if name)

    subtitle = track.get("subtitle") or track.get("artist") or track.get("artistsText")
    if isinstance(subtitle, dict):
        subtitle = subtitle.get("text")
    return _clean_artist_name(str(subtitle)) if subtitle else None


def _track_name_from_obj(obj: dict[str, Any]) -> str | None:
    track = obj.get("track", obj)
    if not isinstance(track, dict):
        return None

    title = track.get("name") or track.get("title")
    if isinstance(title, dict):
        title = title.get("text")
    if not title:
        return None

    artist = _artist_from_track(track)
    return f"{title} - {artist}" if artist else str(title)


def _tracks_from_items(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []

    tracks = []
    for item in items:
        if isinstance(item, dict):
            track_name = _track_name_from_obj(item)
            if track_name:
                tracks.append(track_name)
    return tracks


def _legacy_tracks_from_entity(entity: dict[str, Any]) -> list[str]:
    track_list = (
        entity.get("trackList")
        or entity.get("topTracks")
        or (entity.get("tracks") and entity.get("tracks").get("items"))
        or (entity.get("tracks") and entity.get("tracks").get("data"))
    )
    return _tracks_from_items(track_list)


def _recursive_track_candidates(obj: Any, path: str = "$") -> list[tuple[str, list[str]]]:
    candidates = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            next_path = f"{path}.{key}"
            tracks = _tracks_from_items(value)
            if len(tracks) >= 2:
                candidates.append((next_path, tracks))
            candidates.extend(_recursive_track_candidates(value, next_path))
    elif isinstance(obj, list):
        tracks = _tracks_from_items(obj)
        if len(tracks) >= 2:
            candidates.append((path, tracks))
        for index, value in enumerate(obj):
            candidates.extend(_recursive_track_candidates(value, f"{path}[{index}]"))
    return candidates


def _dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        key = value.strip()
        if key and key not in seen:
            result.append(key)
            seen.add(key)
    return result


def comparable_track_name(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip()


def _best_candidate(candidates: list[tuple[str, list[str]]]) -> tuple[str, list[str]] | None:
    if not candidates:
        return None
    return max(candidates, key=lambda item: (len(item[1]), item[0].count("trackList"), -len(item[0])))


def _parse_next_data(html: str) -> tuple[dict[str, Any] | None, BeautifulSoup]:
    soup = BeautifulSoup(html, "html.parser")
    next_data_tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not next_data_tag or not next_data_tag.string:
        return None, soup
    return json.loads(next_data_tag.string), soup


def fetch_legacy_embed_playlist(sp_url: str, session: requests.Session | None = None) -> PlaylistFetchResult:
    session = session or requests.Session()
    url = embed_url_for(sp_url)
    try:
        resp = session.get(url, headers=DEFAULT_HEADERS, timeout=20)
        resp.raise_for_status()
        data, _ = _parse_next_data(resp.text)
        entity = _get_path(data, ["props", "pageProps", "state", "data", "entity"]) if data else None
        playlist_name = convert(entity.get("name"), "zh-tw") if isinstance(entity, dict) and entity.get("name") else None
        tracks = _legacy_tracks_from_entity(entity) if isinstance(entity, dict) else []
        return PlaylistFetchResult("legacy_embed", url, playlist_name, _dedupe_keep_order(tracks), resp.status_code)
    except Exception as exc:
        return PlaylistFetchResult("legacy_embed", url, None, [], None, str(exc))


def fetch_redesigned_playlist(sp_url: str, session: requests.Session | None = None) -> PlaylistFetchResult:
    session = session or requests.Session()
    url = embed_url_for(sp_url)
    try:
        resp = session.get(url, headers=DEFAULT_HEADERS, timeout=20)
        resp.raise_for_status()
        data, soup = _parse_next_data(resp.text)
        entity = _get_path(data, ["props", "pageProps", "state", "data", "entity"]) if data else None
        playlist_name = convert(entity.get("name"), "zh-tw") if isinstance(entity, dict) and entity.get("name") else None

        candidates = []
        if isinstance(entity, dict):
            legacy = _legacy_tracks_from_entity(entity)
            if legacy:
                candidates.append(("entity.legacy_track_fields", legacy))
        if data:
            candidates.extend(_recursive_track_candidates(data))

        best = _best_candidate(candidates)
        if best:
            source_path, tracks = best
            return PlaylistFetchResult(
                f"redesigned_embed:{source_path}",
                url,
                playlist_name,
                _dedupe_keep_order(tracks),
                resp.status_code,
            )

        html_tracks = _tracks_from_html_rows(soup)
        return PlaylistFetchResult("redesigned_embed:html_rows", url, playlist_name, html_tracks, resp.status_code)
    except Exception as exc:
        return PlaylistFetchResult("redesigned_embed", url, None, [], None, str(exc))


def _tracks_from_html_rows(soup: BeautifulSoup) -> list[str]:
    tracks = []
    rows = soup.find_all("li", class_=lambda value: value and "TracklistRow_trackListRow" in value)
    for row in rows:
        title_tag = row.find("h3", class_=lambda value: value and "TracklistRow_title" in value)
        artist_tag = row.find("h4", class_=lambda value: value and "TracklistRow_subtitle" in value)
        if title_tag and artist_tag:
            title = title_tag.get_text(strip=True)
            artist = _clean_artist_name(artist_tag.get_text(strip=True))
            if title:
                tracks.append(f"{title} - {artist}" if artist else title)
    return _dedupe_keep_order(tracks)


def compare_track_lists(new_tracks: list[str], old_tracks: list[str]) -> dict[str, list[str]]:
    new_set = {comparable_track_name(track) for track in new_tracks}
    old_set = {comparable_track_name(track) for track in old_tracks}
    return {
        "only_new": [track for track in new_tracks if comparable_track_name(track) not in old_set],
        "only_legacy": [track for track in old_tracks if comparable_track_name(track) not in new_set],
        "same_order_differences": [
            f"{index + 1}. new={new} | legacy={old}"
            for index, (new, old) in enumerate(zip(new_tracks, old_tracks))
            if comparable_track_name(new) != comparable_track_name(old)
        ],
    }


def _find_chrome_executable() -> str | None:
    candidates = [
        os.environ.get("CHROME_PATH"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        shutil.which("msedge"),
        shutil.which("msedge.exe"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _free_local_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


async def _cdp_fetch_rendered_tracks(sp_url: str, timeout_seconds: int, headless: bool) -> PlaylistFetchResult:
    try:
        import websockets
    except ImportError as exc:
        return PlaylistFetchResult("browser_open_page", sp_url, None, [], None, f"websockets is required: {exc}")

    chrome = _find_chrome_executable()
    if not chrome:
        return PlaylistFetchResult("browser_open_page", sp_url, None, [], None, "Chrome or Edge executable not found")

    port = _free_local_port()
    profile_dir = tempfile.mkdtemp(prefix="playlist-admin-chrome-")
    chrome_args = [
        chrome,
        "--disable-gpu",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
        "--window-size=1600,1200",
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        sp_url,
    ]
    if headless:
        chrome_args.insert(1, "--headless=new")

    proc = subprocess.Popen(
        chrome_args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        tabs = None
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1) as resp:
                    tabs = json.loads(resp.read().decode("utf-8"))
                if tabs:
                    break
            except Exception:
                time.sleep(0.1)

        if not tabs:
            return PlaylistFetchResult("browser_open_page", sp_url, None, [], None, "Chrome DevTools did not start")

        page_target = None
        for tab in tabs:
            if tab.get("type") == "page" and "open.spotify.com" in tab.get("url", ""):
                page_target = tab
                break
        if not page_target:
            for tab in tabs:
                if tab.get("type") == "page":
                    page_target = tab
                    break
        if not page_target:
            return PlaylistFetchResult("browser_open_page", sp_url, None, [], None, "No Chrome page target found")

        websocket_url = page_target["webSocketDebuggerUrl"]
        async with websockets.connect(websocket_url, max_size=30_000_000) as ws:
            msg_id = 0

            async def command(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
                nonlocal msg_id
                msg_id += 1
                await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
                while True:
                    message = json.loads(await ws.recv())
                    if message.get("id") == msg_id:
                        return message

            await command("Page.enable")
            await command("Runtime.enable")

            expression = r"""
(() => {
  const clean = (value) => (value || '').replace(/\s+/g, ' ').trim();
  const rows = [...document.querySelectorAll('[data-testid="tracklist-row"], div[role="row"]')];
  const tracks = [];
  for (const row of rows) {
    const rowText = clean(row.innerText);
    if (!rowText || /^#?\s*標題\s+專輯/i.test(rowText)) continue;

    const trackLinks = [...row.querySelectorAll('a[href*="/track/"]')];
    let title = clean((trackLinks[0] && trackLinks[0].innerText) || '');
    const artistLinks = [...row.querySelectorAll('a[href*="/artist/"]')]
      .map((link) => clean(link.innerText))
      .filter(Boolean);

    if (!title) {
      const lines = row.innerText.split('\n').map(clean).filter(Boolean);
      title = lines.find((line) => !/^\d+$/.test(line) && !/^\d+:\d{2}$/.test(line)) || '';
    }

    let artists = [...new Set(artistLinks)].join(', ');
    if (!artists && title) {
      const lines = row.innerText.split('\n').map(clean).filter(Boolean);
      const titleIndex = lines.indexOf(title);
      if (titleIndex >= 0 && lines[titleIndex + 1] && !/^\d+:\d{2}$/.test(lines[titleIndex + 1])) {
        artists = lines[titleIndex + 1];
      }
    }

    if (title && artists) tracks.push(`${title} - ${artists}`);
    else if (title) tracks.push(title);
  }
  return {
    title: document.title,
    playlistName: clean(document.querySelector('[data-testid="entityTitle"] h1')?.innerText || document.querySelector('h1')?.innerText || ''),
    tracks: [...new Set(tracks)],
    bodySample: document.body.innerText.slice(0, 1000)
  };
})()
"""

            scroll_expression = r"""
(() => {
  const scrollables = [...document.querySelectorAll('main, div')]
    .filter((el) => el.scrollHeight > el.clientHeight + 200)
    .sort((a, b) => (b.scrollHeight - b.clientHeight) - (a.scrollHeight - a.clientHeight));
  const el = scrollables[0] || document.scrollingElement || document.documentElement;
  const before = el.scrollTop;
  el.scrollTop = before + Math.max(700, Math.floor(el.clientHeight * 0.8));
  window.scrollBy(0, 700);
  return { before, after: el.scrollTop, height: el.scrollHeight, client: el.clientHeight };
})()
"""

            last_value = None
            collected: list[str] = []
            unchanged_rounds = 0
            while time.time() < deadline:
                result = await command(
                    "Runtime.evaluate",
                    {"expression": expression, "returnByValue": True, "awaitPromise": False},
                )
                last_value = result.get("result", {}).get("result", {}).get("value")
                if isinstance(last_value, dict):
                    before_count = len(collected)
                    collected = _dedupe_keep_order([*collected, *last_value.get("tracks", [])])
                    if len(collected) >= 50:
                        return PlaylistFetchResult(
                            "browser_open_page:dom",
                            sp_url,
                            last_value.get("playlistName") or None,
                            collected,
                            200,
                        )
                    if len(collected) == before_count:
                        unchanged_rounds += 1
                    else:
                        unchanged_rounds = 0

                await command("Runtime.evaluate", {"expression": scroll_expression, "returnByValue": True})
                if len(collected) >= 20 and unchanged_rounds >= 8:
                    tracks = _dedupe_keep_order(collected)
                    return PlaylistFetchResult(
                        "browser_open_page:dom",
                        sp_url,
                        last_value.get("playlistName") if isinstance(last_value, dict) else None,
                        tracks,
                        200,
                    )
                time.sleep(1)

            sample = ""
            if isinstance(last_value, dict):
                sample = last_value.get("bodySample", "")
            return PlaylistFetchResult(
                "browser_open_page:dom",
                sp_url,
                None,
                [],
                200,
                f"Timed out waiting for rendered tracks. Sample: {sample[:200]}",
            )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        shutil.rmtree(profile_dir, ignore_errors=True)


def fetch_browser_open_playlist(
    sp_url: str,
    timeout_seconds: int = 45,
    headless: bool = True,
) -> PlaylistFetchResult:
    import asyncio

    return asyncio.run(_cdp_fetch_rendered_tracks(sp_url, timeout_seconds, headless))
