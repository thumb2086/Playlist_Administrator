
import os
import sys
from core.library import get_normalized_tokens, find_song_exact_format, find_song_prefer_flac, build_library_index, find_song_in_library

def test_search():
    print("🧪 Testing Search Logic...")
    
    # Check zhconv directly
    try:
        from zhconv import convert
        test_t = "依著光"
        print(f"  zhconv ('著') Test: '{test_t}' -> '{convert(test_t, 'zh-cn')}'")
        test_q = "中國"
        print(f"  zhconv ('國') Test: '{test_q}' -> '{convert(test_q, 'zh-cn')}'")
    except ImportError:
        print("  zhconv NOT INSTALLED!")
    
    # ---------------------------------------------------------
    # User's Problematic Case: '依著光'
    # ---------------------------------------------------------
    playlist_entry = "依著光"
    existing_file = "告五人 - 依著光.flac"
    
    print(f"\nTesting: '{playlist_entry}' vs '{existing_file}'")
    
    library_files = [os.path.abspath(existing_file)]
    library_index = build_library_index(library_files)
    
    # Pass 1 Logic (Scan)
    match1 = find_song_exact_format(playlist_entry, "flac", library_index)
    print(f"  Scan Pass 1 (find_song_exact_format): {'✅ Found' if match1 else '❌ Not Found'}")
    
    # Pass 2 Logic (Scan - Metadata)
    match2 = find_song_in_library(playlist_entry, library_index)
    print(f"  Scan Pass 2 (find_song_in_library): {'✅ Found' if match2 else '❌ Not Found'}")
    
    # Downloader Logic
    match3 = find_song_prefer_flac(playlist_entry, library_files)
    print(f"  Downloader Pass (find_song_prefer_flac): {'✅ Found' if match3 else '❌ Not Found'}")

    # Case 2: Traditional vs Simplified
    playlist_entry2 = "依著光"
    existing_file2 = "告五人 - 依着光.flac" # Simplified '着'
    print(f"\nTesting (Simplified File): '{playlist_entry2}' vs '{existing_file2}'")
    
    p_tokens = get_normalized_tokens(playlist_entry2)
    f_tokens = get_normalized_tokens("告五人 - 依着光")
    print(f"  Playlist Tokens: {p_tokens}")
    print(f"  File Tokens:     {f_tokens}")
    
    library_index2 = build_library_index([os.path.abspath(existing_file2)])
    print(f"  Index Keys: {list(library_index2.keys())}")
    
    match_s = find_song_exact_format(playlist_entry2, "flac", library_index2)
    print(f"  Scan Pass 1: {'✅ Found' if match_s else '❌ Not Found'}")

if __name__ == "__main__":
    test_search()
