# Playlist Administrator

給 Spotube 與本機音樂庫使用的維護工具：M4A 轉 MP3、建立/更新 Spotify 播放清單、管理匯出。預設流程不下載音樂檔。

## 功能概覽

- 將 Spotube 的 M4A 轉成 MP3（輸出到 `mp3` 子資料夾，支援多執行緒）。
- 透過 Spotify embed 頁面建立/更新 `.m3u8`（支援 playlist/album/artist/track URL）。
- 移除播放清單中已不存在的檔案項目。
- 必要時把未分類歌曲移到 `_Unsorted`。
- 將選取播放清單匯出到 USB/SD（Copy 或 Mirror）。
- Tkinter 桌面 UI 內建播放器與歌詞（`.lrc`）。
- Streamlit UI 含儀表板與設定頁。

## 快速開始

1. 安裝相依套件：
   ```bash
   pip install -r requirements.txt
   ```
2. 啟動介面：
   ```bash
   python main.py
   ```
   或：
   ```bash
   streamlit run streamlit_app.py
   ```
3. 設定 Base Folder（音樂庫根目錄）。可為：
   - 已含 `Music` 與 `Playlists` 的資料夾，或
   - 直接包含 `.m4a` 的 Spotube 資料夾。
4. 加入 Spotify URL，按 Start/Update。

## 安裝（EXE）

GitHub Actions 會自動編譯 Windows 安裝版。請到 GitHub Releases 下載最新安裝檔並執行安裝。

## 設定檔

設定檔存放在使用者目錄，並可寫入 base folder：

- 主設定：`%LOCALAPPDATA%\Playlist Administrator\data\config.json`
- 若設定 `base_path`，會在 base folder 內建立 `config.json` 並以其為主。App data 的設定檔只保留 `base_path` 指向。

重要設定：

- `base_path`: 音樂庫根目錄。`Music`、`Playlists`、`USB_Output` 由此衍生。
- `ffmpeg_path`: M4A 轉 MP3 所需的 `ffmpeg` 路徑。
- `spotube_folder_name`: 音樂庫內 Spotube 目錄名稱。設為 `""` 代表 base folder 直接是 Spotube。
- `spotube_mp3_subfolder`: MP3 輸出子資料夾名稱（預設 `mp3`）。
- `spotube_convert_workers`: 轉檔工作數（預設 4）。
- `prefer_mp3_playlists`: 產生播放清單時優先 MP3。

## 專案結構

- `main.py`: Tkinter 入口。
- `streamlit_app.py`: Streamlit UI。
- `core/`: 核心流程（播放清單、轉檔、Spotify 抓取、同步/匯出、metadata）。
- `gui/`: Tkinter 介面與設定視窗。
- `utils/`: 設定與工具、i18n。
- `tools/`: 小工具腳本。
- `Docs_ZH/`: 其他中文文件。
- `PLAYBACK_FIX_README.md`: Windows 播放問題修正說明。
- `YTDLP_UPDATE_GUIDE.md`: yt-dlp 更新步驟。

## 備註

- M4A 轉 MP3 需要 `ffmpeg`，缺少時會跳過轉檔。
- Spotify 抓取依賴 embed 頁面，需要網路連線。
- 下載相關工具（yt-dlp、DAB、spotDL）在 `core/downloader.py`，但預設更新流程未使用。
