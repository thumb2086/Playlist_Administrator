"""
Convert SRT subtitles to clean TXT (strip timestamps, keep only text).
Also removes duplicate consecutive lines from auto-generated captions.
"""
import os, re, sys, glob

def srt_to_text(srt_path):
    with open(srt_path, encoding='utf-8') as f:
        content = f.read()

    lines = content.strip().split('\n')
    text_lines = []
    last = ''

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip number lines (just digits)
        if re.match(r'^\d+$', line):
            continue
        # Skip timestamp lines
        if '-->' in line:
            continue
        # Skip HTML tags like <font>, <i>, etc.
        line = re.sub(r'<[^>]+>', '', line)
        # Skip duplicate consecutive text (auto-caption glitch)
        if line == last:
            continue
        text_lines.append(line)
        last = line

    return '\n'.join(text_lines)

def process_dir(dir_path):
    srt_files = glob.glob(os.path.join(dir_path, '*.srt'))
    converted = 0
    for srt in srt_files:
        txt_path = srt.replace('.srt', '.txt')
        text = srt_to_text(srt)
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(text)
        converted += 1
    return converted

if __name__ == '__main__':
    base = r'C:\Users\CPXru\Music\Spotube\podcast_downloads'
    total = 0
    for entry in sorted(os.listdir(base)):
        pod_dir = os.path.join(base, entry)
        if not os.path.isdir(pod_dir):
            continue
        c = process_dir(pod_dir)
        if c > 0:
            print(f'{entry}: {c} SRT → TXT')
        total += c
    print(f'共轉換 {total} 個檔案')
