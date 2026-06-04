"""
Spotify 播放清單取得模組

使用 Embed 頁面抓取方式取得 Spotify 播放清單曲目。
無需認證，快速且穩定。
"""

import json
import os
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
    """播放清單取得結果"""
    source: str
    url: str
    playlist_name: str | None
    tracks: list[str]
    status_code: int | None = None
    error: str | None = None


# ==================== 工具函數 ====================

def _dedupe_keep_order(values: Iterable[str]) -> list[str]:
    """去除重複項目但保持順序"""
    seen = set()
    result = []
    for value in values:
        key = value.strip()
        if key and key not in seen:
            result.append(key)
            seen.add(key)
    return result


def comparable_track_name(value: str) -> str:
    """標準化曲目名稱用於比較"""
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip()


def compare_track_lists(new_tracks: list[str], old_tracks: list[str]) -> dict[str, list[str]]:
    """比較兩個曲目列表的差異"""
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


# ==================== 快速 Embed 抓取（保留的最快方法） ====================

def _get_path(obj: Any, keys: Iterable[str]) -> Any:
    """安全地從嵌套字典取得值"""
    curr = obj
    for key in keys:
        if isinstance(curr, dict) and key in curr:
            curr = curr[key]
        else:
            return None
    return curr


def _clean_artist_name(name: str | None) -> str | None:
    """清理藝人名稱（移除 Explicit 標記）"""
    if not name:
        return name
    return re.sub(r"^E(?=[A-Z\u4e00-\u9fff\u3040-\u30ff])", "", name).strip()


def _artist_from_track(track: dict[str, Any]) -> str | None:
    """從曲目資料中提取藝人名稱"""
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
    """從曲目物件提取完整曲目名稱（含藝人）"""
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
    """從項目列表提取曲目名稱"""
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
    """從 entity 物件提取曲目列表（支援多種格式）"""
    track_list = (
        entity.get("trackList")
        or entity.get("topTracks")
        or (entity.get("tracks") and entity.get("tracks").get("items"))
        or (entity.get("tracks") and entity.get("tracks").get("data"))
    )
    return _tracks_from_items(track_list)


def _parse_next_data(html: str) -> tuple[dict[str, Any] | None, BeautifulSoup]:
    """從 HTML 解析 __NEXT_DATA__ JSON"""
    soup = BeautifulSoup(html, "html.parser")
    next_data_tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not next_data_tag or not next_data_tag.string:
        return None, soup
    return json.loads(next_data_tag.string), soup


def spotify_type_and_id(sp_url: str) -> tuple[str, str]:
    """從 Spotify URL 提取類型和 ID"""
    clean_url = sp_url.split("?", 1)[0].strip().rstrip("/")
    for type_path in ("playlist", "album", "artist", "track"):
        marker = f"{type_path}/"
        if marker in clean_url:
            return type_path, clean_url.split(marker, 1)[1].split("/", 1)[0]
    return "playlist", clean_url


def embed_url_for(sp_url: str) -> str:
    """建立 embed URL"""
    type_path, sp_id = spotify_type_and_id(sp_url)
    return f"https://open.spotify.com/embed/{type_path}/{sp_id}"


def fetch_legacy_embed_playlist(sp_url: str, session: requests.Session | None = None) -> PlaylistFetchResult:
    """
    最快的播放清單取得方法
    
    使用 Spotify embed 頁面抓取，無需認證，速度最快。
    這是推薦的預設方法，因為不需要設定任何 API 金鑰。
    
    Args:
        sp_url: Spotify URL（播放清單、專輯、藝人或單曲）
        session: 可選的 requests Session 物件
        
    Returns:
        PlaylistFetchResult 物件
    """
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


# ==================== 統一介面 ====================

def fetch_playlist(
    sp_url: str,
    session: requests.Session | None = None
) -> PlaylistFetchResult:
    """
    使用 Embed 頁面抓取 Spotify 播放清單
    
    Args:
        sp_url: Spotify URL
        session: requests Session（可選）
        
    Returns:
        PlaylistFetchResult 物件
    """
    return fetch_legacy_embed_playlist(sp_url, session)
