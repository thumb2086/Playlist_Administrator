@echo off
echo Building Playlist Administrator with zhconv support...
pyinstaller --noconfirm --onedir --console --collect-all zhconv "gui/app.py"
echo Build completed! Check the dist folder for the executable.
pause
