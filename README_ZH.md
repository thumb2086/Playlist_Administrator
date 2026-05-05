# Playlist Administrator

![Version](https://img.shields.io/badge/version-1.6.0-blue)

Playlist Administrator 是一個 Windows 桌面工具，用來維護以 Spotify 播放清單與 Spotube 下載檔為核心的本機音樂庫。它可以更新 Spotify 來源的 `.m3u8` 播放清單、把 Spotube M4A 轉成 MP3、追蹤被 Spotify 歌單移除的歌曲、匯出播放清單，並顯示音樂庫統計資料。

預設更新流程不會從 Spotify 下載新音訊，它會整理你本機已經存在的音樂檔。

## 功能重點

- Tkinter 桌面 UI，支援深色/淺色主題、設定視窗、播放器、歌詞、進度、暫停/停止與統計資料頁。
- 透過 Spotify embed 頁面抓取 playlist/album/artist/track，無需 Spotify API 金鑰。
- 產生 `.m3u8` 播放清單，並以本機音樂庫進行歌曲匹配。
- 透過 FFmpeg 將 Spotube M4A 轉成 MP3，並使用 metadata 匹配，避免檔名不同造成誤判。
- 將從 Spotify 播放清單移除的歌曲記錄到固定內部清單 `_Removed Songs.m3u8`。
- 產生 `_Unsorted.m3u8`，列出沒有被使用者播放清單收錄的本機歌曲。
- 統計資料會排除 `_Removed Songs.m3u8`、`_Unsorted.m3u8`、`_spotify_debug.txt` 等內部檔案。
- 支援 USB/SD 匯出，包含 Copy 與 Mirror 模式。
- 支援 `.lrc` 歌詞與可選的既有歌曲歌詞補抓。
- 在 Base Folder 下建立 session log。
- 提供 CLI，可執行更新、Spotify 抓取、歌單檢查與匹配測試。
- GitHub Actions release build：推送 `v1.6.1` 這類 tag 時，會自動把版本 `1.6.1` 寫入 app 與 installer。

## 音樂庫結構

在設定中選擇 Base Folder。典型結構如下：

```text
Base Folder/
  Music/
    mp3/
    m4a/
    ...
  playlists/
    Daily Mix 1.m3u8
    _Removed Songs.m3u8
    _Unsorted.m3u8
  config.json
  logs/
  USB_Output/
```

程式會依 `base_path` 自動推導 `Music`、`playlists`、`USB_Output` 等工作路徑。

## 快速開始

1. 安裝相依套件：

   ```bash
   pip install -r requirements.txt
   ```

2. 啟動桌面介面：

   ```bash
   python main.py
   ```

3. 開啟設定並選擇 Base Folder。

4. 在 Library 頁加入 Spotify URL，然後執行更新。

## 桌面更新流程

主要更新流程會依序執行：

1. 掃描本機音樂庫，必要時解除 Windows 下載檔封鎖。
2. 如果 FFmpeg 可用，將 Spotube M4A 轉成 MP3。
3. 抓取已設定的 Spotify URL，重建對應 `.m3u8` 播放清單。
4. 將從 Spotify 歌單移除的歌曲記錄到 `_Removed Songs.m3u8`。
5. 移除播放清單中指向不存在檔案的項目。
6. 建立或更新 `_Unsorted.m3u8`，列出未被播放清單使用的本機歌曲。
7. 使用 metadata-aware MP3/M4A 匹配更新統計資料。

## 設定

重要設定包含：

- `base_path`: 音樂庫根目錄，其它路徑都由它推導。
- `language`: `zh-TW` 或 `en`。
- `theme`: `dark` 或 `light`。
- `ffmpeg_path`: FFmpeg 執行檔路徑，用於 M4A 轉 MP3。
- `spotube_folder_name`: 音樂庫中的 Spotube 資料夾名稱。
- `spotube_convert_matched_only`: 只轉換有匹配播放清單的 M4A。
- `spotube_strict_matching`: 舊版相容用的匹配設定。
- `enable_retroactive_lyrics`: 對既有歌曲補抓缺少的歌詞。
- `lyrics_folder_name`: `.lrc` 歌詞資料夾名稱。
- `auto_update_check`: 啟動時檢查 GitHub Releases 是否有新版本。
- `debug_mode`: 開啟詳細 debug 與耗時紀錄。

設定檔位置：

- `%LOCALAPPDATA%\Playlist Administrator\data\config.json`
- 設定 `base_path` 後，會使用 `Base Folder\config.json` 作為主要工作設定

App data 裡的設定主要保留 `base_path` 指向；Base Folder 內的設定會成為主要設定來源。

## CLI 使用方式

所有命令都支援 `--config path/to/config.json`。

### `update`

執行主要更新流程。

```bash
python cli.py update
python cli.py update --config path/to/config.json
python cli.py update --force
python cli.py update --progress
```

### `scrape`

抓取 Spotify URL 並重建播放清單。

```bash
python cli.py scrape
python cli.py scrape --url "https://open.spotify.com/playlist/..."
python cli.py scrape --url "https://open.spotify.com/playlist/..." --force
```

### `fetch-playlist`

只檢查 Spotify embed 抓取結果，不執行完整更新流程。

```bash
python cli.py fetch-playlist "https://open.spotify.com/playlist/..."
python cli.py fetch-playlist "https://open.spotify.com/playlist/..." --show-tracks
python cli.py fetch-playlist "https://open.spotify.com/playlist/..." --output tracks.txt
```

### `match`

用 `_spotify_debug.txt` 或指定曲目清單測試本機匹配。

```bash
python cli.py match
python cli.py match --file "tracks.txt"
python cli.py match --no-prefer-mp3
python cli.py match --verbose
python cli.py match --fail-on-missing
```

## Release Build

推送版本 tag 後，GitHub Actions 會自動編譯 Windows 安裝檔。

```bash
git tag v1.6.1
git push origin v1.6.1
```

workflow 會：

- 驗證 tag 格式，例如 `v1.6.1`
- 將 `1.6.1` 寫入 build 時的 `utils/version.py`
- 在 build 工作區同步 README badge
- 將 `1.6.1` 傳給 Inno Setup 作為 `AppVersion`
- 建立名為 `Playlist Administrator v1.6.1` 的 GitHub Release

原始碼中的 `utils/version.py` 保留大版本基準，例如 `1.6.0`、`1.7.0`。Patch release 由 CI tag 自動處理。

## 專案結構

- `main.py`: Tkinter 入口。
- `cli.py`: 命令列介面。
- `core/library.py`: 主要更新流程、轉檔、播放清單清理、匯出、統計與匹配。
- `core/spotify.py`: Spotify embed 抓取與播放清單寫入。
- `core/snapshot_manager.py`: Removed Songs 快照追蹤。
- `core/audio_converter.py`: 音訊轉檔工具。
- `core/ffmpeg_installer.py`: FFmpeg 偵測與安裝輔助。
- `gui/app.py`: 主桌面 UI。
- `gui/settings.py`: 設定視窗。
- `gui/update_dialog.py`: 更新通知視窗。
- `utils/config.py`: 設定載入、路徑推導、debug/timing helper。
- `utils/version.py`: 基準版本與 release metadata。
- `utils/logger.py`: Session 檔案日誌。
- `installer/PlaylistAdministrator.iss`: Inno Setup 安裝腳本。
- `docs/` 與 `Docs_ZH/`: 架構與維護文件。
- `tools/`: 小工具腳本。

## 備註

- Spotify 抓取依賴 Spotify embed 頁面，如果 Spotify 改版可能需要調整。
- M4A 轉 MP3 需要 FFmpeg。
- `_Removed Songs.m3u8`、`_Unsorted.m3u8` 等內部播放清單會刻意排除在使用者播放清單統計之外。
- 桌面 UI 是主要支援入口；CLI 主要用於自動化與診斷。
