"""Check if specific YouTube videos have subtitles."""
import subprocess

videos = [
    ('BBiBV1cZIPw', 'XEP15'),
    ('YJCPm-uYHW0', 'XEP14'),
    ('_EiepB7lttA', 'XEP13'),
    ('QVIR61JR2G8', 'XEP12'),
    ('JhWFVzaVEDI', 'XEP11'),
    ('7sVSh1N9v2k', 'XEP10'),
    ('NZGYUCHpm0w', 'user提供的'),
]

cookie = r'C:\Users\CPXru\Desktop\thumb\大拇哥實驗室\cookies.txt'

for vid, label in videos:
    r = subprocess.run(
        ['yt-dlp', '--cookies', cookie, '--list-subs', f'https://www.youtube.com/watch?v={vid}'],
        capture_output=True, timeout=30, encoding='utf-8', errors='replace')
    has_manual = 'zh-TW' in r.stdout
    has_auto = 'zh-Hant' in r.stdout
    no_subs = 'has no' in r.stdout
    status = '✅ MANUAL zh-TW' if has_manual else ('⚠️ AUTO only' if has_auto else '❌ NO SUBS')
    print(f'{label:12s} ({vid}): {status}')
