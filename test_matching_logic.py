
import os
import sys

# Add current directory to path
sys.path.append(os.getcwd())

from core.library import get_normalized_tokens, build_library_index, find_song_in_library, find_song_exact_format

def test_matching():
    # Test case 1: Single track name without artist, query is subset of filename
    song_query = "Memories Of You"
    filename = "Areeb Mahmood - Memories Of You.mp3"
    
    print(f"\nTesting Query: '{song_query}'")
    print(f"Target file: '{filename}'")
    
    query_tokens = tuple(get_normalized_tokens(song_query))
    file_tokens = tuple(get_normalized_tokens(os.path.splitext(filename)[0]))
    
    print(f"Query Tokens: {query_tokens}")
    print(f"File Tokens: {file_tokens}")
    
    # Simulate library index
    library_index = {
        file_tokens: ["/music/" + filename]
    }
    
    # 1. Test find_song_exact_format (Pre-scan logic)
    res_exact = find_song_exact_format(song_query, "mp3", library_index)
    print(f"find_song_exact_format result: {res_exact}")
    
    # 2. Test find_song_in_library (Deep scan logic)
    res_library = find_song_in_library(song_query, library_index)
    print(f"find_song_in_library result: {res_library}")
    
    # 3. Test Metadata Index Lookup
    metadata_index = {
        file_tokens: ["/music/" + filename]
    }
    res_metadata = find_song_in_library(song_query, {}, metadata_index=metadata_index)
    print(f"find_song_in_library (metadata index) result: {res_metadata}")
    
    if res_exact and res_library and res_metadata:
        print("\n✅ SUCCESS: All matching functions found the song!")
    else:
        print("\n❌ FAILURE: One or more functions failed to find the song.")

if __name__ == "__main__":
    test_matching()
