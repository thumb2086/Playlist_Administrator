import requests
from bs4 import BeautifulSoup
import json

url = "https://open.spotify.com/embed/playlist/37i9dQZF1E3ahvZ5s71oFH"
headers = {'User-Agent': 'Mozilla/5.0'}
resp = requests.get(url, headers=headers)
soup = BeautifulSoup(resp.text, 'html.parser')

next_data = soup.find("script", {"id": "__NEXT_DATA__"})
if next_data:
    data = json.loads(next_data.string)
    # Print the specific path we were looking for
    try:
        entity = data['props']['pageProps']['state']['data']['entity']
        print(f"Name found: {entity.get('name')}")
    except KeyError as e:
        print(f"Path failed at: {e}")
        # Print keys to help find where it is
        print("Top keys:", data.keys())
        if 'props' in data:
            print("probs keys:", data['props'].keys())
            if 'pageProps' in data['props']:
                print("pageProps keys:", data['props']['pageProps'].keys())

else:
    print("No NEXT_DATA found")
