
# Playlist Administrator 指令說明書

## CLI（與 GUI 共用同一引擎）

`playlist-admin`（npm 包）**只是啟動器** — 真正的 pipeline / podcast / spotube
邏輯全部在 Flutter app 內（`lib/cli_main.dart`），跟 GUI 共用同一份實作。
先 build 一次：

```bash
flutter build windows --release
```

之後：

```bash
playlist-admin pipeline                   # 完整流程（轉檔 → 爬取 → 清理 → 分類 → metadata → LUFS）
playlist-admin pipeline --step N          # 從第 N 步開始
playlist-admin podcast                    # Podcast Pipeline（RSS → YT 字幕 → Groq 逐字稿）
playlist-admin status                     # 顯示狀態
playlist-admin spotube-download <name>    # 下載單一歌單
playlist-admin spotube-download-all       # 下載所有歌單
playlist-admin spotube-move               # 搬移 M4A
playlist-admin spotube-cleanup            # 清除孤兒 MP3
playlist-admin rag build [--reset]        # 建立 podcast RAG 向量庫（Ollama + ChromaDB）
playlist-admin rag query "問題" [--topk N] # 查 podcast 逐字稿語意
```

- 直接執行 exe 也可以：`playlist-admin.exe pipeline`（同一份引擎）。
- RAG 細節見 `rag/README.md`。

---

## CLI 指令（Dart）

### 完整流程

```bash
dart run lib/cli_main.dart pipeline
```

依序執行：轉檔 → 爬取 Spotify → 清理遺失歌曲 → 分類未收錄歌曲 → 增強 Metadata。

### 只看狀態

```bash
dart run lib/cli_main.dart status
```

顯示：
- 資料庫歌曲總數（MP3 / M4A / FLAC）
- 各歌單的匹配狀況（已完成 / 缺少）
- 空間節省統計

### 爬取 Spotify 歌單

```bash
dart run lib/cli_main.dart scrape
```

爬取 `config.json` 中所有 Spotify URL，比對本地檔案，輸出 M3U8 播放清單。

### 轉檔 M4A → MP3

```bash
dart run lib/cli_main.dart convert
```

掃描 Music/m4a 目錄，將尚未有對應 MP3 的 M4A 轉檔（需要 ffmpeg）。

### 清理遺失歌曲

```bash
dart run lib/cli_main.dart prune
```

檢查 M3U8 歌單中所有檔案是否存在磁碟，移除已刪除的條目。

### 整理未分類歌曲

```bash
dart run lib/cli_main.dart unsorted
```

掃描音樂庫中所有未被任何歌單收錄的歌曲，寫入 `_Unsorted.m3u8`。

---

## Spotube 自動化

Spotube 自動化透過 Win32 API 操作 Spotube GUI 來自動下載歌單。

### 校準點擊座標（必要步驟）

由於每個人的螢幕解析度、視窗位置不同，Spotube 操作需要先校準按鈕位置。

**方法一：Python 校準工具（建議）**

```bash
pip install pywin32
python tools/spotube_calibrate.py
```

依序將滑鼠移到 9 個目標元素上，按下 Enter 記錄位置：

| 步驟 | 名稱 | 目標元素 |
|---|---|---|
| 1 | `sidebar_library` | 側邊欄 Library 圖示 |
| 2 | `library_filter` | Library 頁面搜尋/過濾輸入框 |
| 3 | `first_playlist_card` | 過濾後出現的第一個歌單卡片 |
| 4 | `three_dot_menu` | 歌單頁面右上角的三點選單（⋯） |
| 5 | `download_all_offset` | 選單中的「下載全部」（自動計算偏移） |
| 6 | `confirm_button` | 確認對話框的「同意/Download」 |
| 7 | `skip_detect` | 跳過對話框上一個明顯的白色像素（用於偵測） |
| 8 | `skip` |「略過 / Skip」按鈕 |
| 9 | `skip_all` |「全部略過 / Skip All」按鈕 |

完成後座標自動寫入 `config.json` 的 `spotube_coords`。

**方法二：Flutter 內建校準**

```bash
dart run lib/calibrate.dart
```

### 下載單一歌單

```bash
dart run lib/cli_main.dart spotube-download "Daily Mix 1"
```

程式會：
1. 啟動/啟用 Spotube
2. 最大化視窗
3. 點擊側邊欄 Library
4. 在搜尋框輸入歌單名稱
5. 點擊第一個結果
6. 點擊三點選單 → 下載全部 → 確認
7. 監測跳過對話框（最多 30 秒），自動按 Skip → Skip All
8. 下載完成後最小化

### 下載所有歌單

```bash
dart run lib/cli_main.dart spotube-download-all
```

依序對 `config.json` 中所有 `urlNames` 執行下載。  
已下載過的歌單會記錄在 `lastUpdated`，不會重複下載。

### 搬移下載檔案

```bash
dart run lib/cli_main.dart spotube-move
```

將 Spotube 預設下載目錄 `%USERPROFILE%/Downloads/Spotube` 中的音檔搬到 `Music/m4a`。

### 重置下載紀錄

```bash
dart run lib/cli_main.dart spotube-reset
```

清除所有下載記錄，讓所有歌單可以被重新下載。

---

## 設定檔說明

主設定檔位置：`{base_path}/config.json`

### 主要欄位

| 欄位 | 類型 | 說明 |
|---|---|---|
| `base_path` | string | 資料庫根目錄 |
| `library_path` | string | 音樂庫目錄（預設 `{base_path}/Music`） |
| `playlists_path` | string | M3U8 歌單目錄（預設 `{base_path}/Playlists`） |
| `url_names` | object | Spotify URL → 歌單名稱 對應表 |
| `search_names` | object | 搜尋別名對應表（中文/英文） |
| `spotube_coords` | object | Spotube 自動化按鈕座標 |
| `last_updated` | object | 各歌單最後同步日期 |
| `audio_format` | string | 目標音檔格式（`mp3`, `flac`） |
| `max_threads` | int | 轉檔執行緒數 |
| `ffmpeg_path` | string | FFmpeg 執行檔路徑 |
| `spotube_exe_path` | string | Spotube 執行檔路徑 |
| `spotube_exact_match` | bool | 是否要求檔名與 Spotify 完全一致 |
| `enable_metadata_enrichment` | bool | 是否啟用 Metadata 增強（重新命名檔案） |

### 搜尋別名（search_names）

用於中英文歌名/藝人名的模糊比對。例如：

```json
{
  "search_names": {
    "日本流行樂合輯": "J-Pop Mix",
    "韓國流行樂合輯": "K-Pop Mix",
    "每週新發現": "Discover Daily"
  }
}
```

可在設定頁面「搜尋別名」區塊編輯。

---

## M3U8 格式

所有歌單儲存為 UTF-8 編碼的 `.m3u8` 檔案：

```
#EXTM3U
#EXTINF:-1,YOASOBI - 夜に駆ける
../Music/YOASOBI - 夜に駆ける.mp3
#EXTINF:-1,Ado - 唱
../Music/Ado - 唱.mp3
```

- 路徑為**相對路徑**（相對於 Playlists 目錄）
- 使用**正斜線 `/`** 作為路徑分隔符號
- 只有**匹配到的歌曲**才會寫入（unmatched 不會被寫入）
- 換行使用 LF（`\n`）

---

## 開發用指令

### Flutter 分析

```bash
flutter analyze
```

### 編譯 Windows Release

```bash
flutter build windows --release
```

輸出：`build/windows/x64/runner/Release/playlist-admin.exe`

### 編譯 Windows Debug

```bash
flutter build windows --debug
```

輸出：`build/windows/x64/runner/Debug/playlist-admin.exe`

### 版本標籤

發版只推 tag 即可，**不需**更新 pubspec.yaml 或任何檔案，
GitHub Actions 會自動從 tag 讀取版本號填入編譯：

```bash
# 1. 先 commit 程式碼修正（不用動版本號）
git commit -am "修復 xxx"

# 2. 直接打 tag 並推送
git tag v2.6.66
git push origin v2.6.66
```

- tag 名稱格式：`vX.Y.Z`（例如 `v2.6.66`）
- 推送後 CI 會自動：`flutter build windows --release --dart-define=APP_VERSION=<版本號>` → Inno Setup 打包 → 上傳 GitHub Release
- `pubspec.yaml` 的 `version` 欄位僅供分支推播（非 tag）時備用，發版流程可忽略
