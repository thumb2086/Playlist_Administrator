# Playlist Administrator 選項總表

本文件以目前程式碼為準，整理出：

- 有預設值的設定
- UI 可直接調整的設定
- 仍被程式使用、但不一定出現在 UI 的隱藏設定
- 明顯屬於殘留或待清理的設定

## 一、核心路徑與基礎設定

| 鍵名 | 預設值 | 用途 | UI 狀態 | 備註 |
| --- | --- | --- | --- | --- |
| `base_path` | 無 | 專案根資料夾 | Tk/Streamlit 可調 | 最重要設定 |
| `library_path` | 由 `base_path` 推導 | 音樂庫路徑 | 不直接編輯 | 通常是 `base_path/Music` |
| `playlists_path` | 由 `base_path` 推導 | 歌單輸出路徑 | 唯讀 | 通常是 `base_path/Playlists` |
| `export_path` | 由 `base_path` 推導 | 匯出資料夾 | Streamlit 可改 | 通常是 `base_path/USB_Output` |
| `ffmpeg_path` | `bin/ffmpeg.exe` | 音訊轉檔工具路徑 | Tk/Streamlit 可調 | Spotube 轉檔與匯出品質會用到 |
| `language` | `zh-TW` | 語系 | Tk/Streamlit 可調 | `zh-TW` / `en` |
| `theme` | `dark` | Tk 主題 | Tk 可調 | 目前只有 Tk 用到 |

## 二、Spotify / 歌單設定

| 鍵名 | 預設值 | 用途 | UI 狀態 | 備註 |
| --- | --- | --- | --- | --- |
| `spotify_urls` | `[]` | 已追蹤的 Spotify playlist URL 清單 | Tk/Streamlit 可改 | 主流程核心 |
| `url_names` | `{}` | URL 對應歌單名稱快取 | 間接維護 | `add_url()` 會寫入 |
| `last_updated` | `{}` | 記錄各 URL 最後同步日期 | 不直接編輯 | 用來避免重複同步 |

## 三、Spotube / 轉檔相關

| 鍵名 | 預設值 | 用途 | UI 狀態 | 備註 |
| --- | --- | --- | --- | --- |
| `spotube_folder_name` | `spotube` | Spotube 資料夾名稱 | Streamlit 可調 | Tk 目前沒有此欄位 |
| `spotube_exact_match` | `True` | Spotube 檔名比對偏嚴格 | Streamlit 可調 | `core/spotify.py` 仍使用 |
| `spotube_convert_matched_only` | `False` | 只轉 playlist 裡有出現的 M4A | Tk/Streamlit 可調 | 可視為使用者最重要的 Spotube 開關 |
| `spotube_strict_matching` | `True` | M4A 對 MP3 轉檔比對是否只接受精準名稱 | Tk 可調 | Streamlit 目前沒有此欄位 |
| `spotube_m4a_subfolder` | 無預設 | Spotube M4A 子資料夾 | 無 UI | `core/library.py` 仍支援 |
| `spotube_mp3_subfolder` | 無預設 | Spotube MP3 子資料夾 | 無 UI | `core/library.py` 仍支援 |
| `spotube_convert_workers` | 無預設，底層 fallback `4` | 轉檔執行緒數 | 無 UI | 屬於隱藏進階選項 |

## 四、更新流程 / 背景行為

| 鍵名 | 預設值 | 用途 | UI 狀態 | 備註 |
| --- | --- | --- | --- | --- |
| `setup_completed` | `False` | 是否完成首次設定 | 內部使用 | 首次啟動精靈判斷 |
| `auto_sync_on_add` | `False` | 新增 URL 時是否立即做完整同步 | Tk 可調 | 關掉可加快新增 URL 速度 |
| `auto_update_check` | `True` | 啟動後是否檢查新版 | Tk 可調 | 與歌單流程無直接關係 |
| `max_threads` | `4` | 更新流程執行緒數上限 | 無 UI | 目前偏內部設定 |
| `debug_mode` | `False` | 開啟 debug 輸出 | Tk 可調 | 方便排查 |

## 五、歌詞 / Metadata / 其他功能

| 鍵名 | 預設值 | 用途 | UI 狀態 | 備註 |
| --- | --- | --- | --- | --- |
| `enable_retroactive_lyrics` | `False` | 補抓舊歌詞 | 無 UI | 非主流程核心 |
| `retry_failed_lyrics` | `False` | 重試失敗歌詞 | 無 UI | 內部控制 |
| `lyrics_offsets` | `{}` | 歌詞時間偏移 | 無 UI | 播放器輔助 |
| `auto_metadata` | `False` | 自動 metadata 行為 | 無 UI | 目前不是主要簡化對象 |
| `enable_metadata_enrichment` | 無預設 | 進階 metadata 補強 | 無 UI | `update_library_logic()` 內有條件使用 |

## 六、DAB / 下載相關

| 鍵名 | 預設值 | 用途 | UI 狀態 | 備註 |
| --- | --- | --- | --- | --- |
| `dab_use_lossless` | `False` | DAB 是否偏好無損 | 無 UI | 非預設主流程 |
| `dab_use_metadata` | `False` | DAB 是否依 metadata | 無 UI | 非預設主流程 |
| `dab_email` | `""` | DAB 帳號 | 無 UI | 敏感資訊 |
| `dab_password` | `""` | DAB 密碼 | 無 UI | 敏感資訊 |

## 七、目前已觀察到的殘留 / 可清理項

### A. 明顯應該移除

| 鍵名 | 現況 | 原因 |
| --- | --- | --- |
| `spotify_fetch_method` | `gui/app.py` 仍讀取 | UI 顯示殘留，實際流程只走 embed |
| `spotify_client_id` | `gui/app.py` 仍讀取 | OAuth 已不是目前主流程 |
| `spotify_client_secret` | 可能存在舊設定檔 | 同上 |

### B. 還活著，但需要產品決策

| 鍵名 | 現況 | 建議 |
| --- | --- | --- |
| `spotube_folder_name` | Streamlit 還能改 | 若團隊幾乎不改，可改成固定值或自動偵測 |
| `spotube_strict_matching` | Tk 可調、底層有用 | 若要降複雜度，可固定為 `True` |
| `spotube_convert_workers` | 無 UI 但仍可生效 | 可先保留為進階隱藏設定 |
| `spotube_m4a_subfolder` / `spotube_mp3_subfolder` | 無 UI 但底層保留 | 若專案已固定資料夾結構，可評估清理 |

## 八、兩套 UI 的差異

### Tkinter 設定視窗目前有

- `language`
- `theme`
- `auto_update_check`
- `base_path`
- `ffmpeg_path`
- `spotube_convert_matched_only`
- `spotube_strict_matching`
- `auto_sync_on_add`
- `debug_mode`

### Streamlit 設定頁目前有

- `base_path`
- `language`
- `ffmpeg_path`
- `spotube_folder_name`
- `spotube_exact_match`
- `spotube_convert_matched_only`

### 目前的不一致

1. Tk 有 `spotube_strict_matching`，Streamlit 沒有
2. Streamlit 有 `spotube_folder_name`、`spotube_exact_match`，Tk 沒有
3. 這代表使用者在兩個介面看到的是兩套不同的設定心智模型

## 九、建議的整理方向

### 最保守版本

- 保留 `spotube_convert_matched_only`
- 保留 `spotube_exact_match`
- 把 `spotube_strict_matching` 固定為 `True`
- 把 `spotube_folder_name` 固定為 `spotube` 或自動偵測

### 更激進版本

- 改成單一 `spotube_mode`
  - `disabled`
  - `basic`
  - `smart`

### 以目前程式碼來看，較穩妥的建議

先走保守版本，原因：

1. 底層轉檔流程仍明確依賴 `spotube_strict_matching`
2. Tk 與 Streamlit UI 已經不一致，先減少選項比改抽象模式更安全
3. 現階段最值得先清的是殘留 Spotify API 顯示，不是先重構 Spotube 模式
