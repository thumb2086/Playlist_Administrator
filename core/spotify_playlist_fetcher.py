"""
Spotify 播放清單取得模組

提供兩種取得方式：
1. fetch_legacy_embed_playlist - 快速 embed 頁面抓取（無需認證，最快速）
2. fetch_via_web_api - Spotify Web API（需要 Client ID/Secret 和 Premium 訂閱才能取得個人化動態清單）
"""

import json
import os
import re
import base64
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


# ==================== Spotify Web API 支援 (OAuth 使用者授權) ====================

import hashlib
import secrets
import webbrowser
from urllib.parse import urlencode, parse_qs, urlparse
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time


class SpotifyWebAPI:
    """
    Spotify Web API 客戶端（支援 OAuth 使用者授權）
    
    使用 OAuth 2.0 Authorization Code Flow + PKCE，支援：
    - 個人化播放清單（Daily Mix、Discover Weekly）
    - 私人播放清單讀取
    
    使用方式：
    1. 在 https://developer.spotify.com/dashboard 建立 App
    2. 設定 Redirect URI: http://localhost:8888/callback
    3. 取得 Client ID
    4. 使用者授權登入（會開啟瀏覽器）
    
    注意：需要 Spotify Premium 才能存取 Web API 的個人化內容
    """
    
    AUTH_URL = "https://accounts.spotify.com/authorize"
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    API_BASE = "https://api.spotify.com/v1"
    REDIRECT_URI = "http://localhost:8888/callback"
    
    def __init__(self, client_id: str | None = None, client_secret: str | None = None, 
                 access_token: str | None = None, refresh_token: str | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: str | None = access_token
        self._refresh_token: str | None = refresh_token
        self._token_type: str = "Bearer"
        self._code_verifier: str | None = None
    
    def is_configured(self) -> bool:
        """檢查是否已設定 Client ID"""
        return bool(self.client_id)
    
    def _generate_pkce(self) -> tuple[str, str]:
        """產生 PKCE code_verifier 和 code_challenge"""
        code_verifier = base64.urlsafe_b64encode(
            secrets.token_bytes(32)
        ).decode('utf-8').rstrip('=')
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode('utf-8').rstrip('=')
        return code_verifier, code_challenge
    
    def authenticate_with_user_auth(self, timeout: int = 60) -> bool:
        """
        使用 OAuth Authorization Code Flow + PKCE 進行使用者授權
        會開啟瀏覽器讓使用者登入 Spotify
        """
        if not self.client_id:
            print("錯誤: Client ID 未設定")
            return False
        
        # 產生 PKCE 參數
        self._code_verifier, code_challenge = self._generate_pkce()
        state = secrets.token_urlsafe(16)
        
        # 建立授權 URL
        auth_params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.REDIRECT_URI,
            "state": state,
            "scope": "playlist-read-private playlist-read-collaborative user-library-read",
            "code_challenge_method": "S256",
            "code_challenge": code_challenge
        }
        auth_url = f"{self.AUTH_URL}?{urlencode(auth_params)}"
        
        # 啟動本地伺服器接收回調
        auth_code = None
        received_state = None
        server_error = None
        
        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                nonlocal auth_code, received_state, server_error
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                
                if "error" in query:
                    server_error = query["error"][0]
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(f"授權失敗: {server_error}".encode())
                    return
                
                if "code" in query:
                    auth_code = query["code"][0]
                    received_state = query.get("state", [None])[0]
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    html = """
                    <html>
                    <head><title>授權成功</title></head>
                    <body style="font-family: sans-serif; text-align: center; padding: 50px;">
                        <h1>✅ Spotify 授權成功！</h1>
                        <p>您可以關閉此視窗並回到應用程式。</p>
                    </body>
                    </html>
                    """
                    self.wfile.write(html.encode())
                else:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"Invalid request")
            
            def log_message(self, format, *args):
                pass  # 抑制伺服器日誌輸出
        
        # 啟動伺服器
        server = HTTPServer(("localhost", 8888), CallbackHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        
        # 開啟瀏覽器
        print(f"正在開啟瀏覽器進行 Spotify 授權...")
        webbrowser.open(auth_url)
        
        # 等待回調
        start_time = time.time()
        while auth_code is None and server_error is None:
            if time.time() - start_time > timeout:
                print("授權逾時")
                server.shutdown()
                return False
            time.sleep(0.5)
        
        server.shutdown()
        
        if server_error:
            print(f"授權錯誤: {server_error}")
            return False
        
        if received_state != state:
            print("錯誤: State 驗證失敗（可能的 CSRF 攻擊）")
            return False
        
        # 交換 access token
        return self._exchange_code_for_token(auth_code)
    
    def _exchange_code_for_token(self, auth_code: str) -> bool:
        """用授權碼交換 access token"""
        try:
            data = {
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": self.REDIRECT_URI,
                "client_id": self.client_id,
                "code_verifier": self._code_verifier
            }
            
            # 如果有 client_secret，加入認證
            if self.client_secret:
                credentials = base64.b64encode(
                    f"{self.client_id}:{self.client_secret}".encode()
                ).decode()
                headers = {
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            else:
                headers = {"Content-Type": "application/x-www-form-urlencoded"}
            
            resp = requests.post(self.TOKEN_URL, headers=headers, data=data, timeout=30)
            resp.raise_for_status()
            token_data = resp.json()
            
            self._access_token = token_data.get("access_token")
            self._refresh_token = token_data.get("refresh_token")
            self._token_type = token_data.get("token_type", "Bearer")
            
            print(f"✅ Spotify 授權成功！取得 {token_data.get('scope', 'unknown')} 權限")
            return bool(self._access_token)
            
        except Exception as exc:
            print(f"交換 token 失敗: {exc}")
            return False
    
    def refresh_access_token(self) -> bool:
        """使用 refresh token 更新 access token"""
        if not self._refresh_token:
            return False
        
        try:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self.client_id
            }
            
            if self.client_secret:
                credentials = base64.b64encode(
                    f"{self.client_id}:{self.client_secret}".encode()
                ).decode()
                headers = {"Authorization": f"Basic {credentials}"}
            else:
                headers = {}
            
            resp = requests.post(self.TOKEN_URL, headers=headers, data=data, timeout=30)
            resp.raise_for_status()
            token_data = resp.json()
            
            self._access_token = token_data.get("access_token")
            if token_data.get("refresh_token"):
                self._refresh_token = token_data.get("refresh_token")
            
            return bool(self._access_token)
            
        except Exception as exc:
            print(f"重新整理 token 失敗: {exc}")
            return False
    
    def _get_auth_header(self) -> dict[str, str]:
        """建立認證標頭"""
        if not self.client_id or not self.client_secret:
            raise ValueError("Client ID 和 Client Secret 未設定")
        
        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()
        
        return {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    
    def authenticate(self) -> bool:
        """
        使用 Client Credentials Flow 取得存取權杖
        這不需要使用者互動，適合伺服器端應用
        """
        if not self.is_configured():
            return False
        
        try:
            resp = requests.post(
                self.AUTH_URL,
                headers=self._get_auth_header(),
                data={"grant_type": "client_credentials"},
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            
            self._access_token = data.get("access_token")
            self._token_type = data.get("token_type", "Bearer")
            return bool(self._access_token)
            
        except Exception as exc:
            print(f"Spotify API 認證失敗: {exc}")
            return False
    
    def _api_headers(self) -> dict[str, str]:
        """建立 API 請求標頭"""
        if not self._access_token:
            raise ValueError("未認證，請先呼叫 authenticate()")
        
        return {
            "Authorization": f"{self._token_type} {self._access_token}",
            "Accept": "application/json",
        }
    
    def _extract_id_from_url(self, spotify_url: str) -> tuple[str, str] | None:
        """從 Spotify URL 提取類型和 ID"""
        patterns = [
            (r"spotify:playlist:([a-zA-Z0-9]+)", "playlist"),
            (r"spotify:album:([a-zA-Z0-9]+)", "album"),
            (r"open\.spotify\.com/playlist/([a-zA-Z0-9]+)", "playlist"),
            (r"open\.spotify\.com/album/([a-zA-Z0-9]+)", "album"),
        ]
        
        for pattern, item_type in patterns:
            match = re.search(pattern, spotify_url)
            if match:
                return item_type, match.group(1)
        
        return None
    
    def get_playlist_tracks(
        self, 
        playlist_id: str, 
        limit: int = 100,
        fields: str | None = None
    ) -> dict[str, Any] | None:
        """
        取得播放清單中的所有曲目
        
        注意：免費帳號可以讀取公開播放清單
        """
        if not self._access_token and not self.authenticate():
            return None
        
        all_tracks = []
        offset = 0
        playlist_name = None
        
        # 首先取得播放清單基本資訊
        try:
            resp = requests.get(
                f"{self.API_BASE}/playlists/{playlist_id}",
                headers=self._api_headers(),
                params={"fields": "name,tracks.total"},
                timeout=30
            )
            resp.raise_for_status()
            playlist_data = resp.json()
            playlist_name = playlist_data.get("name")
            total_tracks = playlist_data.get("tracks", {}).get("total", 0)
        except Exception as exc:
            print(f"取得播放清單資訊失敗: {exc}")
            return None
        
        # 分批取得所有曲目
        while offset < total_tracks:
            try:
                params = {
                    "limit": min(limit, 100),  # Spotify API 限制每次最多 100 首
                    "offset": offset,
                    "fields": fields or "items(track(name,artists(name),album(name)))"
                }
                
                resp = requests.get(
                    f"{self.API_BASE}/playlists/{playlist_id}/tracks",
                    headers=self._api_headers(),
                    params=params,
                    timeout=30
                )
                resp.raise_for_status()
                data = resp.json()
                
                items = data.get("items", [])
                if not items:
                    break
                
                all_tracks.extend(items)
                offset += len(items)
                
            except Exception as exc:
                print(f"取得曲目時發生錯誤 (offset={offset}): {exc}")
                break
        
        return {
            "name": playlist_name,
            "total": total_tracks,
            "items": all_tracks
        }
    
    def get_album_tracks(self, album_id: str, limit: int = 50) -> dict[str, Any] | None:
        """取得專輯中的所有曲目"""
        if not self._access_token and not self.authenticate():
            return None
        
        all_tracks = []
        offset = 0
        album_name = None
        
        # 首先取得專輯基本資訊
        try:
            resp = requests.get(
                f"{self.API_BASE}/albums/{album_id}",
                headers=self._api_headers(),
                timeout=30
            )
            resp.raise_for_status()
            album_data = resp.json()
            album_name = album_data.get("name")
            total_tracks = album_data.get("tracks", {}).get("total", 0)
        except Exception as exc:
            print(f"取得專輯資訊失敗: {exc}")
            return None
        
        # 分批取得所有曲目
        while offset < total_tracks:
            try:
                params = {
                    "limit": min(limit, 50),
                    "offset": offset
                }
                
                resp = requests.get(
                    f"{self.API_BASE}/albums/{album_id}/tracks",
                    headers=self._api_headers(),
                    params=params,
                    timeout=30
                )
                resp.raise_for_status()
                data = resp.json()
                
                items = data.get("items", [])
                if not items:
                    break
                
                all_tracks.extend(items)
                offset += len(items)
                
            except Exception as exc:
                print(f"取得曲目時發生錯誤 (offset={offset}): {exc}")
                break
        
        return {
            "name": album_name,
            "total": total_tracks,
            "items": all_tracks
        }


def fetch_via_web_api(
    sp_url: str,
    client_id: str | None = None,
    client_secret: str | None = None,
    access_token: str | None = None,
    use_user_auth: bool = True
) -> PlaylistFetchResult:
    """
    使用 Spotify Web API 取得播放清單
    
    支援兩種認證方式：
    1. 使用者授權 (OAuth PKCE) - 可取得個人化播放清單如 Daily Mix
    2. Client Credentials - 僅能取得公開播放清單
    
    Args:
        sp_url: Spotify 播放清單或專輯 URL
        client_id: Spotify App 的 Client ID
        client_secret: Spotify App 的 Client Secret（可選，PKCE 流程不需要）
        access_token: 已有的 access token（如果有）
        use_user_auth: 是否使用使用者授權流程（預設 True）
    
    Returns:
        PlaylistFetchResult 物件
    """
    # 優先使用參數，其次環境變數
    client_id = client_id or os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = client_secret or os.environ.get("SPOTIFY_CLIENT_SECRET")
    
    if not client_id:
        return PlaylistFetchResult(
            source="web_api",
            url=sp_url,
            playlist_name=None,
            tracks=[],
            error="Spotify Client ID 未設定。請在環境變數設定 SPOTIFY_CLIENT_ID。"
        )
    
    api = SpotifyWebAPI(client_id, client_secret, access_token=access_token)
    
    # 解析 URL
    parsed = api._extract_id_from_url(sp_url)
    if not parsed:
        return PlaylistFetchResult(
            source="web_api",
            url=sp_url,
            playlist_name=None,
            tracks=[],
            error="無法解析 Spotify URL"
        )
    
    item_type, item_id = parsed
    
    # 認證
    if use_user_auth:
        # 使用使用者授權（OAuth PKCE）- 可取得個人化內容
        print("🔐 正在啟動 Spotify 使用者授權流程...")
        print("   瀏覽器將會開啟，請登入您的 Spotify 帳號")
        if not api.authenticate_with_user_auth(timeout=120):
            return PlaylistFetchResult(
                source="web_api",
                url=sp_url,
                playlist_name=None,
                tracks=[],
                error="Spotify 使用者授權失敗。請確認您已登入並授權應用程式。"
            )
    else:
        # 使用 Client Credentials - 僅限公開播放清單
        print("🔐 正在使用 Client Credentials 認證...")
        if not api.authenticate():
            return PlaylistFetchResult(
                source="web_api",
                url=sp_url,
                playlist_name=None,
                tracks=[],
                error="Spotify API 認證失敗，請檢查 Client ID 和 Client Secret"
            )
    
    # 取得資料
    try:
        if item_type == "playlist":
            data = api.get_playlist_tracks(item_id)
        else:
            data = api.get_album_tracks(item_id)
        
        if not data:
            return PlaylistFetchResult(
                source="web_api",
                url=sp_url,
                playlist_name=None,
                tracks=[],
                error="無法取得曲目資料"
            )
        
        # 解析曲目
        tracks = []
        for item in data.get("items", []):
            # 處理播放清單的巢狀結構
            if item_type == "playlist":
                track = item.get("track")
            else:
                track = item
            
            if not track:
                continue
            
            name = track.get("name")
            artists = track.get("artists", [])
            
            if name and artists:
                artist_names = ", ".join([a.get("name", "") for a in artists if a.get("name")])
                tracks.append(f"{name} - {artist_names}")
        
        return PlaylistFetchResult(
            source=f"web_api:{item_type}",
            url=sp_url,
            playlist_name=convert(data.get("name"), "zh-tw") if data.get("name") else None,
            tracks=_dedupe_keep_order(tracks),
            status_code=200
        )
        
    except Exception as exc:
        return PlaylistFetchResult(
            source="web_api",
            url=sp_url,
            playlist_name=None,
            tracks=[],
            error=str(exc)
        )


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
    method: str = "auto",
    client_id: str | None = None,
    client_secret: str | None = None,
    session: requests.Session | None = None
) -> PlaylistFetchResult:
    """
    統一的播放清單取得介面
    
    支援多種取得方式：
    - "auto": 自動選擇（有 API 金鑰就用 API，否則用 embed）
    - "embed": 使用 embed 頁面抓取（最快，無需認證）
    - "api": 使用 Spotify Web API（最穩定，需要 Client ID/Secret）
    
    Args:
        sp_url: Spotify URL
        method: 取得方式 ("auto", "embed", "api")
        client_id: Spotify Client ID（method="api" 時需要）
        client_secret: Spotify Client Secret（method="api" 時需要）
        session: requests Session（method="embed" 時使用）
        
    Returns:
        PlaylistFetchResult 物件
    """
    # 檢查是否有 API 金鑰
    has_api_keys = bool(
        (client_id and client_secret) or 
        (os.environ.get("SPOTIFY_CLIENT_ID") and os.environ.get("SPOTIFY_CLIENT_SECRET"))
    )
    
    # 決定使用哪種方法
    if method == "auto":
        if has_api_keys:
            method = "api"
        else:
            method = "embed"
    
    # 執行對應的方法
    if method == "api":
        return fetch_via_web_api(sp_url, client_id, client_secret)
    else:
        return fetch_legacy_embed_playlist(sp_url, session)
