#!/usr/bin/env python3
"""
調試搜尋功能
"""

import os
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.library import find_song_in_library, find_song_in_library_debug, get_normalized_tokens
from mutagen.easyid3 import EasyID3

def debug_search():
    """調試搜尋功能"""
    print("🔍 調試搜尋功能...")
    
    # 載入配置
    from utils.config import load_config
    config = load_config()
    library_path = config['library_path']
    
    # 掃描音樂檔案
    import glob
    search_pattern = os.path.join(library_path, "**", "*")
    all_files = glob.glob(search_pattern, recursive=True)
    audio_files = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]
    
    # 測試搜尋
    song_name = "BIDO 曾愷妤 - SUGAR HIGH"
    title_part = song_name.split(' - ', 1)[1].strip()
    
    print(f"🎵 搜尋歌曲：{song_name}")
    print(f"🎶 提取的歌名：{title_part}")
    print(f"🔤 歌名 tokens：{tuple(get_normalized_tokens(title_part))}")
    
    # 手動檢查 SUGAR HIGH.mp3
    target_file = None
    for file_path in audio_files:
        if 'SUGAR HIGH' in file_path:
            target_file = file_path
            break
    
    if target_file:
        print(f"\n📁 找到目標檔案：{target_file}")
        
        # 檢查檔名 tokens
        filename = os.path.basename(target_file)
        name_no_ext = os.path.splitext(filename)[0]
        filename_tokens = tuple(get_normalized_tokens(name_no_ext))
        print(f"📝 檔名：{name_no_ext}")
        print(f"🔤 檔名 tokens：{filename_tokens}")
        
        # 檢查 metadata
        try:
            audio = EasyID3(target_file)
            metadata_title = audio.get('title', [None])[0]
            print(f"🏷️ Metadata 標題：{metadata_title}")
            print(f"🔤 Metadata tokens：{tuple(get_normalized_tokens(metadata_title))}")
            
            # 比較
            metadata_tokens = tuple(get_normalized_tokens(metadata_title))
            query_title_tokens = tuple(get_normalized_tokens(title_part))
            print(f"✅ Tokens 匹配：{metadata_tokens == query_title_tokens}")
            
            # 測試部分匹配
            print(f"🔍 檢查 'sugar' 和 'high' 是否都在 metadata tokens 中：")
            print(f"  'sugar' in metadata_tokens: {'sugar' in metadata_tokens}")
            print(f"  'high' in metadata_tokens: {'high' in metadata_tokens}")
            
        except Exception as e:
            print(f"❌ 讀取 metadata 失敗：{e}")
        
        # 測試 find_song_in_library
        print(f"\n🔍 測試 find_song_in_library：")
        result = find_song_in_library(song_name, audio_files)
        if result:
            print(f"✅ 找到：{result}")
        else:
            print(f"❌ 未找到")
            
        # 測試 debug version
        print(f"\n🔍 測試 find_song_in_library_debug：")
        result_debug = find_song_in_library_debug(song_name, audio_files)
        if result_debug:
            print(f"✅ 找到：{result_debug}")
        else:
            print(f"❌ 未找到")
            
        # 測試只用歌名搜尋
        print(f"\n🔍 測試只用歌名搜尋：")
        result_title_only = find_song_in_library(title_part, audio_files)
        if result_title_only:
            print(f"✅ 找到：{result_title_only}")
        else:
            print(f"❌ 未找到")
            
        # 手動測試 subset matching
        print(f"\n🔍 手動測試 subset matching：")
        title_tokens_local = tuple(get_normalized_tokens(title_part))
        metadata_tokens_local = tuple(get_normalized_tokens(metadata_title))
        title_tokens_set = set(title_tokens_local)
        metadata_tokens_set = set(metadata_tokens_local)
        is_subset = title_tokens_set.issubset(metadata_tokens_set)
        coverage = len(title_tokens_set) / len(metadata_tokens_set) if len(metadata_tokens_set) > 0 else 0
        print(f"  title_tokens_set: {title_tokens_set}")
        print(f"  metadata_tokens_set: {metadata_tokens_set}")
        print(f"  is_subset: {is_subset}")
        print(f"  coverage: {coverage:.2f}")
        print(f"  passes coverage >= 0.3: {coverage >= 0.3}")

if __name__ == "__main__":
    debug_search()
