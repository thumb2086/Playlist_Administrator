# Playlist Administrator (Streamlit GUI)

這是一個自動化工具，幫助你整理音樂庫，並匯出成方便放入 USB 的歌單資料夾。

## 新版重點

- 下載引擎改為 **spotDL standalone executable**（透過 `subprocess` 呼叫，不 `import spotdl`）。
- Spotify 來源下載有更完整 metadata（歌手、專輯、封面）。
- 保留原本 smart matching，避免重複下載。
- 若某首歌拿不到 Spotify track URL，會回退到舊下載流程。

## 安裝

1. 安裝 Python 套件：
```bash
pip install -r requirements.txt
```
2. 建立本機執行檔資料夾：
```bash
mkdir -p bin
```
3. 從 spotDL Releases 下載可執行檔：
   - https://github.com/spotDL/spotify-downloader/releases
4. 從 FFmpeg 官網下載可執行檔：
   - https://ffmpeg.org/download.html
5. 將檔案放入 `bin/`：
   - Windows：`bin/spotdl.exe`、`bin/ffmpeg.exe`
   - Linux/macOS：`bin/spotdl`、`bin/ffmpeg`

## 執行方式

Streamlit 介面：
```bash
streamlit run streamlit_app.py
```

Tkinter 介面（舊版）：
```bash
python main.py
```

## GUI 設定（spotDL）

進入 `⚙️ 系統設定 -> 一般 & 路徑` 設定：
- `spotdl 路徑`（預設 `bin/spotdl.exe`）
- `ffmpeg 路徑`（預設 `bin/ffmpeg.exe`）
- `格式`（`mp3` / `m4a` / `opus`）
- `強制覆蓋`（關閉=跳過既有檔、開啟=強制覆蓋）
- `Bitrate`（選填，例如 `320k`）
- `spotDL Timeout`（預設 `600` 秒）
- `輸出模板`（選填；空白時用 `Music/{artist}/{album}/{title}.{output-ext}`）

## 下載流程

1. 先更新 Spotify 歌單/專輯/藝人/單曲資訊。
2. 建立本地索引，找出缺少歌曲。
3. 下載缺歌時：
   - 有 Spotify track URL：走 spotDL。
   - 無 URL 或失敗：回退舊 downloader。
4. 更新狀態，後續匯出流程維持不變。

## 資料夾說明

- `Music/`：主音樂庫。
- `Playlists/`：歌單檔（`.m3u8` / `.m3u` / `.txt`）。
- `USB_Output/`：匯出資料夾。
- `bin/`：本機執行檔（`spotdl`、`ffmpeg`），已在 `.gitignore` 排除。

## 雲端打包（GitHub Actions + PyInstaller）

- Workflow 檔案：`.github/workflows/build.yml`
- 觸發條件：推送 tag `v*`
- Jobs：`build-windows` + `build-linux`
- Python 版本：`3.12`
- 主要指令：
  - Windows：`pyinstaller --noconfirm --onefile --windowed --name PlaylistAdministrator --add-binary "bin/*;bin" streamlit_app.py`
  - Linux：`pyinstaller --noconfirm --onefile --windowed --name PlaylistAdministrator --add-binary "bin/*:bin" streamlit_app.py`
- 產物會上傳為 artifact，並附加到 GitHub Release。

## 測試 Checklist

1. 小歌單測試
   - 匯入 3-5 首歌的 Spotify 歌單，確認可完整下載。
2. Metadata 驗證
   - 抽查檔案標籤：title、artist、album、cover。
3. 無重複下載
   - 再執行一次更新，確認既有歌曲會被略過。
4. fallback 驗證
   - 測一首缺 URL 對應的歌曲，確認會走舊流程。
5. 錯誤處理
   - 暫時填錯 `spotdl 路徑`，確認會記錄錯誤且不中斷整體任務。
6. 匯出驗證
   - 匯出歌單後，確認 `USB_Output/` 結構與歌曲數量正確。
