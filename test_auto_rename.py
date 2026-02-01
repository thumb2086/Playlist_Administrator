#!/usr/bin/env python3
"""
測試自動下載和重新命名功能
"""

import os
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.downloader import download_song
from utils.config import load_config

def test_auto_rename():
    """測試自動下載和重新命名功能"""
    print("🧪 測試自動下載和重新命名功能...")
    
    # 載入配置
    config = load_config()
    if not config or 'library_path' not in config:
        print("❌ 無法載入配置或 library_path 未設定")
        return
    
    library_path = config['library_path']
    audio_format = config.get('audio_format', 'mp3')
    
    print(f"📁 庫存路徑：{library_path}")
    print(f"🎵 音訊格式：{audio_format}")
    
    # 測試歌曲（使用一個簡單的測試歌曲）
    test_song = "Taylor Swift - Anti-Hero"
    
    print(f"\n🎶 測試下載：{test_song}")
    
    def log_callback(message):
        print(message)
    
    try:
        # 執行下載
        result_path = download_song(
            song_name=test_song,
            library_path=library_path,
            audio_format=audio_format,
            log_func=log_callback,
            file_list=[],
            config=config
        )
        
        if result_path and os.path.exists(result_path):
            print(f"\n✅ 下載成功！")
            print(f"📁 檔案路徑：{result_path}")
            print(f"📄 檔案名稱：{os.path.basename(result_path)}")
            
            # 檢查檔名是否符合預期格式
            filename = os.path.basename(result_path)
            if ' - ' not in filename:
                print("✅ 檔名格式正確：只有歌名（有 metadata）")
            else:
                print("⚠️ 檔名格式：歌手 - 歌名（可能無 metadata）")
        else:
            print("❌ 下載失敗")
            
    except Exception as e:
        print(f"❌ 測試失敗：{str(e)}")

if __name__ == "__main__":
    test_auto_rename()
