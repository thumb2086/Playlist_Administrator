# Spotube 邏輯整合報告

## 一、Spotube 架構概覽

Spotube 是跨平台音樂串流 app（Flutter），核心設計：

```
插件系統 (Hetu Script) → Spotify metadata（歌名、藝人、封面、歌詞）
         ↓
YouTube 引擎 (yt-dlp / YouTubeExplode / NewPipe)
         ↓
搜尋 → 匹配排名 → 下載 → metadata 寫入 → 播放
```

**關鍵套件：**
- `youtube_explode_dart` — YouTube 搜尋/下載（純 Dart，無需 API key）
- `metadata_god` — 讀寫 MP3/M4A 的 ID3 tag（title、artist、album、封面）
- `yt_dlp_dart` — yt-dlp 的 Dart wrapper
- `drift` — SQLite ORM，用於快取
- `lrc` — LRC 歌詞格式解析
- `fuzzywuzzy` — 模糊字串匹配
- `dio` — HTTP 下載（支援分塊、進度回報）

---

## 二、可整合的邏輯

### 1. Spotify Metadata 擷取（優先級：高）

**現狀：** 我們用 Spotify Embed 網頁爬蟲，只能拿到歌單列表。

**Spotube 做法：** 用 Hetu 插件從 Spotify API 拿 metadata（歌名、藝人、專輯、封面 URL）。

**建議改寫：** 直接用 Dart 呼叫 Spotify Web API（不需 OAuth，用內建 client token）：
- 端點：`https://api.spotify.com/v1/tracks/{id}`
- 拿到：title、artist、album、album art URL、duration
- 比我們現在的 Embed 爬蟲更穩定、更快

### 2. 封面圖嵌入（優先級：高）

**現狀：** 播放器顯示預設音樂圖示，沒有封面。

**Spotube 做法：**
1. 從 Spotify API 拿 album art URL
2. 用 `flutter_cache_manager` 下載並快取
3. 用 `metadata_god` 嵌入 M4A/MP3 的 ID3 tag

**建議改寫：** 用 ffmpeg 嵌入封面（我們已有 ffmpeg）：
```bash
ffmpeg -i input.mp3 -i cover.jpg -map 0:a -map 1:v -c:a copy -c:v mjpeg -id3v2_version 3 -metadata:s:v albumartwork="" output.mp3
```

### 3. 搜尋結果排名演算法（優先級：中）

**現狀：** 我們用 fuzzy matching 比對歌單歌曲與本地檔案。

**Spotube 的 `rankResults()`：**
- 藝人名匹配 +1
- 歌名包含藝人 +1
- 歌名完全匹配 +3
- 含 "official" 標記 +1
- 模糊匹配分數

**建議：** 加入我們的 matching 邏輯，減少誤判。

### 4. 檔名清理邏輯（優先級：低）

**Spotube 的 `sanitizeFilename()`：**
- 移除控制字元（\0-\x1f）
- 移除 Windows 保留字元（CON、PRN 等）
- 移除非法字元（/\:*?"<>|）
- 限制長度 255 字元
- 處理尾端空格和點

**建議：** 整合到我們的 `normalizeFileName`。

### 5. 同步歌詞 LRCLib（優先級：低）

**Spotube 做法：** 用 LRCLib API 查詢同步歌詞，SQLite 快取。

**建議：** 我們播放器已有 LRC 解析，可加入 LRCLib API 作為線上歌詞來源。

---

## 三、不建議整合的

- **Hetu 插件系統** — 太複雜，我們不需要插件架構
- **YouTube 引擎切換** — 我們已用 yt-dlp，夠用
- **Riverpod 狀態管理** — 我們用 setState，不需改
- **drift SQLite ORM** — 我們的快取機制夠用

---

## 四、實施計畫

### Phase 1：Spotify Metadata + 封面（1-2 週）
- 新增 `SpotifyApiService`：用 Dart http 呼叫 Spotify API
- 拿到 track metadata（title、artist、album、art URL）
- 下載封面圖並用 ffmpeg 嵌入 MP3/M4A
- 播放器顯示封面

### Phase 2：搜尋排名改善（1 週）
- 整合 Spotube 的 ranking 演算法
- 改善歌單匹配準確度

### Phase 3：歌詞 + 檔名清理（1 週）
- 加入 LRCLib API 歌詞查詢
- 整合檔名清理邏輯

---

## 五、Spotube 原始碼位置

```
C:\Users\CPXru\Desktop\thumb\program\spotube_source\
├── lib/
│   ├── services/          ← YouTube 引擎、metadata 擷取
│   ├── provider/          ← 下載管理、歌詞
│   ├── models/            ← 資料模型
│   ├── utils/             ← 檔名清理、搜尋建構
│   └── pages/             ← UI 頁面
└── pubspec.yaml           ← 套件依賴
```

關鍵參考文件：
- `lib/services/sourced_track/sourced_track.dart` — 搜尋+排名邏輯
- `lib/utils/service_utils.dart` — 檔名清理、搜尋建構
- `lib/provider/download_manager_provider.dart` — 下載+metadata 寫入
- `lib/provider/lyrics/synced.dart` — LRCLib 歌詞
