# Spotube Playlist Manager (GUI)

這是一個自動化工具，幫助你整理音樂庫，並匯出成方便放入 USB 的歌單資料夾。
**新版介面 (GUI)，操作更直覺！**

## 安裝

1.  開啟終端機，執行 `pip install -r requirements.txt`。
2.  確認電腦已安裝 `ffmpeg`。

## 如何使用

執行 `python main.py`，視窗開啟後：

**步驟 1：管理歌單 (Manage URLs)**
*   **新增歌單**：去 [Chosic Spotify Analyzer](https://www.chosic.com/spotify-playlist-analyzer/) 分析你想下載的 Spotify 歌單，然後複製網址 (有 `?plid=...` 的那個) 貼上，按 "Add URL"。
*   **手動歌單**：你也可以直接在 `Playlists` 資料夾放入文字檔 (`.txt`)，一行一首歌名。

**步驟 2：操作 (Actions)**
*   點擊 **[全部更新 (下載 & 同步)]**：程式會自動抓取歌單內容，並去 YouTube 下載缺少的歌曲。
    *   (程式會智慧比對，不會重複下載已經有的歌)
    *   (支援斷點續傳，下次開這按一下就好)

**步驟 3：匯出成品**
*   點擊 **[選擇歌單匯出至 USB]**：把你整理好的歌，複製到 `USB_Export` 資料夾。
*   完成後會自動開啟資料夾，你直接拉到 USB 隨身碟即可。

## 資料夾說明
*   `Library/`: **[總倉庫]** 下載下來的 MP3 都在這，不要刪。
*   `Playlists/`: **[歌單]** 存放歌單資訊的檔案。
*   `USB_Export/`: **[成品]** 每次匯出前會清空，只放你這次要的歌。
