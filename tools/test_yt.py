import sys, time
sys.stdout.reconfigure(encoding='utf-8')
import yt_dlp

start = time.time()
try:
    ydl_opts = {
        'format': 'bestaudio',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'socket_timeout': 15,
        'extractor_args': {'youtube': {'player_client': ['web', 'tv']}},
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info('ytsearch1:Hootie Frutti Kpop', download=False)
        e = info['entries'][0]
        url = e.get('url', '')
        title = e.get('title', '')
        print('title:', title)
        print('url:', url[:100])
        print('time: %.1fs' % (time.time() - start))
except Exception as ex:
    print('ERROR after %.1fs: %s' % (time.time() - start, ex))
