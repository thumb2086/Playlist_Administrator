"""
用 spotdl 隨機下載 3 首歌，與 Spotube M4A 比較
"""
import os
import sys
import json
import subprocess
import random
import tempfile

M4A_DIR = r"C:\Users\CPXru\Music\Spotube\m4a"
OUT_DIR = r"C:\Users\CPXru\Desktop\thumb\program\Playlist_Administrator\tools\spotdl_test"
SAMPLE_N = 3

def ffprobe(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace"
        )
        return json.loads(r.stdout) if r.returncode == 0 else None
    except:
        return None

os.makedirs(OUT_DIR, exist_ok=True)
all_m4a = [f for f in os.listdir(M4A_DIR) if f.lower().endswith(".m4a")]
picked = random.sample(all_m4a, min(SAMPLE_N, len(all_m4a)))

print(f"=== 隨機下載 {len(picked)} 首歌比較 ===\n")

for i, m4a_name in enumerate(picked):
    stem = m4a_name.rsplit(".", 1)[0]
    m4a_path = os.path.join(M4A_DIR, m4a_name)

    # Spotube M4A 分析
    m4a_d = ffprobe(m4a_path)
    m4a_fmt = m4a_d.get("format", {}) if m4a_d else {}
    m4a_tags = m4a_fmt.get("tags", {})
    m4a_br = round(int(m4a_fmt.get("bit_rate", 0)) / 1000)
    m4a_sz = round(int(m4a_fmt.get("size", 0)) / 1048576, 2)
    m4a_dur = round(float(m4a_fmt.get("duration", 0)), 1)

    print(f"[{i+1}/{len(picked)}] {stem[:55]}")
    print(f"  Spotube M4A: {m4a_br}kbps  {m4a_sz}MB  {m4a_dur}s")
    if m4a_tags.get("title"):
        print(f"  Metadata: {m4a_tags.get('artist','')} - {m4a_tags.get('title','')}")

    # spotdl 下載
    print(f"  spotdl 下載中...")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "spotdl", "download", stem, "--output", OUT_DIR, "--format", "mp3"],
            capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace"
        )
        # 找下載的檔案
        downloaded = [f for f in os.listdir(OUT_DIR) if f.lower().endswith(".mp3")]
        if not downloaded:
            print(f"  spotdl: 下載失敗 (可能搜不到或超時)")
            print()
            continue

        mp3_path = os.path.join(OUT_DIR, downloaded[-1])
        mp3_d = ffprobe(mp3_path)
        mp3_fmt = mp3_d.get("format", {}) if mp3_d else {}
        mp3_tags = mp3_fmt.get("tags", {})
        mp3_br = round(int(mp3_fmt.get("bit_rate", 0)) / 1000)
        mp3_sz = round(int(mp3_fmt.get("size", 0)) / 1048576, 2)
        mp3_dur = round(float(mp3_fmt.get("duration", 0)), 1)

        print(f"  spotdl MP3:  {mp3_br}kbps  {mp3_sz}MB  {mp3_dur}s")
        if mp3_tags.get("title"):
            print(f"  Metadata: {mp3_tags.get('artist','')} - {mp3_tags.get('title','')}")

        dur_diff = abs(m4a_dur - mp3_dur)
        br_diff = mp3_br - m4a_br
        print(f"  差異: 位元率 {br_diff:+}kbps  時長差 {dur_diff}s  大小 {mp3_sz - m4a_sz:+.1f}MB")
    except subprocess.TimeoutExpired:
        print(f"  spotdl: 超時 (>120s)")
    except Exception as e:
        print(f"  spotdl: 錯誤 {e}")
    print()

# 清理
print(f"下載檔案在: {OUT_DIR}")
print("實驗完成")
