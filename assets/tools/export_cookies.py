"""
Export browser cookies for yt-dlp to bypass YouTube rate limiting.
"""
import subprocess, sys, os

cookies_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'music', 'yt_cookies.txt')

for browser in ['chrome', 'edge', 'firefox', 'brave', 'opera']:
    print(f'Trying {browser}...')
    r = subprocess.run(
        ['yt-dlp', '--cookies-from-browser', browser, '--cookies', cookies_file,
         '--skip-download', '--print', 'id', 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'],
        capture_output=True, timeout=30, encoding='utf-8', errors='replace')
    if r.returncode == 0 and os.path.exists(cookies_file) and os.path.getsize(cookies_file) > 0:
        print(f'  ✅ Cookies exported from {browser} to {cookies_file}')
        sys.exit(0)
    else:
        err = r.stderr.strip()[:120].replace('\n', ' ')
        print(f'  ❌ {err}')

print('Failed to export cookies from any browser')
sys.exit(1)
