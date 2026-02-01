#!/usr/bin/env python3
"""
檔案重新命名功能測試腳本
用於測試根據 metadata 重新命名音樂檔案的功能
"""

import os
import sys
from pathlib import Path

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.file_renamer import create_file_renamer
from utils.config import load_config, derive_paths

def test_rename_functionality():
    """測試重新命名功能"""
    print("🧪 開始測試檔案重新命名功能...")
    
    # 載入配置
    config = load_config()
    if not config or 'base_path' not in config:
        print("❌ 無法載入配置或 base_path 未設定")
        return
    
    # 取得庫存路徑
    if 'library_path' in config:
        library_path = config['library_path']
    else:
        print("❌ library_path 未設定")
        return
    
    if not os.path.exists(library_path):
        print(f"❌ 庫存路徑不存在：{library_path}")
        return
    
    print(f"📁 庫存路徑：{library_path}")
    
    # 創建重新命名器
    renamer = create_file_renamer(library_path)
    
    # 掃描音樂檔案
    print("\n🔍 掃描音樂檔案...")
    audio_files = renamer.scan_library(recursive=True)
    print(f"找到 {len(audio_files)} 個音樂檔案")
    
    if not audio_files:
        print("⚠️ 沒有找到任何音樂檔案")
        return
    
    # 測試前5個檔案的 metadata 提取
    print("\n📋 測試前5個檔案的 metadata 提取：")
    for i, file_path in enumerate(audio_files[:5], 1):
        print(f"\n{i}. {os.path.basename(file_path)}")
        
        metadata = renamer.extract_metadata(file_path)
        if metadata:
            print(f"   🎵 歌手：{metadata.get('artist', '未知')}")
            print(f"   🎶 歌名：{metadata.get('title', '未知')}")
            print(f"   💿 專輯：{metadata.get('album', '未知')}")
            print(f"   📅 年份：{metadata.get('date', '未知')}")
            
            # 生成新檔名
            file_ext = Path(file_path).suffix.lower()
            new_filename = renamer.generate_new_filename(metadata, file_ext)
            if new_filename:
                print(f"   🔄 新檔名：{new_filename}")
            else:
                print("   ❌ 無法生成新檔名")
        else:
            print("   ❌ 無法提取 metadata")
    
    # 預覽變更
    print("\n🔍 預覽重新命名變更（前10個）：")
    preview = renamer.preview_changes(recursive=True, limit=10)
    
    if not preview:
        print("✅ 所有檔案都已經是正確的命名格式！")
    else:
        print(f"找到 {len(preview)} 個需要重新命名的檔案：")
        for i, item in enumerate(preview, 1):
            print(f"{i}. {item['old_name']}")
            print(f"   → {item['new_name']}")
            print(f"   🎵 {item['artist']} - {item['title']}")
    
    # 詢問是否要執行重新命名
    if preview:
        print(f"\n⚠️ 找到 {len(preview)} 個檔案需要重新命名")
        response = input("是否要執行重新命名？(y/N): ").strip().lower()
        
        if response == 'y':
            print("\n🔄 執行批次重新命名...")
            results = renamer.batch_rename(dry_run=False, recursive=True)
            
            print("\n📊 處理結果：")
            print(f"📁 總共掃描檔案：{results['total_files']} 個")
            print(f"✅ 成功重新命名：{results['renamed']} 個")
            print(f"⏭️ 已跳過：{results['skipped']} 個")
            print(f"❌ 錯誤：{results['errors']} 個")
        else:
            print("❌ 取消重新命名操作")
    
    print("\n🎉 測試完成！")

if __name__ == "__main__":
    test_rename_functionality()
