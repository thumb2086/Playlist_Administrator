import urllib.request, json, urllib.parse, sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')

for name in ['游庭皓的財經皓角', '晨間財經速解讀']:
    url = 'https://itunes.apple.com/search?term=' + urllib.parse.quote(name) + '&media=podcast&limit=1'
    resp = urllib.request.urlopen(url, timeout=10)
    data = json.loads(resp.read())
    if data['resultCount'] > 0:
        r = data['results'][0]
        print(r['collectionName'])
        print('  作者:', r.get('artistName', '?'))
        print('  集數:', r.get('trackCount', '?'))
        print('  RSS:', r.get('feedUrl', '?'))
    else:
        print(name, ': 沒找到')
    print()
