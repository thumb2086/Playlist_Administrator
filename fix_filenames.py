#!/usr/bin/env python3
"""
檔案名稱修復工具
批量修復音樂檔案的命名問題，包括：
1. 移除多餘的符號和空格
2. 保留重要的識別資訊（Netflix、影集等）
3. 統一命名格式為「歌手-歌名」
4. 修復空檔名問題
"""

import os
import sys
import re
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils.config import load_config, derive_paths
from core.file_renamer import create_file_renamer
from utils.helpers import sanitize_filename

def scan_problematic_files(library_path):
    """掃描有問題的檔案"""
    problematic_files = []
    audio_extensions = {'.mp3', '.flac', '.m4a', '.mp4', '.mp2', '.mp1'}
    
    for root, dirs, files in os.walk(library_path):
        for file in files:
            file_path = os.path.join(root, file)
            file_ext = Path(file).suffix.lower()
            
            if file_ext not in audio_extensions:
                continue
                
            # 檢查各種問題
            issues = []
            name_without_ext = Path(file).stem
            
            # 1. 空檔名或只有副檔名
            if not name_without_ext or name_without_ext.isspace():
                issues.append("空檔名")
            
            # 2. 末尾有多餘符號
            if name_without_ext.endswith(('-', '_', '.', ' ')):
                issues.append("末尾多餘符號")
            
            # 3. 連續符號
            if '--' in name_without_ext or '__' in name_without_ext or '  ' in name_without_ext:
                issues.append("連續符號")
            
            # 4. 非常短的檔名（可能是被過度清理）
            if len(name_without_ext) <= 3 and name_without_ext.isalnum():
                issues.append("檔名過短")
            
            # 5. 包含常見的垃圾內容
            garbage_patterns = [
                'Official Video', 'Music Video', 'MV', '官方MV', 
                'Official Music Video', 'Music Video', 'Lyrics Video'
            ]
            for pattern in garbage_patterns:
                if pattern.lower() in file.lower():
                    issues.append(f"包含垃圾內容: {pattern}")
                    break
            
            # 6. 檢查是否有奇怪的符號組合
            if re.search(r'[-_]{2,}', name_without_ext):
                issues.append("多餘的連續符號")
            
            # 7. 檢查是否有未清理的 Netflix/影集內容（這些應該保留，但檢查格式）
            if netflix_patterns := ['Netflix', '影集', '插曲', '片尾曲', '主題曲']:
                has_netflix = any(pattern in file for pattern in netflix_patterns)
                if has_netflix and re.search(r'[-_]\s*$', name_without_ext):
                    issues.append("Netflix內容末尾有符號")
            
            # 8. 檢查檔名是否以奇怪的方式結尾
            if re.search(r'[^a-zA-Z0-9\u4e00-\u9fff\u3040-\u30ff\s\-\._\(\)\[\]]$', name_without_ext):
                issues.append("檔名末尾有奇怪字元")
            
            # 9. 檢查是否有過多的標點符號
            punctuation_count = sum(1 for c in name_without_ext if c in '.,;:!?')
            if punctuation_count > 3:
                issues.append("過多標點符號")
            
            # 10. 檢查是否有未處理的 Explicit 前綴
            if re.match(r'^E[A-Z\u4e00-\u9fff\u3040-\u30ff]', name_without_ext):
                issues.append("Explicit 前綴未清理")
            
            if issues:
                problematic_files.append({
                    'path': file_path,
                    'name': file,
                    'issues': issues
                })
    
    return problematic_files

def preview_rename_changes(renamer, file_path):
    """預覽重新命名的變化"""
    result = renamer.rename_file(file_path, dry_run=True)
    return result

def fix_all_files(library_path, dry_run=True):
    """修復所有有問題的檔案"""
    print(f"🔍 掃描音樂庫: {library_path}")
    
    # 掃描問題檔案
    problematic_files = scan_problematic_files(library_path)
    print(f"\n📊 找到 {len(problematic_files)} 個有問題的檔案")
    
    if not problematic_files:
        print("✅ 沒有發現問題檔案！")
        return
    
    # 顯示問題檔案列表
    print("\n🔍 問題檔案列表:")
    for i, file_info in enumerate(problematic_files[:10], 1):  # 只顯示前10個
        print(f"{i:2d}. {file_info['name']}")
        for issue in file_info['issues']:
            print(f"     ⚠️  {issue}")
    
    if len(problematic_files) > 10:
        print(f"     ... 還有 {len(problematic_files) - 10} 個檔案")
    
    # 創建重新命名器
    renamer = create_file_renamer(library_path)
    
    print(f"\n{'🔍 預覽模式' if dry_run else '🔧 修復模式'} - 檢查重新命名效果:")
    
    fixed_count = 0
    error_count = 0
    
    for file_info in problematic_files:
        file_path = file_info['path']
        old_name = os.path.basename(file_path)
        
        try:
            result = preview_rename_changes(renamer, file_path)
            
            if result['success'] and result['new_path'] != file_path:
                new_name = os.path.basename(result['new_path'])
                print(f"✅ {old_name}")
                print(f"   → {new_name}")
                fixed_count += 1
                
                # 如果不是預覽模式，執行實際重新命名
                if not dry_run:
                    actual_result = renamer.rename_file(file_path, dry_run=False)
                    if not actual_result['success']:
                        print(f"   ❌ 重新命名失敗: {actual_result['message']}")
                        error_count += 1
            elif result['success']:
                print(f"ℹ️  {old_name} (無需修改)")
            else:
                print(f"❌ {old_name}")
                print(f"   ⚠️  {result['message']}")
                error_count += 1
                
        except Exception as e:
            print(f"❌ {old_name}")
            print(f"   💥 處理錯誤: {str(e)}")
            error_count += 1
    
    print(f"\n📈 統計結果:")
    print(f"   總計檢查: {len(problematic_files)} 個檔案")
    print(f"   可以修復: {fixed_count} 個檔案")
    print(f"   處理錯誤: {error_count} 個檔案")
    
    if dry_run and fixed_count > 0:
        print(f"\n💡 要執行實際修復，請執行: python {__file__} --fix")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='修復音樂檔案命名問題')
    parser.add_argument('--fix', action='store_true', help='執行實際修復（預設為預覽模式）')
    parser.add_argument('--config', help='指定配置檔案路徑')
    
    args = parser.parse_args()
    
    # 載入配置
    try:
        config = load_config()
        paths = derive_paths(config)
        library_path = paths['library_path']
        
        if not library_path or not os.path.exists(library_path):
            print("❌ 音樂庫路徑不存在或未配置")
            return
            
    except Exception as e:
        print(f"❌ 載入配置失敗: {str(e)}")
        return
    
    # 執行修復
    fix_all_files(library_path, dry_run=not args.fix)

if __name__ == "__main__":
    main()
