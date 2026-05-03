# Playlist Administrator

![Version](https://img.shields.io/badge/version-1.5.0-blue)

本機音樂庫維護工具：建立/更新 Spotify 播放清單、管理匯出、整理音樂。預設流程不下載音樂檔。

## 功能概覽

- 透過 Spotify embed 頁面建立/更新 `.m3u8` 播放清單（支援 playlist/album/artist/track URL，無需認證）。
- 移除播放清單中已不存在的檔案項目。
- 必要時把未分類歌曲移到 `_Unsorted`。
- 將選取播放清單匯出到 USB/SD（Copy 或 Mirror）。
- Tkinter 桌面 UI 內建播放器與歌詞（`.lrc`）。
- Tkinter 桌面 UI 內建播放器、歌詞與設定視窗。
- 命令列介面供自動化使用。

## 快速開始

1. 安裝相依套件：
   ```bash
   pip install -r requirements.txt
   ```
2. 啟動桌面介面：
   ```bash
   python main.py
   ```
3. 設定 Base Folder（音樂庫根目錄）。應包含：
   - `Music/` - 您的音訊檔案（MP3、FLAC 等）
   - `Playlists/` - 播放清單檔案（.m3u8）
4. 加入 Spotify URL，按 Start/Update。

## CLI 使用方式

```bash
# 更新音樂庫與播放清單
python cli.py update

# 只抓取 Spotify URL
python cli.py scrape --url "https://open.spotify.com/playlist/..."

# 透過 Embed 取得播放清單曲目
python cli.py fetch-playlist "https://open.spotify.com/playlist/..." --show-tracks

# 測試本地匹配
python cli.py match --file "_spotify_debug.txt"
```

## 安裝（EXE）

GitHub Actions 會自動編譯 Windows 安裝版。請到 GitHub Releases 下載最新安裝檔並執行安裝。

## 設定檔

設定檔存放在使用者目錄，並可寫入 base folder：

- 主設定：`%LOCALAPPDATA%\Playlist Administrator\data\config.json`
- 若設定 `base_path`，會在 base folder 內建立 `config.json` 並以其為主。App data 的設定檔只保留 `base_path` 指向。

重要設定：

- `base_path`: 音樂庫根目錄。`Music`、`Playlists`、`USB_Output` 由此衍生。
- `ffmpeg_path`: `ffmpeg` 路徑（選用，用於音訊轉換）。
- `spotube_folder_name`: 音樂庫內 Spotube 目錄名稱（選用）。
- `spotube_exact_match`: 使用簡單檔名匹配 Spotube 下載（預設：True）。

## 專案結構

- `main.py`: Tkinter 入口。
- `cli.py`: 命令列介面。
- `core/`: 核心流程（播放清單、Spotify 抓取、同步/匯出、metadata）。
- `gui/`: Tkinter 介面與設定視窗。
- `utils/`: 設定與工具、i18n。
- `tools/`: 小工具腳本。
- `docs/`: 文件。
- `PLAYBACK_FIX_README.md`: Windows 播放問題修正說明。
- `YTDLP_UPDATE_GUIDE.md`: yt-dlp 更新步驟。

## 備註

- Spotify 抓取依賴 embed 頁面，需要網路連線，無需認證。
- 播放清單預設使用 MP3 檔案。
- 下載相關工具（yt-dlp、DAB、spotDL）在 `core/downloader.py`，但預設更新流程未使用。
- Tkinter 是目前唯一支援的 UI 入口。
