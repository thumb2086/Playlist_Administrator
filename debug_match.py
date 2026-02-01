import os
import sys
from mutagen.id3 import ID3, EasyID3
from mutagen.flac import FLAC
from mutagen.mp4 import MP4
sys.path.insert(0, '.')
from core.library import get_normalized_tokens

def check_file(file_path):
    print(f"Checking: {file_path}")
    if not os.path.exists(file_path):
        print("File not found!")
        return
    
    filename = os.path.basename(file_path)
    name_no_ext = os.path.splitext(filename)[0]
    file_tokens = get_normalized_tokens(name_no_ext)
    print(f"Filename tokens: {file_tokens}")
    
    metadata_title = None
    metadata_artist = None
    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == '.mp3':
            try:
                audio = EasyID3(file_path)
                metadata_title = audio.get('title', [None])[0]
                metadata_artist = audio.get('artist', [None])[0]
            except:
                audio = ID3(file_path)
                if 'TIT2' in audio: metadata_title = str(audio['TIT2'])
                if 'TPE1' in audio: metadata_artist = str(audio['TPE1'])
        elif ext == '.flac':
            audio = FLAC(file_path)
            metadata_title = audio.get('TITLE', [None])[0]
            metadata_artist = audio.get('ARTIST', [None])[0]
    except Exception as e:
        print(f"Error reading metadata: {e}")
    
    print(f"Metadata Title: {metadata_title}")
    print(f"Metadata Artist: {metadata_artist}")
    if metadata_title:
        print(f"Metadata Title Tokens: {get_normalized_tokens(metadata_title)}")
    if metadata_artist:
        print(f"Metadata Artist Tokens: {get_normalized_tokens(metadata_artist)}")

if __name__ == "__main__":
    check_file("data/Music/夢想塗鴉冊.mp3")
    
    query = "GENBLUE幻藍小熊 - 夢想塗鴉冊 (Color Paper)"
    print(f"\nQuery: {query}")
    query_tokens = get_normalized_tokens(query)
    print(f"Query Tokens: {query_tokens}")
    
    title_part = query
    if ' - ' in query:
        title_part = query.split(' - ', 1)[1].strip()
    print(f"Title Part: {title_part}")
    title_tokens = get_normalized_tokens(title_part)
    print(f"Title Tokens: {title_tokens}")
