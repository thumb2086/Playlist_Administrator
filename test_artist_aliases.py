#!/usr/bin/env python3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import core.library as library


def test_builtin_alias_match():
    files = [
        r"C:\Music\mp3\好像 - Claire Kuo.mp3",
        r"C:\Music\mp3\Can You Feel The Love Tonight - Jeremy Ng.mp3",
    ]
    lib_index = library.build_library_index(files)

    result = library.find_song_simple_match("好像 - 郭靜", ".mp3", lib_index)
    assert result and result.endswith("好像 - Claire Kuo.mp3"), result

    wrong = library.find_song_simple_match("Fish Love - JOLIN蔡依林", ".mp3", lib_index)
    assert wrong is None, wrong


def test_custom_alias_file():
    alias_path = os.path.join(os.path.dirname(__file__), "artist_aliases.example.json")

    original_path_fn = library._artist_aliases_file_path
    try:
        library._artist_aliases_file_path = lambda: alias_path
        library._load_artist_aliases_cached.cache_clear()

        aliases = library.get_artist_aliases()
        assert aliases["claire kuo"] == "郭靜"
        assert aliases["sabrina hu"] == "Sabrina 胡恂舞"
        assert aliases["chih siou"] == "持修"
    finally:
        library._artist_aliases_file_path = original_path_fn
        library._load_artist_aliases_cached.cache_clear()


if __name__ == "__main__":
    test_builtin_alias_match()
    test_custom_alias_file()
    print("artist alias tests passed")
