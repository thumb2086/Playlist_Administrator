# 如何匯出 YouTube Cookies 以繞過驗證

## 為什麼需要這樣做？

YouTube 現在會要求「登入以確認不是機器人」。我們需要從您的瀏覽器匯出 cookies，讓程式能證明「這是真人的帳號」。

## 步驟（使用 Chrome 瀏覽器）

### 1. 安裝瀏覽器擴充功能

請到 Chrome 線上應用程式商店安裝以下其中一個擴充功能：

**推薦選項 1：Get cookies.txt LOCALLY**
- 連結：https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc
- 優點：簡單、安全（不會上傳資料）

**選項 2：cookies.txt**
- 連結：https://chromewebstore.google.com/detail/cookiestxt/njabckikapfpffapmjgojcnbfjonfjfg

### 2. 登入 YouTube

1. 打開 Chrome 瀏覽器
2. 前往 https://www.youtube.com
3. **確保您已登入 Google 帳號**

### 3. 匯出 Cookies

1. 在 YouTube 頁面上，點擊瀏覽器右上角的**擴充功能圖示**
2. 選擇您剛才安裝的 cookies 擴充功能
3. 點擊「Export」或「Download」按鈕
4. 會下載一個名為 `cookies.txt` 或 `youtube.com_cookies.txt` 的檔案

### 4. 放到程式資料夾

1. 找到剛才下載的 `cookies.txt` 檔案
2. **重新命名為** `cookies.txt`（如果檔名不同的話）
3. 把它**複製到這個資料夾**：
   ```
   C:\Users\CPXru\Desktop\thumb\program\spotube_歌單更新軟體\
   ```
   （就是跟 `main.py` 放在同一個資料夾）

### 5. 重新執行程式

現在重新執行程式，它就能用這個 cookies.txt 來通過 YouTube 驗證了！

---

## 注意事項

- ⚠️ **不要把 cookies.txt 分享給別人**，因為它包含您的登入資訊
- 🔄 如果過一段時間後又出現驗證問題，可能是 cookies 過期了，重新匯出一次即可
- ✅ 匯出後可以把瀏覽器擴充功能移除（如果您不想留著的話）

---

## 常見問題

**Q: 我沒有 Chrome，可以用其他瀏覽器嗎？**
A: 可以！Edge、Firefox 都有類似的擴充功能，搜尋「cookies.txt」就能找到。

**Q: 這樣安全嗎？**
A: 只要您使用的是官方商店的擴充功能，並且 cookies.txt 只放在自己電腦，就是安全的。

**Q: 還是不行怎麼辦？**
A: 確認 cookies.txt 確實在程式資料夾內，檔名完全正確（全小寫，沒有多餘的空格或數字）。
