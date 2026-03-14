# Playlist Administrator

專為 Spotube 使用者設計的輕量化維護工具：M4A 轉 MP3、分類、建立/更新 Spotify 播放清單，不包含下載功能。

## 最新使用說明 (Spotube M4A -> MP3 / 播放清單)

- 主資料夾：`C:\Users\CPXru\Music\Spotube`
- 轉檔：`Spotube\*.m4a` -> `Spotube\mp3\*.mp3`
- 播放清單：在 `Spotube\Playlists\` 建立 `.m3u8`，缺檔會自動移除
- 不下載，只做轉檔、分類、建立/更新播放清單

### 專用設定

`data/config.json`（或 GUI/Streamlit 設定）
- `spotube_folder_name`: `""`（使用 base folder 本身）
- `spotube_mp3_subfolder`: `mp3`
- `spotube_convert_workers`: 轉檔線程數（建議 6-8）
- `prefer_mp3_playlists`: `true`（播放清單優先 MP3）

### 目錄結構 (執行後)

```
C:\Users\CPXru\Music\Spotube\
  config.json
  *.m4a
  mp3\
    *.mp3
  Playlists\
    *.m3u8
  _Unsorted\        (若有未分類曲目才會出現)
  USB_Output\       (若有使用匯出才會出現)
```

### 按鈕說明

- Start/Update：開始轉檔 + 更新播放清單
- Pause：暫停並可繼續
- Cancel：在安全節點取消（已啟動的 ffmpeg 會跑完）

### 需要

- 必須有 `ffmpeg`，否則 M4A -> MP3 會被跳過

## 執行

Streamlit UI：
```bash
streamlit run streamlit_app.py
```

Tkinter UI：
```bash
python main.py
```
