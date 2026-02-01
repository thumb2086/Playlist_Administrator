#!/usr/bin/env python3
"""
檢查音樂檔案的 metadata 狀況
"""

import os
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.file_renamer import create_file_renamer
from utils.config import load_config

def check_metadata_status():
    """檢查檔案的 metadata 狀況"""
    print("🔍 檢查音樂檔案 metadata 狀況...")
    
    # 載入配置
    config = load_config()
    if not config or 'library_path' not in config:
        print("❌ 無法載入配置或 library_path 未設定")
        return
    
    library_path = config['library_path']
    print(f"📁 庫存路徑：{library_path}")
    
    # 創建重新命名器
    renamer = create_file_renamer(library_path)
    
    # 掃描音樂檔案
    audio_files = renamer.scan_library(recursive=True)
    print(f"找到 {len(audio_files)} 個音樂檔案")
    
    # 統計 metadata 狀況
    with_metadata = 0
    without_metadata = 0
    problematic_files = []
    
    print("\n📋 檢查前20個檔案的 metadata：")
    for i, file_path in enumerate(audio_files[:20], 1):
        filename = os.path.basename(file_path)
        metadata = renamer.extract_metadata(file_path)
        
        if metadata:
            artist = metadata.get('artist', '').strip()
            title = metadata.get('title', '').strip()
            
            if artist and title:
                with_metadata += 1
                status = "✅ 完整 metadata"
            elif title:
                with_metadata += 1
                status = "⚠️ 只有歌名"
            else:
                without_metadata += 1
                status = "❌ 無 metadata"
            
            print(f"{i:2d}. {filename}")
            print(f"     {status}")
            print(f"     🎵 歌手：'{artist}'")
            print(f"     🎶 歌名：'{title}'")
            print()
        else:
            without_metadata += 1
            print(f"{i:2d}. {filename}")
            print(f"     ❌ 無法提取 metadata")
            print()
    
    # 統計結果
    print(f"\n📊 統計結果（前20個檔案）：")
    print(f"✅ 有 metadata：{with_metadata} 個")
    print(f"❌ 無 metadata：{without_metadata} 個")
    
    # 檢查檔名格式分析
    print(f"\n🔍 檔名格式分析：")
    correct_format = 0
    wrong_format = 0
    
    for file_path in audio_files[:50]:  # 檢查前50個
        filename = os.path.basename(file_path)
        metadata = renamer.extract_metadata(file_path)
        
        if metadata and metadata.get('title'):
            # 如果有 metadata 中的歌名，檔案應該只叫歌名
            expected_name = metadata.get('title', '').strip()
            if expected_name:
                file_ext = Path(file_path).suffix.lower()
                expected_filename = f"{expected_name}{file_ext}"
                
                # 清理檔名用於比較
                clean_expected = renamer.generate_new_filename({'title': expected_name}, file_ext)
                clean_current = Path(filename).name
                
                if clean_expected == clean_current:
                    correct_format += 1
                else:
                    wrong_format += 1
                    if wrong_format <= 5:  # 只顯示前5個錯誤
                        print(f"❌ 格式錯誤：{filename}")
                        print(f"   應該是：{clean_expected}")
        else:
            # 如果沒有 metadata，檔名應該是「歌手 - 歌名」格式
            if ' - ' in filename:
                correct_format += 1
            else:
                wrong_format += 1
                if wrong_format <= 5:
                    print(f"❌ 無 metadata 但格式錯誤：{filename}")
    
    print(f"\n📊 檔名格式統計（前50個）：")
    print(f"✅ 正確格式：{correct_format} 個")
    print(f"❌ 錯誤格式：{wrong_format} 個")

if __name__ == "__main__":
    check_metadata_status()
