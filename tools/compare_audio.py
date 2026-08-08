"""
隨機抽樣實驗：比較 Spotube 下載的 M4A 與轉檔後的 MP3
分析音訊品質、metadata、位元率等差異
"""
import os
import json
import subprocess
import random

BASE = r"C:\Users\CPXru\Music\Spotube"
M4A_DIR = os.path.join(BASE, "m4a")
MP3_DIR = os.path.join(BASE, "mp3")
SAMPLE_N = 15

def ffprobe(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=10
        )
        return json.loads(r.stdout) if r.returncode == 0 else None
    except:
        return None

def analyze(path):
    d = ffprobe(path)
    if not d:
        return None
    fmt = d.get("format", {})
    streams = d.get("streams", [])
    audio = next((s for s in streams if s.get("codec_type") == "audio"), {})
    tags = fmt.get("tags", {})
    return {
        "name": os.path.basename(path),
        "size_mb": round(int(fmt.get("size", 0)) / 1048576, 2),
        "duration_s": round(float(fmt.get("duration", 0)), 1),
        "bitrate_kbps": round(int(fmt.get("bit_rate", 0)) / 1000),
        "codec": audio.get("codec_name", "?"),
        "sample_rate": audio.get("sample_rate", "?"),
        "channels": audio.get("channels", "?"),
        "bits_per_sample": audio.get("bits_per_sample", "?"),
        "title": tags.get("title", tags.get("TITLE", "")),
        "artist": tags.get("artist", tags.get("ARTIST", "")),
        "album": tags.get("album", tags.get("ALBUM", "")),
    }

def sample_files(directory, ext, n):
    files = [os.path.join(directory, f) for f in os.listdir(directory) if f.lower().endswith(ext)]
    return random.sample(files, min(n, len(files)))

print(f"=== 隨機抽樣 {SAMPLE_N} 首 ===\n")

m4a_files = sample_files(M4A_DIR, ".m4a", SAMPLE_N)
mp3_files = sample_files(MP3_DIR, ".mp3", SAMPLE_N)

m4a_results = [analyze(f) for f in m4a_files]
mp3_results = [analyze(f) for f in mp3_files]
m4a_results = [r for r in m4a_results if r]
mp3_results = [r for r in mp3_results if r]

def avg(lst, key):
    vals = [r[key] for r in lst if isinstance(r[key], (int, float))]
    return round(sum(vals) / len(vals), 1) if vals else 0

def fmt_bitrate(kbps):
    if kbps >= 300: return f"{kbps}kbps (高)"
    if kbps >= 200: return f"{kbps}kbps (中)"
    return f"{kbps}kbps (低)"

print(f"{'指標':<18} {'M4A (Spotube)':<20} {'MP3 (轉檔)':<20}")
print("-" * 58)
print(f"{'平均大小':<18} {avg(m4a_results, 'size_mb')} MB{'':<12} {avg(mp3_results, 'size_mb')} MB")
print(f"{'平均時長':<18} {avg(m4a_results, 'duration_s')}s{'':<13} {avg(mp3_results, 'duration_s')}s")
print(f"{'平均位元率':<18} {fmt_bitrate(avg(m4a_results, 'bitrate_kbps')):<20} {fmt_bitrate(avg(mp3_results, 'bitrate_kbps'))}")
print(f"{'編碼':<18} {m4a_results[0]['codec'] if m4a_results else '?':<20} {mp3_results[0]['codec'] if mp3_results else '?'}")
print(f"{'取樣率':<18} {m4a_results[0]['sample_rate'] if m4a_results else '?':<20} {mp3_results[0]['sample_rate'] if mp3_results else '?'}")
print(f"{'聲道':<18} {m4a_results[0]['channels'] if m4a_results else '?':<20} {mp3_results[0]['channels'] if mp3_results else '?'}")
print()

m4a_has_meta = sum(1 for r in m4a_results if r["title"] or r["artist"])
mp3_has_meta = sum(1 for r in mp3_results if r["title"] or r["artist"])
print(f"M4A 有 metadata: {m4a_has_meta}/{len(m4a_results)}")
print(f"MP3 有 metadata: {mp3_has_meta}/{len(mp3_results)}")

if m4a_has_meta > 0:
    print(f"\n--- M4A Metadata 樣本 ---")
    for r in m4a_results[:5]:
        if r["title"] or r["artist"]:
            print(f"  {r['name'][:40]:<42} | {r['artist'][:15]} - {r['title'][:25]}")

if mp3_has_meta > 0:
    print(f"\n--- MP3 Metadata 樣本 ---")
    for r in mp3_results[:5]:
        if r["title"] or r["artist"]:
            print(f"  {r['name'][:40]:<42} | {r['artist'][:15]} - {r['title'][:25]}")

# 檢查 M4A→MP3 配對
print(f"\n--- 配對比對 (同名 M4A→MP3) ---")
matched = 0
mismatched = 0
for mr in m4a_results[:5]:
    stem = mr["name"].rsplit(".", 1)[0]
    mp3_match = next((pr for pr in mp3_results if pr["name"].startswith(stem)), None)
    if mp3_match:
        matched += 1
        diff_dur = abs(mr["duration_s"] - mp3_match["duration_s"])
        print(f"  ✓ {stem[:35]:<37} M4A:{mr['bitrate_kbps']}kbps → MP3:{mp3_match['bitrate_kbps']}kbps (時長差 {diff_dur}s)")
    else:
        mismatched += 1
        print(f"  ✗ {stem[:35]:<37} M4A 存在但 MP3 未找到配對")

print(f"\n配對: {matched}/{matched+mismatched}")
print("實驗完成")
