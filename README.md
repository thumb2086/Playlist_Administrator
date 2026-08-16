# playlist-admin

A Flutter desktop app for Spotify-native music library management: browse the
Spotify home feed, search & stream, playlist sync, batch downloads, and stats.

## Features

- **Spotify 原生整合** — 個人化主頁 / 搜尋串流 / 你的歌單（內部 GQL API，WebView 登入）
- **串流播放** — Spotify 搜尋 → yt-dlp 解析 → ffmpeg VBR 0 轉碼 → 本地 HTTP 串流（可選快取 cache\stream\）
- **原生下載** — yt-dlp 256k Opus → mp3 VBR 0（`preferredquality: 0`），批量一鍵補全
- **播放清單同步** — Spotify embed API 抓取 → m3u8 + 自動下載缺漏曲目
- **工作列媒體控制器** — SMTC 進度條 + 拖動 seek + 播放/暫停/上下首
- **播放佇列** — 拖曳排序 / 移除 / 跳轉 / play next，重啟還原（cache\queue.json）
- **播放統計** — 50%/4min scrobble 規則 → Top 曲目 / 聆聽分鐘 / 最近播放
- **下載統計** — 每輪下載成功率紀錄（cache\downloads_log.json）
- **Sleep timer / Crossfade / 全域熱鍵**（Space、←/→ seek、N/P 切歌）
- **Podcast + RAG** — RSS 下載、Groq 轉錄、Ollama chroma 問答
- **Discord RPC** — 現播歌曲 + 封面

## 資料夾結構（`Music\playlist-admin\`）

```
music\        ← 唯一音樂庫（mp3）
playlists\    ← m3u8
lyrics\       ← LRC
podcasts\     ← 播客音檔
cache\spotify ← Spotify 快取 / snapshot / session
cache\podcast ← 播客處理快取 / chroma_db
cache\lufs    ← LUFS 快取
cache\stream  ← 串流快取
cache\thumbnails
exports\      ← USB 匯出
logs\         ← 日誌
tools\        ← bridge 腳本
config.json   ← 設定
```

## Build

```bash
flutter pub get
flutter build windows --release
```

## CLI

```bash
playlist-admin pipeline [--step N]     # 全管線（抓取→下載→修剪→整理→LUFS）
playlist-admin podcast                 # Podcast 管線
playlist-admin status                  # 狀態
playlist-admin favorite list|toggle    # 我的最愛
playlist-admin rag build|query         # Podcast RAG
```

## Release

Push a `v*` tag to trigger GitHub Actions:

```bash
git tag v2.9.0
git push origin v2.9.0
```

## Dependencies

- `http` + `html` — Spotify embed API
- `crypto` — TOTP（Spotify token）
- `webview_windows`（vendor）— 登入 cookie 擷取
- `audioplayers` — 播放
- `fl_chart` — 圖表
- `flutter_discord_rpc` — Discord presence