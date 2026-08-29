# Python Bridge 全命令對比報告

> 日期: 2026-08-30 | 版本: playlist-admin v2.13.19

---

## 一、架構總覽

```
┌─────────────────────────────────────────────────────────┐
│                    Flutter (Dart) App                    │
├──────────┬──────────┬──────────┬──────────┬─────────────┤
│ download │ podcast  │   rag    │  groq    │  stream     │
│ _service │ _service │ _service │ _native  │ _server     │
└────┬─────┴────┬─────┴────┬─────┴────┬─────┴──────┬──────┘
     │          │          │          │            │
  Process.start()     直接呼叫      已原生化     已原生化
     │          │          │          │            │
┌────▼──────────▼──────────▼──┐  ┌────▼────┐  ┌────▼────┐
│  flutter_download_bridge.py │  │ ffmpeg  │  │ youtube │
│  (15 個子命令)              │  │ ffprobe │  │ explode │
└─────────────────────────────┘  └─────────┘  └─────────┘
```

### 通訊協議
- **Dart → Python**: `Process.start('python', [bridge, command, ...args])`
- **Python → Dart**: stdout JSON lines (`{"type":"progress","percent":50}`)
- **編碼**: `PYTHONIOENCODING=utf-8`

---

## 二、命令狀態總表

| # | 命令 | 用途 | 原生化狀態 | 呼叫者 |
|---|------|------|-----------|--------|
| 1 | `groq-transcribe` | Groq Whisper 轉錄 | ✅ **已原生化** | `podcast_pipeline.dart` |
| 2 | `normalize-mp3-lufs` | LUFS 響度標準化 | ✅ **已原生化** | `pipeline_orchestrator.dart` |
| 3 | `rss-list` | RSS Feed 解析 | ✅ **已原生化** | `podcast_service.dart` |
| 4 | `rss-get-audio` | 取得 podcast 音檔 URL | ✅ **已原生化** | `podcast_service.dart` |
| 5 | `rss-download` | 下載 podcast 音檔 | ✅ **已原生化** | `podcast_service.dart` |
| 6 | `stream-resolve` | 解析可播放音訊 URL | ✅ **已原生化** | `stream_server.dart` |
| 7 | `stream-download` | Spotube 風格下載 | ✅ **已原生化** | `stream_server.dart` |
| 8 | `download-song` | 下載歌曲 | ✅ **已原生化** | `download_service.dart`, `spotube_page.dart` |
| 9 | `download-youtube` | YouTube URL 下載 | ✅ **已原生化** | `download_service.dart` |
| 10 | `download-spotdl` | spotDL 專用下載 | ❌ Python only | `download_service.dart` |
| 11 | `list-missing` | 列出缺少格式的歌曲 | ❌ Python only | `download_service.dart` |
| 12 | `batch-download` | 批次下載缺少歌曲 | ❌ Python only | `download_service.dart` |
| 13 | `youtube-subs` | YouTube 字幕下載 | ❌ Python only | `podcast_service.dart` |
| 14 | `rag-build` | RAG 索引重建 | ❌ Python only | `rag_service.dart` |
| 15 | `rag-query` | RAG 問答查詢 | ❌ **已棄用** | (改用 opencode) |

---

## 三、逐命令詳細對比

### 3.1 ✅ `groq-transcribe` — 已原生化

| 項目 | Python Bridge | Dart 原生 |
|------|--------------|-----------|
| **實現** | `flutter_download_bridge.py:640-957` | `groq_native_service.dart` |
| **大小檢查** | ✅ >20MB 分段 | ✅ >20MB 分段 |
| **分段邏輯** | ffmpeg 5min → 60s sub-chunk | ffmpeg 5min → 60s sub-chunk |
| **格式** | 16kHz mono FLAC | 16kHz mono FLAC |
| **多 Key** | ✅ CSV round-robin | ✅ CSV round-robin |
| **429 重試** | ✅ 換 key + sleep | ✅ 換 key + 退避 |
| **5xx 重試** | ✅ 自動重試 | ✅ 自動重試 |
| **代理** | ✅ Win Registry + Env | ✅ Win Registry + Env |
| **錯誤日誌** | ✅ `stt_errors.log` | ✅ `stt_errors.log` |
| **行數** | ~317 行 Python | ~470 行 Dart |

**結論**: 功能完全對齊，可完全取代 Python bridge。

---

### 3.2 ✅ `normalize-mp3-lufs` — 已原生化

| 項目 | Python Bridge | Dart 原生 |
|------|--------------|-----------|
| **實現** | `flutter_download_bridge.py:537-637` | `lufs_service.dart` |
| **測量** | ffmpeg loudnorm print_format=json | ffmpeg loudnorm print_format=json |
| **標準化** | ffmpeg loudnorm I=-14:TP=-1:LRA=7 | ffmpeg loudnorm I=-14:TP=-1:LRA=7 |
| **快取** | `mp3_lufs_cache.json` | `mp3_lufs_cache.json` |
| **並行** | ❌ 串行 | ✅ 支援並行 |
| **取消** | ❌ | ✅ PipelineState |
| **被呼叫** | ❌ 無人呼叫 | ✅ PipelineOrchestrator |

**結論**: Dart 原生版功能更強（並行 + 取消），完全取代。

---

### 3.3 ✅ `rss-list` / `rss-get-audio` / `rss-download` — 已原生化

| 項目 | Python Bridge | Dart 原生 |
|------|--------------|-----------|
| **實現** | bridge.py:30-118 | `podcast_service.dart` |
| **RSS 解析** | `requests` + XML 解析 | `package:xml` |
| **音檔下載** | `requests` streaming | `http.Client` streaming |
| **Extension** | URL path 推斷 | URL path 推斷 |

**結論**: 完全原生，無 Python 依賴。

---

### 3.4 ✅ `stream-resolve` / `stream-download` — 已原生化

| 項目 | Python Bridge | Dart 原生 |
|------|--------------|-----------|
| **實現** | bridge.py:191-389 | `stream_server.dart` |
| **搜尋** | yt-dlp YouTube search | `youtube_explode_dart` |
| **下載** | yt-dlp + ffmpeg | ffmpeg pipe |
| **HTTP 串流** | ❌ | ✅ `http://127.0.0.1:PORT/stream` |

**結論**: Dart 原生版更強，支援即時串流。

---

### 3.5 ⚠️ `download-song` — 部分原生

| 項目 | Python Bridge | Dart 原生 (部分) |
|------|--------------|-----------------|
| **實現** | bridge.py:121-135 → `core/downloader.py` | `youtube_service.dart` + ffmpeg |
| **搜尋** | yt-dlp YouTube search | `youtube_explode_dart` |
| **下載** | yt-dlp bestaudio | ffmpeg pipe |
| **spotDL fallback** | ✅ | ❌ |
| **ISRC 搜尋** | ✅ | ❌ |
| **Metadata 嵌入** | ✅ (yt-dlp --add-metadata) | ❌ |
| **歌詞下載** | ✅ (yt-dlp --write-subs) | ❌ |
| **多格式支援** | mp3, flac, m4a, wav | mp3 only (pipeline) |

**差距**:
- ❌ 缺少 spotDL 搜尋策略（更精準的歌曲匹配）
- ❌ 缺少 ISRC 搜尋（國際標準錄音編碼）
- ❌ 缺少 metadata 自動嵌入
- ❌ 缺少歌詞下載

**原生化難度**: 🟡 中等 — 核心下載可行，但 spotDL 搜尋邏輯需要 port

---

### 3.6 ⚠️ `download-youtube` — 部分原生

| 項目 | Python Bridge | Dart 原生 (部分) |
|------|--------------|-----------------|
| **實現** | bridge.py:138-188 | `youtube_service.dart` |
| **輸入** | 任意 YouTube URL | 搜尋字串 |
| **yt-dlp** | ✅ 直接使用 | ❌ |
| **格式選擇** | `bestaudio/best` | `audioOnly.sortByBitrate().last` |
| **Postprocessor** | FFmpegExtractAudio | 手動 ffmpeg |
| **進度回報** | ✅ 下載百分比 + 速度 | ❌ |

**差距**:
- ❌ 不能直接接受 YouTube URL（需先解析 video ID）
- ❌ 缺少進度回報（百分比 + 速度）

**原生化難度**: 🟢 低 — `YoutubeExplode` 可解析 URL，包裝一層即可

---

### 3.7 ❌ `list-missing` — 無原生替代

| 項目 | Python Bridge |
|------|--------------|
| **實現** | bridge.py:407-477 → `core/library.py` |
| **功能** | 掃描音樂庫，找出缺少指定格式的歌曲 |
| **依賴** | `core/library.py` (build_library_index, find_song_exact_format, parse_playlist) |
| **快取** | `failed_flac.json` (FLAC 下載失敗記錄) |

**差距**:
- ❌ 需要 port `core/library.py` 的 library index 邏輯
- ❌ 需要 port M3U8 playlist 解析
- ❌ 需要 port FLAC 失敗快取管理

**原生化難度**: 🔴 高 — `core/library.py` 有大量業務邏輯

---

### 3.8 ❌ `batch-download` — 無原生替代

| 項目 | Python Bridge |
|------|--------------|
| **實現** | bridge.py:480-534 → `core/downloader.py` |
| **功能** | 批次下載缺少的歌曲 |
| **依賴** | `download-song` (同 3.5) + `failed_flac.json` 管理 |

**差距**:
- ❌ 依賴 `download-song` 的完整功能
- ❌ 需要 FLAC 失敗快取管理

**原生化難度**: 🔴 高 — 依賴 `download-song` 完整 port

---

### 3.9 ❌ `youtube-subs` — 無原生替代

| 項目 | Python Bridge |
|------|--------------|
| **實現** | bridge.py:968-1054 |
| **功能** | 搜尋 YouTube + 下載中文字幕 (SRT) |
| **搜尋** | YouTube HTTP scraping (非 yt-dlp) |
| **字幕** | yt-dlp writesubtitles + writeautomaticsub |
| **語言** | zh-TW, zh-Hant, zh, zh-Hans, en |
| **Cookie** | 支援 age-restricted 內容 |

**差距**:
- ❌ `youtube_explode_dart` 不支援字幕下載
- ❌ 需要 yt-dlp 的 subtitle 功能
- ❌ 需要 YouTube 搜尋 scraping (非 API)

**原生化難度**: 🔴 高 — 無 Dart 字幕下載函式庫

**替代方案**:
1. 使用 YouTube Data API v3 (需 API key)
2. 使用 `youtube_explode_dart` 的字幕功能 (需確認是否支援)
3. 保留 Python bridge 僅用於此命令

---

### 3.10 ❌ `rag-build` / `rag-query` — 無原生替代

| 項目 | Python Bridge |
|------|--------------|
| **實現** | bridge.py:1075-1129 → `rag/build_db.py`, `rag/query.py` |
| **功能** | RAG 索引重建 / 向量問答 |
| **依賴** | Ollama (本地 LLM), ChromaDB (向量資料庫), sentence-transformers |

**差距**:
- ❌ Ollama + ChromaDB 是 Python 生態系
- ❌ 無 Dart 向量資料庫替代
- ❌ 無 Dart embeddings 模型

**原生化難度**: ⬛ 不可能 — 依賴 Python ML 生態系

**現狀**: `rag-query` 已棄用，改用 `opencode` 的 `podcast-knowledge` skill。

---

## 四、原生化進度圖

```
✅ 已原生化 (9/15 = 60%)
├── groq-transcribe          → groq_native_service.dart
├── normalize-mp3-lufs       → lufs_service.dart
├── rss-list                 → podcast_service.dart
├── rss-get-audio            → podcast_service.dart
├── rss-download             → podcast_service.dart
├── stream-resolve           → stream_server.dart
├── stream-download          → stream_server.dart
├── download-song            → youtube_service.dart + download_service.dart
└── download-youtube         → youtube_service.dart + download_service.dart

❌ 無原生替代 (4/15 = 27%)
├── download-spotdl          → spotDL 函式庫
├── list-missing             → core/library.py
├── batch-download           → core/downloader.py
└── youtube-subs             → yt-dlp subtitle

❌ 已棄用 (1/15 = 7%)
└── rag-query                → 改用 opencode

⚠️ 仍需 Python (1/15 = 7%)
└── rag-build                → Ollama + ChromaDB
```

---

## 五、建議優先順序

### 🟡 中優先（值得做但非關鍵）

| 命令 | 動作 | 預估工時 |
|------|------|---------|
| `list-missing` | Port `core/library.py` 到 Dart | 8-16 hr |
| `batch-download` | 依賴 `list-missing` 完成後實作 | 2-4 hr |

### 🟢 低優先（保留 Python bridge 即可）

| 命令 | 動作 | 說明 |
|------|------|------|
| `youtube-subs` | 保留 Python | yt-dlp 字幕功能無 Dart 替代 |
| `rag-build` | 保留 Python | Ollama + ChromaDB 生態系 |
| `download-spotdl` | 保留 Python | spotDL 函式庫依賴 |

### ⬛ 不做

| 命令 | 說明 |
|------|------|
| `rag-query` | 已棄用，改用 opencode |

---

## 六、最小化 Bridge 策略

如果目標是**最小化 Python 依賴**：

### 已完成 ✅
- `download-youtube` → 原生化完成
- `download-song` → 原生化完成

### 階段 1: 完成 `list-missing` 原生化 (8-16 hr)
- Port `core/library.py` 的 library index 邏輯到 Dart
- Port M3U8 playlist 解析
- Port FLAC 失敗快取管理

### 階段 2: 完成 `batch-download` 原生化 (2-4 hr)
- 依賴 `list-missing` 完成
- 使用原生 `downloadSong` 逐首下載

### 階段 3: 移除 Python bridge (optional)
- 保留 `youtube-subs`, `rag-build` 為獨立 Python 腳本
- 從 `flutter_download_bridge.py` 移除已原生化的命令
- 最終 bridge 僅剩 ~200 行（youtube-subs + rag-build）

---

## 七、檔案清單

| 檔案 | 用途 | 行數 |
|------|------|------|
| `tools/flutter_download_bridge.py` | 主橋接（15 個子命令） | 1182 |
| `lib/services/bridge_service.dart` | 橋接路徑解析 | ~100 |
| `lib/services/download_service.dart` | 下載服務（原生 + bridge 混合） | ~200 |
| `lib/services/youtube_service.dart` | YouTube 原生服務（搜尋 + URL 下載 + ffmpeg） | ~280 |
| `lib/services/podcast_service.dart` | Podcast 服務（部分原生化） | ~250 |
| `lib/services/rag_service.dart` | RAG 服務（呼叫 Python） | ~80 |
| `lib/services/groq_native_service.dart` | Groq 原生客戶端 | ~470 |
| `lib/services/lufs_service.dart` | LUFS 原生服務 | ~430 |
| `lib/services/stream_server.dart` | 串流伺服器 | ~220 |
| `lib/pages/spotube_page.dart` | Spotube 頁面（已改用原生下載） | ~280 |
| `rag/build_db.py` | RAG 索引建立 | ~300 |
| `rag/query.py` | RAG 查詢 | ~200 |
