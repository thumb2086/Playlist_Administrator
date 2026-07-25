"""清除 metadata 更名造成的重複 MP3（與 M4A 檔名不一致的舊檔）"""

import os
import sys
from pathlib import Path

def get_stem(path):
    return Path(path).stem.lower()

def main():
    if len(sys.argv) < 2:
        base = input("請輸入 Music 目錄路徑 (例如 C:\\Users\\CPXru\\Music\\Spotube): ").strip()
    else:
        base = sys.argv[1]

    mp3_dir = os.path.join(base, "mp3")
    m4a_dir = os.path.join(base, "m4a")

    if not os.path.isdir(mp3_dir) or not os.path.isdir(m4a_dir):
        print("錯誤：找不到 mp3 或 m4a 目錄")
        return 1

    # 收集所有 M4A stem
    m4a_stems = set()
    for f in os.listdir(m4a_dir):
        if f.lower().endswith('.m4a'):
            m4a_stems.add(get_stem(f))

    # 掃描 MP3，找出 stem 不在 M4A 中的（metadata 更名過的舊檔）
    orphans = []
    for f in os.listdir(mp3_dir):
        if f.lower().endswith('.mp3'):
            if get_stem(f) not in m4a_stems:
                orphans.append(f)

    if not orphans:
        print("✅ 沒有發現重複/孤兒 MP3 檔案")
        return 0

    print(f"\n⚠️  找到 {len(orphans)} 個可能的重複 MP3（metadata 更名版，與 M4A 檔名不一致）：\n")
    for f in sorted(orphans):
        size = os.path.getsize(os.path.join(mp3_dir, f))
        print(f"  {f}  ({size / 1024 / 1024:.1f} MB)")

    confirm = input(f"\n是否刪除這些 {len(orphans)} 個檔案？(y/N): ").strip().lower()
    if confirm == 'y':
        deleted = 0
        for f in orphans:
            path = os.path.join(mp3_dir, f)
            os.remove(path)
            deleted += 1
            print(f"  ✕ 已刪除: {f}")
        print(f"\n✅ 已完成，刪除 {deleted} 個檔案")
    else:
        print("跳過刪除。")

    return 0

if __name__ == "__main__":
    sys.exit(main())
