import os
import sys

# Setup environment
sys.path.insert(0, '.')
from core.library import get_normalized_tokens, find_song_in_library, build_library_index

def run_test():
    print("🧪 Running Verification for DIOR Matching Case...")
    
    # Mock library files
    library_files = [
        "data/Music/DIOR大穎 - DIOR大穎 - 大人的快樂 - (Official MV） (2025).mp3",
        "data/Music/郭靜全新單曲〈好像〉_.mp3",
        "data/Music/夢想塗鴉冊.mp3"
    ]
    
    # Build a mock index
    index = build_library_index(library_files)
    
    test_cases = [
        {
            "query": "DIOR大穎 - 大人的快樂",
            "expected": "data/Music/DIOR大穎 - DIOR大穎 - 大人的快樂 - (Official MV） (2025).mp3"
        },
        {
            "query": "郭靜 - 好像",
            "expected": "data/Music/郭靜全新單曲〈好像〉_.mp3"
        }
    ]
    
    passed = 0
    for case in test_cases:
        query = case["query"]
        expected = case["expected"]
        print(f"\nSearching for: '{query}'")
        
        qt = get_normalized_tokens(query)
        print(f"  Query Tokens: {qt}")
        
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
