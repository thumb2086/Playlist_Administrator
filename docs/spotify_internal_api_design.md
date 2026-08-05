# Spotify 內部 API + 匹配機制 — 整合設計文件

## 一、目標

複製 Spotube Spotify 插件的邏輯，整合進我們的 app：
1. 用 Spotify 內部 GraphQL API 取得完整 metadata（歌名、藝人、專輯、封面、歌單）
2. 用 YouTube 搜尋 + 評分排名機制匹配本地歌曲
3. 不需 Spotify Premium，只需用戶登入免費帳號

---

## 二、認證流程（複製插件邏輯）

### 流程圖

```
用戶點擊「登入 Spotify」
        ↓
打開 WebView → accounts.spotify.com 登入頁面
        ↓
用戶登入成功 → URL 重導向到 spotify.com/.../status
        ↓
從 WebView 取得 cookies（sp_dc, sp_t 等）
        ↓
用 sp_dc cookie 呼叫 open.spotify.com/api/token
        ↓
回傳 access_token（1 小時有效）
        ↓
儲存 cookies + access_token → 呼叫內部 API
```

### 關鍵端點

| 用途 | 端點 | 認證 |
|---|---|---|
| 取得 token | `https://open.spotify.com/api/token` | Cookie (sp_dc) + TOTP |
| 取得 server time | `https://open.spotify.com/api/server-time` | 無 |
| GraphQL 查詢 | `https://api-partner.spotify.com/pathfinder/v2/query` | Bearer token + Cookies |
| Nuance secret | `https://gist.githubusercontent.com/raw/22ed9c6ba463899e933427f7de1f0eef/nuances.json` | 無 |

### TOTP 生成

```dart
// 用 nuance secret + server time 生成 TOTP
final serverTime = await getServerTime(); // GET /api/server-time
final nuance = await getNuance();         // GET gist
final totp = generateTOTP(
  secret: nuance.s,        // nuance secret
  timestamp: serverTime,   // server timestamp (seconds)
  period: 30,
  digits: 6,
  algorithm: 'sha1',
);
```

### Token 取得

```dart
// GET https://open.spotify.com/api/token
//   ?reason=transport
//   &productType=web-player
//   &totp=<6位TOTP>
//   &totpServer=<server_time>
//   &totpVer=<nuance_version>
// Headers:
//   Cookie: sp_dc=<sp_dc_value>;
//   User-Agent: <隨機字串>
//
// Response:
//   { "accessToken": "...", "accessTokenExpirationTimestampMs": ..., "isAnonymous": false }
```

---

## 三、GraphQL 查詢

### 端點

`POST https://api-partner.spotify.com/pathfinder/v2/query`

### Headers

```
Authorization: Bearer <access_token>
Cookie: sp_dc=...; sp_t=...; ...
Content-Type: application/json
User-Agent: <隨機 UserAgent>
```

### 查詢範例：搜尋

```graphql
query search($searchTerm: String!, $offset: Int, $limit: Int) {
  searchV2(query: $searchTerm, offset: $offset, limit: $limit) {
    tracksV2 {
      items { item { ... on Track { name uri duration { totalMilliseconds } artists { items { profile { name } uri } } albumOfTrack { name uri coverArt { sources { url width height } } } } } }
      totalCount
    }
    albumsV2 { items { ... on Album { name uri albumType coverArt { sources { url width height } } artists { items { profile { name } uri } } } } }
    artists { items { ... on Artist { profile { name } uri visuals { avatarImage { sources { url width height } } } } } }
    playlists { items { ... on Playlist { name uri images { items { sources { url width height } } } ownerV2 { data { name uri } } } } }
  }
}
```

### 查詢範例：取得歌單曲目

```graphql
query playlistTracks($playlistUri: String!, $offset: Int, $limit: Int) {
  playlistV2(uri: $playlistUri) {
    content {
      items {
        item {
          ... on PlaylistItemTrack {
            track {
              ... on Track {
                name uri
                duration { totalMilliseconds }
                artists { items { profile { name } uri } }
                albumOfTrack {
                  name uri
                  coverArt { sources { url width height } }
                  artists { items { profile { name } uri } }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

---

## 四、匹配機制

### 流程

```
Spotify metadata (title, artists, duration_ms)
        ↓
建構搜尋 query
        ↓
YouTube 搜尋 → 拿到 5-10 個候選
        ↓
評分排名 → 選最佳匹配
        ↓
YouTube oEmbed 驗證（預先確認）
        ↓
下載
        ↓
快取 videoId
```

### 搜尋 Query 建構

```dart
// 1. 基本 query：藝人 + 歌名
String buildQuery(String artist, String title) {
  return '$artist $title';
}

// 2. 清理 query（移除噪音）
String cleanQuery(String query) {
  return query
    .replaceAll(RegExp(r'\(.*?\)'), '')      // 移除括號
    .replaceAll(RegExp(r'\[.*?\]'), '')      // 移除方括號
    .replaceAll(RegExp(r'official.*', caseSensitive: false), '')
    .replaceAll(RegExp(r'feat\.|ft\.', caseSensitive: false), '')
    .replaceAll(RegExp(r'\s+'), ' ')
    .trim();
}

// 3. 多候選策略
List<String> buildCandidates(String artist, String title) {
  return [
    '$artist $title',           // 藝人 + 歌名
    '$title',                   // 只有歌名（找 cover/remix）
    '$artist $title official',  // 強調官方
  ];
}
```

### 評分演算法

```dart
int scoreResult(YouTubeSearchResult result, SpotifyTrack track) {
  int score = 0;

  // 歌名匹配（+3）
  if (result.title.toLowerCase().contains(track.title.toLowerCase())) {
    score += 3;
  }

  // 藝人匹配（+1 per artist）
  for (final artist in track.artists) {
    if (result.title.toLowerCase().contains(artist.toLowerCase()) ||
        result.channel.toLowerCase().contains(artist.toLowerCase())) {
      score += 1;
    }
  }

  // 官方內容（+2）
  if (_isOfficial(result)) {
    score += 2;
  }

  // 時長匹配（±10秒 → +3）
  final durationDiff = (result.duration - track.durationMs).abs();
  if (durationDiff < 10000) {
    score += 3;
  }

  return score;
}

bool _isOfficial(YouTubeSearchResult result) {
  final title = result.title.toLowerCase();
  return title.contains('official') ||
         title.contains('music video') ||
         title.contains('lyric') ||
         title.contains('visualizer');
}
```

### YouTube oEmbed 驗證

```dart
// 在下載前，用 oEmbed 預先確認
Future<bool> verifyCandidate(String videoId) async {
  final resp = await http.get(
    Uri.parse('https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=$videoId&format=json'),
  );
  if (resp.statusCode != 200) return false;
  final data = jsonDecode(resp.body);
  // 確認標題合理（不含 "cover", "remix" 等非官方標記）
  return !data['title'].toLowerCase().contains('cover');
}
```

---

## 五、資料模型

### SpotifyTrack

```dart
class SpotifyTrack {
  final String id;          // Spotify URI
  final String title;
  final List<String> artists;
  final String album;
  final String? coverUrl;   // 封面 URL
  final int durationMs;
  final String? isrcCode;   // ISRC（如有）
}
```

### SpotifyPlaylist

```dart
class SpotifyPlaylist {
  final String id;
  final String title;
  final String? description;
  final String? coverUrl;
  final int trackCount;
  final String owner;
}
```

### YouTubeCandidate

```dart
class YouTubeCandidate {
  final String videoId;
  final String title;
  final String channel;
  final int durationMs;
  final String? thumbnail;
  final int score;           // 評分
}
```

---

## 六、架構圖

```
┌─────────────────────────────────────────────────┐
│  UI Layer                                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ 歌單頁面  │  │ 搜尋頁面  │  │ 播放器   │      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘      │
│       │              │              │            │
│  ┌────┴──────────────┴──────────────┴────┐      │
│  │         SpotifyService               │      │
│  │  ┌─────────────┐  ┌──────────────┐   │      │
│  │  │ AuthManager │  │ GraphQLClient│   │      │
│  │  │ (cookie+TOTP│  │ (internal API│   │      │
│  │  │  token)     │  │  queries)    │   │      │
│  │  └──────┬──────┘  └──────┬───────┘   │      │
│  │         │                │            │      │
│  │  ┌──────┴────────────────┴───────┐   │      │
│  │  │       MatchService            │   │      │
│  │  │  YouTube search + ranking     │   │      │
│  │  │  + oEmbed verification        │   │      │
│  │  └───────────────────────────────┘   │      │
│  └──────────────────────────────────────┘      │
└─────────────────────────────────────────────────┘
```

---

## 七、實作計畫

### Phase 1：認證 + WebView（1 週）
- 加入 `webview_flutter` 套件
- 實作 Spotify 登入頁面
- 取得 cookies
- 實作 TOTP 生成
- 取得 access token
- 儲存 session

### Phase 2：GraphQL 客戶端（1 週）
- 實作 GraphQL 查詢（搜尋、歌單、曲目、專輯）
- 整合 SpotifyTrack 模型
- 測試各端點

### Phase 3：匹配機制（1 週）
- YouTube 搜尋整合
- 評分演算法
- oEmbed 驗證
- 快取機制

### Phase 4：整合 UI（1 週）
- 歌單頁面改用 Spotify API
- 搜尋頁面改用 Spotify API
- 播放器封面顯示

---

## 九、風險與限制

| 風險 | 影響 | 緩解 |
|---|---|---|
| Spotify 改 API | 功能失效 | 監控 API 變動，定期更新 |
| TOTP nuance 變動 | 認證失敗 | 從 gist 自動取得最新 nuance |
| Cookie 過期 | 需重新登入 | 定期刷新 token（1小時） |
| 速率限制 | 暫時無法使用 | 實作 retry + backoff |
| WebView 相容性 | 部分平台登入失敗 | 提供 Cookie 手動輸入備案 |

---

## 十、實作順序

1. 先實作 TOTP + Token 取得（用 curl 測試）
2. 再實作 GraphQL 查詢（用 curl 測試）
3. 最後加 WebView + UI 整合

確認 API 可用後再寫 Dart code。
