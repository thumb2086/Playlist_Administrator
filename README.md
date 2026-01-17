# Spotube Playlist Manager (GUI)

An automation tool to organize your music library and export it into USB-ready playlist folders.
**Now with a GUI for a more intuitive experience!**

## Installation

1.  Open your terminal and run `pip install -r requirements.txt`.
2.  Ensure `ffmpeg` is installed on your system.

## How to Use

Run `python main.py`. Once the window opens:

**Step 1: Manage URLs**
*   **Add Playlists**: Use [Chosic Spotify Analyzer](https://www.chosic.com/spotify-playlist-analyzer/) to analyze the Spotify playlist you want to download. Copy the URL (the one with `?plid=...`) and paste it, then click "Add URL".
*   **Manual Playlists**: You can also manually place text files (`.txt`) into the `Playlists` folder, with one song title per line.

**Step 2: Actions**
*   Click **[Update All (Download & Sync)]**: The program will automatically fetch playlist content and download any missing songs from YouTube.
    *   (Smart matching prevents redownloading existing songs)
    *   (Supports resuming; just click the button again next time)

**Step 3: Exporting**
*   Click **[Export to USB]**: Copies your organized songs into the `USB_Export` folder.
*   The folder will open automatically once finished. You can then simply drag the contents to your USB drive.

## Folder Structure
*   `Library/`: **[Master Repository]** All downloaded MP3s are stored here. Do not delete them.
*   `Playlists/`: **[Playlists]** Contains information about your playlists.
*   `USB_Export/`: **[Output]** This folder is cleared before each export and contains only the songs selected for the current export.
