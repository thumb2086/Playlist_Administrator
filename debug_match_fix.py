
import os
import sys

# Mocking the get_normalized_tokens function from core.library
def get_normalized_tokens(text):
    import re
    from zhconv import convert
    
    text = str(text).lower()
    
    try:
        import re as regex
        def convert_chinese_only(match):
            chinese_text = match.group(0)
            try:
                return convert(chinese_text, 'zh-cn')
            except:
                return chinese_text
        text = regex.sub(r'[\u4e00-\u9fff]', convert_chinese_only, text)
    except:
        pass
        
    text = re.sub(r'^e(?=[a-z\u4e00-\u9fff\u3040-\u30ff])', '', text)
    text = re.sub(r'\s*(feat|ft|vs)\.?\s*|\s*[&,x]\s*', ' ', text)
    text = re.sub(r"[\(\[【][^\)\]】]*[\)\]】]", " ", text)
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+", " ", text)
    
    return sorted([t for t in text.split() if t])

def build_library_index(audio_files):
    index = {}
    for file_path in audio_files:
        filename = os.path.basename(file_path)
        name_no_ext = os.path.splitext(filename)[0]
        tokens_tuple = tuple(get_normalized_tokens(name_no_ext))
        if tokens_tuple:
            index[tokens_tuple] = file_path
    return index

def find_song_in_library(song_name, library_source):
    query_tokens = tuple(get_normalized_tokens(song_name))
    if not query_tokens: return None
    
    title_part = song_name.split(' - ', 1)[1].strip() if ' - ' in song_name else song_name.strip()
    title_tokens = tuple(get_normalized_tokens(title_part))
    
    print(f"Query: '{song_name}'")
    print(f"Query Tokens: {query_tokens}")
    print(f"Title Part: '{title_part}'")
    print(f"Title Tokens: {title_tokens}")
    
    if isinstance(library_source, dict):
        # 1. Exact match
        res = library_source.get(query_tokens)
        if res: 
            print("Found via Exact Match")
            return res
            
        # 2. Title match
        if title_tokens:
            res = library_source.get(title_tokens)
            if res:
                print("Found via Title Match")
                return res
        
        print("Not found in index.")
        return None

# Test Cases
files = [
    "C:\\Music\\SongABC.mp3",
    "C:\\Music\\SongDEF.mp3", 
    "C:\\Music\\ArtistX - SongGHI.mp3"
]

# Simulate user renaming "Artist - Title" to "Title"
# Case 1: Playlist has "Artist - SongABC", File is "SongABC.mp3"
print("--- Case 1: Artist - Title vs Title ---")
index = build_library_index(files)
print(f"Index keys: {list(index.keys())}")
find_song_in_library("ArtistA - SongABC", index)

# Case 2: Playlist has "Artist - SongXYZ", File is "SongXYZ.mp3" (Should match if file exists)
print("\n--- Case 2: Playlist 'ArtistB - SongDEF', File 'SongDEF.mp3' ---")
find_song_in_library("ArtistB - SongDEF", index)

# Case 3: Playlist "ArtistC - SongGHI", File "ArtistX - SongGHI.mp3"
print("\n--- Case 3: Playlist 'ArtistC - SongGHI', File 'ArtistX - SongGHI.mp3' ---")
# This fails exact match (ArtistC vs ArtistX)
# Should match title tokens? "SongGHI"
find_song_in_library("ArtistC - SongGHI", index)

