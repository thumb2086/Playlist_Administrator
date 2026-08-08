"""
比較 Spotube (m4a) vs spotdl (mp3) 下載品質
隨機抽樣 10 首歌，從 Spotube 的 m4a 資料夾隨機選歌，
用 spotdl 下載同一首到臨時資料夾，然後用 ffprobe 比較
"""
import os
import sys
import json
import subprocess
import random
import tempfile
import shutil

M4A_DIR = r"C:\Users\CPXru\Music\Spotube\m4a"
SAMPLE_N = 5

def ffprobe(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace"
        )
        return json.loads(r.stdout) if r.returncode == 0 else None
    except:
        return None

def get_meta(path):
    d = ffprobe(path)
    if not d: return {}
    fmt = d.get("format", {})
    streams = d.get("streams", [])
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    tags = fmt.get("tags", {})
    return {
        "size_mb": round(int(fmt.get("size", 0)) / 1048576, 2),
        "duration_s": round(float(fmt.get("duration", 0)), 1),
        "bitrate_kbps": round(int(fmt.get("bit_rate", 0)) / 1000),
        "codec": audio.get("codec_name", "?"),
        "sample_rate": audio.get("sample_rate", "?"),
        "channels": audio.get("channels", "?"),
        "title": tags.get("title", tags.get("TITLE", "")),
        "artist": tags.get("artist", tags.get("ARTIST", "")),
        "album": tags.get("album", tags.get("ALBUM", "")),
    }

# 隨機選歌
all_m4a = [f for f in os.listdir(M4A_DIR) if f.lower().endswith(".m4a")]
picked = random.sample(all_m4a, min(SAMPLE_N, len(all_m4a)))
print(f"=== 隨機抽樣 {len(picked)} 首比較 Spotube vs spotdl ===\n")

tmp_dir = tempfile.mkdtemp(prefix="spotdl_test_")
results = []

for i, m4a_name in enumerate(picked):
    stem = m4a_name.rsplit(".", 1)[0]
    m4a_path = os.path.join(M4A_DIR, m4a_name)
    m4a_meta = get_meta(m4a_path)
    if not m4a_meta:
        continue

    # 用 spotdl 下載同一首
    mp3_name = stem + ".mp3"
    mp3_path = os.path.join(tmp_dir, mp3_name)
    print(f"[{i+1}/{len(picked)}] {stem[:50]}")
    print(f"  Spotube: {m4a_meta['bitrate_kbps']}kbps {m4a_meta['codec']} {m4a_meta['size_mb']}MB")

    try:
        # spotdl download via python module
        r = subprocess.run(
            [sys.executable, "-m", "spotdl", "download", stem, "--output", tmp_dir, "--format", "mp3"],
            capture_output=True, text=True, timeout=90, encoding="utf-8", errors="replace"
        )
        # 找到下載的檔案
        downloaded = [f for f in os.listdir(tmp_dir) if f.lower().endswith(".mp3") and stem[:20].lower() in f.lower()]
        if not downloaded:
            # 嘗試用歌名搜尋
            downloaded = [f for f in os.listdir(tmp_dir) if f.lower().endswith(".mp3")]
            if downloaded:
                mp3_path = os.path.join(tmp_dir, downloaded[-1])
            else:
                print(f"  spotdl: 下載失敗")
                continue
        else:
            mp3_path = os.path.join(tmp_dir, downloaded[0])

        mp3_meta = get_meta(mp3_path)
        if not mp3_meta:
            print(f"  spotdl: 無法分析")
            continue

        print(f"  spotdl: {mp3_meta['bitrate_kbps']}kbps {mp3_meta['codec']} {mp3_meta['size_mb']}MB")
        print(f"  Duration: {m4a_meta['duration_s']}s vs {mp3_meta['duration_s']}s")
        print()

        results.append({
            "name": stem[:40],
            "m4a": m4a_meta,
            "mp3": mp3_meta,
            "bitrate_diff": mp3_meta['bitrate_kbps'] - m4a_meta['bitrate_kbps'],
            "duration_diff": abs(mp3_meta['duration_s'] - m4a_meta['duration_s']),
        })
    except Exception as e:
        print(f"  spotdl 錯誤: {e}\n")

# 匯總
if results:
    print(f"\n{'='*60}")
    print(f"=== 匯總 ({len(results)} 首成功比對) ===")
    print(f"{'='*60}\n")

    avg_m4a_br = sum(r['m4a']['bitrate_kbps'] for r in results) / len(results)
    avg_mp3_br = sum(r['mp3']['bitrate_kbps'] for r in results) / len(results)
    avg_m4a_size = sum(r['m4a']['size_mb'] for r in results) / len(results)
    avg_mp3_size = sum(r['mp3']['size_mb'] for r in results) / len(results)
    avg_br_diff = sum(r['bitrate_diff'] for r in results) / len(results)
    avg_dur_diff = sum(r['duration_diff'] for r in results) / len(results)

    print(f"{'指標':<20} {'Spotube (m4a)':<20} {'spotdl (mp3)':<20}")
    print(f"{'-'*60}")
    print(f"{'平均位元率':<20} {avg_m4a_br:.0f} kbps{'':<12} {avg_mp3_br:.0f} kbps")
    print(f"{'平均大小':<20} {avg_m4a_size:.1f} MB{'':<14} {avg_mp3_size:.1f} MB")
    print(f"{'位元率差異':<20} {'':<20} {avg_br_diff:+.0f} kbps")
    print(f"{'時長差異':<20} {'':<20} {avg_dur_diff:.1f}s")
    print()

    # metadata 比較
    m4a_meta_count = sum(1 for r in results if r['m4a']['title'] or r['m4a']['artist'])
    mp3_meta_count = sum(1 for r in results if r['mp3']['title'] or r['mp3']['artist'])
    print(f"M4A 有 metadata: {m4a_meta_count}/{len(results)}")
    print(f"MP3 有 metadata: {mp3_meta_count}/{len(results)}")

    print(f"\n--- 明細 ---")
    for r in results:
        br_icon = "↑" if r['bitrate_diff'] > 0 else ("↓" if r['bitrate_diff'] < 0 else "=")
        print(f"  {r['name'][:35]:<37} M4A:{r['m4a']['bitrate_kbps']:>4}kbps → MP3:{r['mp3']['bitrate_kbps']:>4}kbps {br_icon}{abs(r['bitrate_diff']):>3}")

# 清理
shutil.rmtree(tmp_dir, ignore_errors=True)
print("\n實驗完成")
