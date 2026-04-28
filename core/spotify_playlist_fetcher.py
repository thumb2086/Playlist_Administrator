import json
import re
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
    new_set = set(new_tracks)
    old_set = set(old_tracks)
    return {
        "only_new": [track for track in new_tracks if track not in old_set],
        "only_legacy": [track for track in old_tracks if track not in new_set],
        "same_order_differences": [
            f"{index + 1}. new={new} | legacy={old}"
            for index, (new, old) in enumerate(zip(new_tracks, old_tracks))
            if new != old
        ],
    }
