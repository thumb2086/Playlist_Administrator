#!/usr/bin/env python3
"""
測試修改後的搜尋功能
"""

import os
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.library import find_song_in_library, build_library_index
from utils.config import load_config

def test_search_fix():
    """測試修改後的搜尋功能"""
    print("🧪 測試修改後的搜尋功能...")
    
    # 載入配置
    config = load_config()
    if not config or 'library_path' not in config:
        print("❌ 無法載入配置或 library_path 未設定")
        return
    
    library_path = config['library_path']
    print(f"📁 庫存路徑：{library_path}")
    
    # 掃描音樂檔案
    import glob
    search_pattern = os.path.join(library_path, "**", "*")
    all_files = glob.glob(search_pattern, recursive=True)
    audio_files = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]
    
    print(f"📊 找到 {len(audio_files)} 個音樂檔案")
    
    # 建立索引
    print("\n🔍 建立檔案索引...")
    lib_index = build_library_index(audio_files)
    
    # 測試搜尋一些歌曲
    test_songs = [
        "AKB48 Team TP - RESET",  # 這個應該被重新命名為 "RESET"
        "BIDO 曾愷妤 - SUGAR HIGH",  # 這個應該被重新命名為 "SUGAR HIGH"
        "Taylor Swift - Anti-Hero",  # 測試一個可能不存在的歌曲
    ]
    
    print("\n🎵 測試搜尋功能：")
    for song_name in test_songs:
        print(f"\n🔍 搜尋：{song_name}")
        
        # 使用索引搜尋
        result_index = find_song_in_library(song_name, lib_index)
        if result_index:
            print(f"  ✅ 索引搜尋找到：{os.path.basename(result_index)}")
        else:
            print(f"  ❌ 索引搜尋未找到")
        
        # 使用檔案列表搜尋
        result_list = find_song_in_library(song_name, audio_files)
        if result_list:
            print(f"  ✅ 列表搜尋找到：{os.path.basename(result_list)}")
        else:
            print(f"  ❌ 列表搜尋未找到")
    
    # 檢查一些實際存在的檔案
    print("\n📋 檢查實際檔案：")
    for i, file_path in enumerate(audio_files[:5], 1):
        filename = os.path.basename(file_path)
        print(f"\n{i}. {filename}")
        
        # 嘗試反推可能的原始歌曲名稱
        name_no_ext = os.path.splitext(filename)[0]
        
        # 如果檔名只有歌名，嘗試構造「歌手 - 歌名」格式來搜尋
        if ' - ' not in name_no_ext:
            # 嘗試一些常見的歌手前綴
            test_prefixes = ["Taylor Swift - ", "AKB48 Team TP - ", "BIDO 曾愷妤 - "]
            for prefix in test_prefixes:
                test_name = prefix + name_no_ext
                result = find_song_in_library(test_name, audio_files)
                if result == file_path:
                    print(f"  🔍 可以透過 '{test_name}' 找到")
                    break
            else:
                print(f"  ⚠️ 無法透過常見前綴找到")
        else:
            print(f"  ✅ 檔名已包含 ' - ' 分隔符")

if __name__ == "__main__":
    test_search_fix()
