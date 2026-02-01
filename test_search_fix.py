import os
import sys

# Setup environment
sys.path.insert(0, '.')
from core.library import get_normalized_tokens, find_song_in_library, build_library_index

def run_test():
    print("🧪 Running Verification for Improved Matching Logic...")
    
    # Mock library files
    library_files = [
        "data/Music/夢想塗鴉冊.mp3",
        "data/Music/Rockstar.mp3",
        "data/Music/告五人 - 癒合.mp3",
        "data/Music/破碎的薔薇.mp3"
    ]
    
    # Build a mock index
    index = build_library_index(library_files)
    print("\nLibrary Index Tokens:")
    for tokens in index:
        print(f"  {tokens} -> {index[tokens]}")
    
    test_cases = [
        {
            "query": "GENBLUE幻藍小熊 - 夢想塗鴉冊 (Color Paper)",
            "expected": "data/Music/夢想塗鴉冊.mp3"
        },
        {
            "query": "dxs-Rockstar",
            "expected": "data/Music/Rockstar.mp3"
        },
        {
            "query": "福夢 - 破碎的薔薇 (stripped)",
            "expected": "data/Music/破碎的薔薇.mp3"
        },
        {
            "query": "癒合",
            "expected": "data/Music/告五人 - 癒合.mp3"
        },
        {
            "query": "Post Malone - Rockstar",
            "expected": "data/Music/Rockstar.mp3"
        }
    ]
    
    passed = 0
    for case in test_cases:
        query = case["query"]
        expected = case["expected"]
        print(f"\nSearching for: '{query}'")
        
        qt = get_normalized_tokens(query)
        print(f"  Query Tokens: {qt}")
        
        title_part = query
        if ' - ' in query: title_part = query.split(' - ', 1)[1].strip()
        tt = get_normalized_tokens(title_part)
        print(f"  Title Tokens: {tt}")
        
        result = find_song_in_library(query, index)
        
        if result == expected:
            print(f"✅ PASSED: Found {result}")
            passed += 1
        else:
            print(f"❌ FAILED: Found {result}, expected {expected}")
            
    print(f"\n📊 Result: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)

if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
