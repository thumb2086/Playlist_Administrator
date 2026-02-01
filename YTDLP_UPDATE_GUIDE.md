# yt-dlp Nightly 更新指南

## 問題說明
YouTube 已更新接口，需要使用 yt-dlp 的 nightly 版本才能正常下載。

## 更新方法

### 方法1: 使用批次檔 (推薦)
執行 `update_ytdlp_nightly.bat` 自動更新

### 方法2: 手動更新
```bash
# 1. 卸載現有版本
pip uninstall yt-dlp -y

# 2. 安裝 nightly 版本
pip install --pre --upgrade yt-dlp

# 3. 驗證版本
yt-dlp --version
```

### 方法3: 直接從 GitHub 安裝
```bash
pip install --force-reinstall https://github.com/yt-dlp/yt-dlp/archive/refs/heads/master.tar.gz
```

## 驗證更新
執行後應該看到類似輸出：
```
yt-dlp 2024.01.15.123456 (nightly)
```

## 注意事項
- Nightly 版本更新頻繁，建議定期更新
- 如果遇到問題，可以回退到穩定版：
  ```bash
  pip install yt-dlp==2023.12.30
  ```

## 修復的問題
- ✅ "Requested format is not available" 錯誤
- ✅ PO Token 驗證問題
- ✅ YouTube 接口變更導致的下載失敗
