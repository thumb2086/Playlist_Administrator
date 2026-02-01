#!/usr/bin/env python3
"""
批次重新命名音樂檔案工具
將所有歌曲統一命名為: 歌手 - 歌名.mp3 格式
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.file_renamer import create_file_renamer
from utils.config import load_config
from utils.helpers import sanitize_filename

def batch_rename_songs(dry_run=True):
    """批次重新命名所有歌曲"""
    print("🎵 批次重新命名工具")
    print("=" * 50)
    
    if dry_run:
        print("⚠️  預覽模式 - 不會實際更改任何檔案")
    else:
        print("🔥 執行模式 - 將會實際重新命名檔案！")
    print()
    
    # Load config
    config = load_config()
    if not config or 'library_path' not in config:
        print("❌ 無法載入配置或 library_path 未設定")
        return
    
    library_path = config['library_path']
    print(f"📁 音樂庫路徑：{library_path}")
    
    # Create renamer
    renamer = create_file_renamer(library_path)
    
    # Scan library
    audio_files = renamer.scan_library(recursive=True)
    print(f"🔍 找到 {len(audio_files)} 個音樂檔案")
    print()
    
    # Process files
    changes = []
    errors = []
    skipped = []
    
    for file_path in audio_files:
        filename = os.path.basename(file_path)
        metadata = renamer.extract_metadata(file_path)
        
        if not metadata:
            errors.append((file_path, "無法讀取 metadata"))
            continue
        
        artist = metadata.get('artist', '').strip()
        title = metadata.get('title', '').strip()
        
        if not title:
            # Try to extract title from filename
            name_no_ext = os.path.splitext(filename)[0]
            if ' - ' in name_no_ext:
                parts = name_no_ext.split(' - ', 1)
                if len(parts) == 2:
                    title = parts[1].strip()
                else:
                    title = name_no_ext
            else:
                title = name_no_ext
        
        if not title:
            errors.append((file_path, "無法確定歌名"))
            continue
        
        # Generate new filename: 歌手 - 歌名.ext or just 歌名.ext
        file_ext = Path(file_path).suffix.lower()
        
        if artist:
            new_name = f"{sanitize_filename(artist)} - {sanitize_filename(title)}{file_ext}"
        else:
            new_name = f"{sanitize_filename(title)}{file_ext}"
        
        # Check if rename is needed
        if filename == new_name:
            skipped.append(file_path)
            continue
        
        new_path = Path(file_path).parent / new_name
        
        # Check for conflicts
        if new_path.exists() and str(new_path) != file_path:
            errors.append((file_path, f"目標檔案已存在: {new_name}"))
            continue
        
        changes.append({
            'old_path': file_path,
            'new_path': str(new_path),
            'old_name': filename,
            'new_name': new_name
        })
    
    # Report
    print(f"📊 分析結果：")
    print(f"   ✅ 需要重新命名：{len(changes)} 個")
    print(f"   ⏭️  已經正確：{len(skipped)} 個")
    print(f"   ❌ 無法處理：{len(errors)} 個")
    print()
    
    if changes:
        print("📝 變更預覽 (前20個)：")
        for i, change in enumerate(changes[:20], 1):
            print(f"   {i}. {change['old_name']}")
            print(f"      → {change['new_name']}")
        
        if len(changes) > 20:
            print(f"   ... 還有 {len(changes) - 20} 個變更")
        print()
    
    if errors:
        print("❌ 錯誤列表 (前10個)：")
        for path, reason in errors[:10]:
            print(f"   - {os.path.basename(path)}: {reason}")
        print()
    
    # Execute if not dry run
    if not dry_run and changes:
        print("🔄 開始重新命名...")
        success = 0
        for change in changes:
            try:
                import shutil
                shutil.move(change['old_path'], change['new_path'])
                success += 1
            except Exception as e:
                print(f"   ❌ 失敗: {change['old_name']} - {e}")
        
        print(f"✅ 完成！成功重新命名 {success}/{len(changes)} 個檔案")
    elif not dry_run:
        print("✅ 沒有需要變更的檔案")
    else:
        print("💡 如果確認無誤，請執行:")
        print("   .venv\\Scripts\\python.exe rename_all_songs.py --execute")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="批次重新命名音樂檔案")
    parser.add_argument('--execute', action='store_true', help='實際執行重新命名 (預設為預覽模式)')
    args = parser.parse_args()
    
    batch_rename_songs(dry_run=not args.execute)
