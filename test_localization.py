import requests
from bs4 import BeautifulSoup
import json

# URL provided by user in config
url = "https://open.spotify.com/embed/playlist/37i9dQZF1E3ahvZ5s71oFH"

# Test 1: No Language Header
print("Testing without language header...")
headers1 = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
resp1 = requests.get(url, headers=headers1)

def check_artist(html, case_name):
    soup = BeautifulSoup(html, 'html.parser')
    next_data = soup.find("script", {"id": "__NEXT_DATA__"})
    if next_data:
        data = json.loads(next_data.string)
        try:
            track_list = data['props']['pageProps']['state']['data']['entity']['trackList']
            # Find the song "今天星期六"
            for item in track_list:
                track = item.get('track', item)
                name = track.get('name')
                if "今天星期六" in name:
                    artists = track.get('artists', [])
                    if artists:
                        print(f"[{case_name}] Found song: {name}")
                        print(f"[{case_name}] Artist: {artists[0]['name']}")
                        return
            print(f"[{case_name}] Song '今天星期六' not found in first page")
        except Exception as e:
            print(f"Error parsing: {e}")

check_artist(resp1.text, "No Header")

# Test 2: With TW Header
print("\nTesting with zh-TW header...")
headers2 = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7'
}
resp2 = requests.get(url, headers=headers2)
check_artist(resp2.text, "With zh-TW")
