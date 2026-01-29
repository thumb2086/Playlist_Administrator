import os
import shutil
import glob
from core.library import parse_playlist, build_library_index, find_song_in_library
from utils.helpers import sanitize_filename

def sync_folders(source_base_dir, target_base_dir, playlist_names, mode, log_func=None):
    """
    Synchronizes selected playlist folders from source to target directory.

    Args:
        source_base_dir (str): The base directory containing Music and Playlists folders.
        target_base_dir (str): The target USB/SD card base directory.
        playlist_names (list): A list of playlist names (strings) to synchronize.
        mode (str): "Copy" or "Mirror".
        log_func (callable, optional): A function to log messages. Defaults to print.
    """
    if log_func is None:
        log_func = print

    log_func(f"開始同步：模式 [{mode}]")
    log_func(f"來源目錄: {source_base_dir}")
    log_func(f"目標目錄: {target_base_dir}")
    log_func(f"同步歌單: {', '.join(playlist_names)}")

    source_music_dir = os.path.join(source_base_dir, "Music")
    source_playlists_dir = os.path.join(source_base_dir, "Playlists")

    if not os.path.exists(source_music_dir):
        log_func(f"錯誤: 來源音樂目錄不存在 - {source_music_dir}")
        return
    if not os.path.exists(source_playlists_dir):
        log_func(f"錯誤: 來源播放清單目錄不存在 - {source_playlists_dir}")
        return

    # Build a comprehensive index of all available source audio files
    log_func("建立來源音樂庫索引...")
    all_source_audio_files = []
    for root, _, files in os.walk(source_music_dir):
        for file in files:
            if file.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm')):
                all_source_audio_files.append(os.path.join(root, file))
    source_library_index = build_library_index(all_source_audio_files)
    log_func(f"來源音樂庫索引完成，共 {len(source_library_index)} 首歌。")

    for pl_name in playlist_names:
        log_func(f"\n處理歌單: {pl_name}")
        target_playlist_folder = os.path.join(target_base_dir, sanitize_filename(pl_name))
        os.makedirs(target_playlist_folder, exist_ok=True)

        m3u_file_path = os.path.join(source_playlists_dir, f"{sanitize_filename(pl_name)}.m3u8")

        if not os.path.exists(m3u_file_path):
            log_func(f"警告: 歌單M3U8檔案不存在 - {m3u_file_path}，跳過此歌單。")
            continue

        songs_in_playlist = parse_playlist(m3u_file_path)
        expected_target_files = set()
        copied_count = 0

        # --- 第一階段: 複製/更新檔案 ---
        for song_name in songs_in_playlist:
            source_song_full_path = find_song_in_library(song_name, source_library_index)

            if source_song_full_path and os.path.exists(source_song_full_path):
                file_ext = os.path.splitext(source_song_full_path)[1]
                target_song_path = os.path.join(target_playlist_folder, f"{sanitize_filename(song_name)}{file_ext}")

                expected_target_files.add(target_song_path) # Track files that should be in target

                if not os.path.exists(target_song_path) or \
                   os.path.getsize(source_song_full_path) != os.path.getsize(target_song_path) or \
                   os.path.getmtime(source_song_full_path) > os.path.getmtime(target_song_path):
                    
                    try:
                        shutil.copy2(source_song_full_path, target_song_path)
                        copied_count += 1
                        log_func(f"  複製: {os.path.basename(source_song_full_path)}")
                    except Exception as e:
                        log_func(f"  錯誤複製 {os.path.basename(source_song_full_path)}: {e}")
                # else:
                #     log_func(f"  跳過 (已存在): {os.path.basename(source_song_full_path)}")
            else:
                log_func(f"  警告: 找不到歌曲來源檔案: {song_name}")
        
        log_func(f"歌單 [{pl_name}] 複製/更新 {copied_count} 首歌。")

        # --- 第二階段: 鏡像模式特有 - 刪除多餘檔案 ---
        if mode == "Mirror":
            deleted_count = 0
            for root, _, files in os.walk(target_playlist_folder):
                for file in files:
                    full_target_file_path = os.path.join(root, file)
                    if full_target_file_path not in expected_target_files:
                        try:
                            os.remove(full_target_file_path)
                            deleted_count += 1
                            log_func(f"  刪除多餘檔案: {os.path.basename(full_target_file_path)}")
                        except Exception as e:
                            log_func(f"  錯誤刪除 {os.path.basename(full_target_file_path)}: {e}")
            log_func(f"歌單 [{pl_name}] 刪除 {deleted_count} 個多餘檔案。")

    log_func("同步任務完成！")

if __name__ == '__main__':
    # 簡單的測試用例
    # 確保你有一些測試數據和M3U8文件
    # 創建假的 source_dir 和 target_dir
    test_source_base_dir = "test_source"
    test_target_base_dir = "test_target"

    # 模擬 config 結構
    test_config = {
        'base_path': os.path.abspath(test_source_base_dir),
        'playlists_path': os.path.join(os.path.abspath(test_source_base_dir), 'Playlists'),
        'library_path': os.path.join(os.path.abspath(test_source_base_dir), 'Music')
    }

    # 創建測試用的目錄和文件
    os.makedirs(os.path.join(test_source_base_dir, "Music"), exist_ok=True)
    os.makedirs(os.path.join(test_source_base_dir, "Playlists"), exist_ok=True)
    
    # 創建假的音樂文件
    with open(os.path.join(test_source_base_dir, "Music", "Song A.mp3"), "w") as f:
        f.write("dummy content A")
    with open(os.path.join(test_source_base_dir, "Music", "Song B.mp3"), "w") as f:
        f.write("dummy content B")
    with open(os.path.join(test_source_base_dir, "Music", "Song C.flac"), "w") as f:
        f.write("dummy content C")

    # 創建假的M3U8播放清單
    with open(os.path.join(test_source_base_dir, "Playlists", "My Playlist.m3u8"), "w", encoding='utf-8-sig') as f:
        f.write("#EXTM3U\r\n")
        f.write("#EXTINF:-1,Song A\r\n")
        f.write("../Music/Song A.mp3\r\n")
        f.write("#EXTINF:-1,Song B\r\n")
        f.write("../Music/Song B.mp3\r\n")
    
    # 創建一個只包含部分歌曲的播放清單
    with open(os.path.join(test_source_base_dir, "Playlists", "Short Playlist.m3u8"), "w", encoding='utf-8-sig') as f:
        f.write("#EXTM3U\r\n")
        f.write("#EXTINF:-1,Song C\r\n")
        f.write("../Music/Song C.flac\r\n")


    print("\n--- 測試標準複製模式 ---")
    sync_folders(test_source_base_dir, test_target_base_dir, ["My Playlist", "Short Playlist"], "Copy")

    print("\n--- 測試鏡像同步模式 (有變動) ---")
    # 在目標目錄中創建一個多餘的檔案
    os.makedirs(os.path.join(test_target_base_dir, "My Playlist"), exist_ok=True)
    with open(os.path.join(test_target_base_dir, "My Playlist", "Extra Song.mp3"), "w") as f:
        f.write("extra content")
    
    sync_folders(test_source_base_dir, test_target_base_dir, ["My Playlist"], "Mirror")
    
    # 清理測試文件
    print("\n--- 清理測試文件 ---")
    shutil.rmtree(test_source_base_dir)
    shutil.rmtree(test_target_base_dir)
    print("測試完成及清理。")
