import unittest
import sys
import os

# Add current dir to sys.path so we can import main
sys.path.append(os.getcwd())
import main

class TestFix(unittest.TestCase):
    def test_sanitize_filename(self):
        self.assertEqual(main.sanitize_filename("test"), "test")
        self.assertEqual(main.sanitize_filename("test/foo"), "test_foo")
        self.assertEqual(main.sanitize_filename('test"foo'), "test_foo")
        self.assertEqual(main.sanitize_filename("test:foo"), "test_foo")
        self.assertEqual(main.sanitize_filename("test*foo"), "test_foo")
        self.assertEqual(main.sanitize_filename("test?foo"), "test_foo")
        self.assertEqual(main.sanitize_filename("test<foo"), "test_foo")
        self.assertEqual(main.sanitize_filename("test>foo"), "test_foo")
        self.assertEqual(main.sanitize_filename("test|foo"), "test_foo")

    def test_find_song_in_library(self):
        # Mock file list (simulated cache)
        # Note: logic converts to simplified chinese and lowercases
        files = [
            "C:\\Music\\Jay Chou - Sunny Day.mp3",
            "C:\\Music\\Eason Chan - Ten Years.flac", 
            "C:\\Music\\G.E.M. - Light Years Away.mp3"
        ]
        
        # Exact match (normalized)
        self.assertEqual(main.find_song_in_library("Jay Chou - Sunny Day", files), files[0])
        
        # Fuzzy match parts
        self.assertEqual(main.find_song_in_library("Eason Chan - Ten Years", files), files[1])
        
        # Non-match
        self.assertIsNone(main.find_song_in_library("Unknown - Song", files))

    def test_normalize_with_brackets(self):
        # Case reported by user: Title inside brackets
        # Spotify: Bestards - 今天星期六
        # YouTube: 理想混蛋 Bestards【今天星期六 Oh, My Saturday】Official Music Video
        
        raw_yt_name = "理想混蛋 Bestards【今天星期六 Oh, My Saturday】Official Music Video"
        query_spot = "Bestards - 今天星期六"
        
        # Test 1: Normalize shouldn't delete "今天星期六"
        norm = main.normalize_name(raw_yt_name)
        self.assertIn("今天星期六", norm)
        
        # Test 2: Find logic should find it (mock file list)
        files = ["C:\\Music\\" + raw_yt_name + ".mp3"]
        found = main.find_song_in_library(query_spot, files)
        self.assertIsNotNone(found)
        self.assertEqual(found, files[0])

    def test_different_artist_same_song(self):
        # Case reported: "許維芳 - 我受夠了" vs "艾薇 Ivy - 我受夠了"
        # The tool should NOT match these.
        
        file_list = ["C:\\Music\\許維芳 - 我受夠了.mp3"]
        query_target = "艾薇 Ivy, 吳霏 - 我受夠了"
        
        found = main.find_song_in_library(query_target, file_list)
        self.assertIsNone(found, "Should not match different artists even if title is same")

if __name__ == '__main__':
    unittest.main()
