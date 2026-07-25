"""
Batch download YouTube subtitles for all podcast audio files.
Uses yt-dlp with rate limiting to avoid 429 errors.
Saves as .srt (timed) or falls back to .txt (plain transcript renamed to .srt).
"""
import os, sys, glob, re, subprocess, threading, time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

lock = threading.Lock()
ytdl = 'yt-dlp'
cookies_file = r'C:\Users\CPXru\Desktop\thumb\大拇哥實驗室\cookies.txt'

def download_subs_single(audio_path, podcast_name):
    base = os.path.splitext(audio_path)[0]
    srt_path = base + '.srt'
    if os.path.exists(srt_path):
        return 'skip'

    title = os.path.splitext(os.path.basename(audio_path))[0]
    # Clean up title for YouTube search
    search_title = re.sub(r'^EP\d+\s*[-–—]\s*', '', title).strip()
    search_title = search_title.replace('_', ' ').replace('【', '').replace('】', '').replace('｜', ' ').replace('（', ' ').replace('）', ' ').replace('[', '').replace(']', '')
    search_title = re.sub(r'\s+', ' ', search_title).strip()
    query = f'{search_title} {podcast_name}'

    cmd = [ytdl, '--cookies', cookies_file, f'ytsearch:{query}',
           '--skip-download',
           '--write-subs', '--write-auto-subs',
           '--sub-langs', 'zh-TW,zh-Hant,zh-Hans,zh,en',
           '--sub-format', 'srt',
           '--output', base + '.%(ext)s',
           '--quiet', '--no-warnings',
           '--windows-filenames',
           '--retries', '3',
           '--sleep-requests', '1.5',
           '--throttled-rate', '100K']

    try:
        r = subprocess.run(cmd, capture_output=True, timeout=60,
                          encoding='utf-8', errors='replace')
        stderr = r.stderr.lower()
        if 'error' in stderr and '429' in stderr:
            return 'ratelimit'

        dir_name = os.path.dirname(audio_path)
        base_name = os.path.basename(base)

        # Check for .srt first (timed subtitles)
        srt_candidates = [f for f in os.listdir(dir_name) if f.startswith(base_name) and f.endswith('.srt')]
        if srt_candidates:
            src = os.path.join(dir_name, srt_candidates[0])
            if src != srt_path:
                os.replace(src, srt_path)
            # Clean up extra .srt files (language variants)
            for f in srt_candidates[1:]:
                try: os.remove(os.path.join(dir_name, f))
                except: pass
            return 'ok'

        # Fallback: check for .txt (plain transcript without timestamps)
        txt_candidates = [f for f in os.listdir(dir_name) if f.startswith(base_name) and f.endswith('.txt')]
        if txt_candidates:
            src = os.path.join(dir_name, txt_candidates[0])
            os.replace(src, srt_path)  # Rename .txt → .srt
            for f in txt_candidates[1:]:
                try: os.remove(os.path.join(dir_name, f))
                except: pass
            return 'ok'

        # Clean up leftover junk like .vtt
        for f in os.listdir(dir_name):
            if f.startswith(base_name) and f != os.path.basename(audio_path):
                try: os.remove(os.path.join(dir_name, f))
                except: pass

        if 'no subtitles' in stderr or 'no video' in stderr:
            return 'nosubs'
        return 'notfound'
    except subprocess.TimeoutExpired:
        return 'timeout'
    except Exception as e:
        return f'error:{str(e)[:60]}'


def process_podcast(podcast_dir):
    podcast_name = os.path.basename(podcast_dir)
    audio_files = []
    for ext in ('*.mp3', '*.m4a', '*.wav', '*.flac'):
        audio_files.extend(glob.glob(os.path.join(podcast_dir, ext)))

    to_process = [af for af in audio_files if not os.path.exists(os.path.splitext(af)[0] + '.srt')]
    if not to_process:
        return 0, 0, 0, 0, 0

    total = len(to_process)
    ok = notfound = nosubs = ratelimit = errors = 0
    done = 0

    print(f'\n[{podcast_name}] 需下載 {total}/{len(audio_files)} 個字幕')

    for af in to_process:
        result = download_subs_single(af, podcast_name)
        done += 1
        if done % 5 == 0 or done == total:
            print(f'\r  [{podcast_name}] {done}/{total} (✅{ok} ⚠️{nosubs} ❓{notfound} 🐢{ratelimit})', end='', flush=True)

        if result == 'ok':
            ok += 1
        elif result == 'notfound':
            notfound += 1
        elif result == 'nosubs':
            nosubs += 1
        elif result == 'ratelimit':
            ratelimit += 1
            if ratelimit <= 3:
                time.sleep(5)
        else:
            errors += 1
            if errors <= 5:
                with lock:
                    print(f'\n  ❌ {os.path.basename(af)}: {result}')

        time.sleep(1.0)

    print(f'\n  [{podcast_name}] 完成: ✅ {ok} ⚠️{nosubs} ❓{notfound} 🐢{ratelimit} ❌{errors}')
    return ok, notfound, nosubs, ratelimit, errors


def main():
    base = r'C:\Users\CPXru\Music\Spotube\podcast_downloads'
    if not os.path.exists(base):
        print(f'Podcast 目錄不存在: {base}')
        return

    total_ok = total_notfound = total_nosubs = total_ratelimit = total_errors = 0
    for entry in sorted(os.listdir(base)):
        pod_dir = os.path.join(base, entry)
        if not os.path.isdir(pod_dir):
            continue
        ok, nf, ns, rl, err = process_podcast(pod_dir)
        total_ok += ok
        total_notfound += nf
        total_nosubs += ns
        total_ratelimit += rl
        total_errors += err

    print(f'\n=== 全部完成 ===')
    print(f'成功: {total_ok}, 找不到: {total_notfound}, 無字幕: {total_nosubs}, 限流: {total_ratelimit}, 錯誤: {total_errors}')


if __name__ == '__main__':
    main()
