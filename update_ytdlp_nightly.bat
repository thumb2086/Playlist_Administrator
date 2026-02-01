@echo off
echo 正在更新 yt-dlp 到 nightly 版本...
echo.

REM 停用現有的 yt-dlp
pip uninstall yt-dlp -y

REM 安裝 nightly 版本
pip install --pre --upgrade yt-dlp

REM 驗證安裝
echo.
echo 驗證安裝版本:
yt-dlp --version

echo.
echo yt-dlp nightly 版本更新完成！
echo.
pause
