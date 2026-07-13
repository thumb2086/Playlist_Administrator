import urllib.request, xml.etree.ElementTree as ET, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')

urls = [
    ('default (limit=50)', 'https://feeds.soundcloud.com/users/soundcloud:users:735679489/sounds.rss'),
    ('limit=200', 'https://feeds.soundcloud.com/users/soundcloud:users:735679489/sounds.rss?limit=200'),
    ('limit=500', 'https://feeds.soundcloud.com/users/soundcloud:users:735679489/sounds.rss?limit=500'),
    ('limit=1000', 'https://feeds.soundcloud.com/users/soundcloud:users:735679489/sounds.rss?limit=1000'),
    ('limit=10000', 'https://feeds.soundcloud.com/users/soundcloud:users:735679489/sounds.rss?limit=10000'),
]

for label, url in urls:
    try:
        resp = urllib.request.urlopen(url, timeout=15)
        root = ET.fromstring(resp.read())
        items = root.findall('.//item')
        print(f'{label}: {len(items)} 集')
    except Exception as e:
        print(f'{label}: error - {e}')
