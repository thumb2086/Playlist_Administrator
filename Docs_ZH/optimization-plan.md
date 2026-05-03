# Playlist Administrator 優化決策清單

本文件不是直接列「想法」，而是依照目前程式碼現況，整理成可以執行的優先順序。

## 結論先講

最應該先做的不是大改流程，而是先把「已經失效但還殘留在 UI / 設定中的概念」清乾淨。

目前最值得優先處理的 4 項如下：

1. 移除啟動時 `proactive_name_fetch`
2. 移除 Spotify API 殘留顯示與設定鍵
3. 統一 Spotube 設定心智模型
4. 補文件，讓後續清理不再靠猜

## 優先級排序

## P1：立刻可做，風險低

### 1. 移除啟動時 `proactive_name_fetch`

位置：

- `gui/app.py:171` 附近

原因：

- 啟動 500ms 後會自動開背景執行緒
- 若 `url_names` 已有快取，這段大多沒有價值
- 會讓啟動流程多一個無條件背景工作

判斷：

- 這是最乾淨的低風險優化
- 保留函式本身即可，因為 `add_url()` 仍依賴抓名稱流程

### 2. 清掉 `view_playlist_songs()` 的 Spotify API 殘留文字

位置：

- `gui/app.py:1562` 附近

原因：

- 目前實際抓取路徑已是 embed-only
- UI 還在顯示 `embed/api/auto`
- 這會讓使用者誤以為 OAuth/API 仍可切換

判斷：

- 這屬於純顯示層清理
- 幾乎沒有行為風險

### 3. 從設定預設值與文件中移除舊 Spotify API 概念

位置：

- `utils/config.py`
- 舊文件與說明

原因：

- `spotify_fetch_method`
- `spotify_client_id`
- `spotify_client_secret`

這幾個概念若還在設定檔或文件裡，只會增加誤導與維護成本。

判斷：

- 若只做「不再讀取、不再顯示、不再寫入」，風險低

## P2：可以做，但要保守

### 4. 簡化 Spotube 設定

現況問題：

- Tk 和 Streamlit 的設定欄位不一致
- 使用者要理解 `spotube_exact_match`
- `spotube_convert_matched_only`
- `spotube_strict_matching`
- `spotube_folder_name`

這四個欄位的差別，學習成本偏高

我建議先做的版本：

- UI 只保留 `spotube_convert_matched_only`
- `spotube_strict_matching` 固定為 `True`
- `spotube_folder_name` 固定 `spotube` 或自動偵測
- `spotube_exact_match` 先保留，因為它仍影響播放清單匹配

原因：

1. 這條路修改面最小
2. 不需要立刻重寫底層轉檔策略
3. 能先把兩套 UI 靠攏

## P3：先不要急著動

### 5. 不建議現在移除 Spotube 轉檔主體

原因：

- `core/library.py` 的 M4A -> MP3 流程還在主更新流程內
- 很多狀態判斷、metadata 命名校正都還有實際用途
- 若直接拔掉，容易影響既有使用者音樂庫

### 6. 不建議現在移除 `_metadata_based_mp3_path`

原因：

- 這是 metadata 導向命名修正的一部分
- 它看起來不是殘留，而是現行轉檔穩定度的重要保護

## 目前實際看到的結構問題

### 1. 文件與程式碼不同步

- `docs/architecture.md` 寫成很多功能已移除
- 但 `core/library.py` 中 Spotube 轉檔仍在

### 2. Tk 與 Streamlit 的設定定義不同步

- Tk 有 `spotube_strict_matching`
- Streamlit 沒有
- Streamlit 有 `spotube_folder_name`
- Tk 沒有

### 3. 設定鍵已經超出目前產品想表達的複雜度

- 不少設定是「工程上還支援」，但產品上不適合再曝光給一般使用者

## 建議分兩階段執行

### 第一階段

- 移除啟動 `proactive_name_fetch`
- 移除 Spotify API 殘留顯示
- 清掉舊設定鍵讀取與文件

### 第二階段

- 簡化 Spotube 設定
- 統一 Tk / Streamlit 的設定欄位
- 視需要把隱藏設定改成硬編碼或自動偵測

## 驗證重點

每次調整後，至少驗證下面 4 件事：

1. 啟動速度是否正常，UI 是否更快可操作
2. 新增 Spotify URL 是否仍能正確抓到歌單名稱
3. 全量更新是否仍能產生 `.m3u8`
4. Spotube 的 M4A -> MP3 流程是否沒有被意外破壞

## 我對下一步的建議

如果現在就要開始改，我建議從這個順序下手：

1. `gui/app.py` 移除啟動背景 `proactive_name_fetch`
2. `gui/app.py` 清掉 `view_playlist_songs()` 的 fetch method 顯示
3. `utils/config.py` 清理舊 Spotify API 預設值或相依讀取
4. `gui/settings.py` / `streamlit_app.py` 開始收斂 Spotube 選項
