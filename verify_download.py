import os
import sys
from core.downloader import download_song

def test_download():
    # Mocking library path
    library_path = "./Test_Library"
    if not os.path.exists(library_path):
        os.makedirs(library_path)
    
    song_name = "派偉俊, Tyson Yoshi - 忘記你"
    audio_format = "mp3"
    
    def log_func(msg):
        print(f"[LOG] {msg}")

    print(f"Testing download for: {song_name}")
    result = download_song(song_name, library_path, audio_format, log_func, [])
    
    if result and os.path.exists(result):
        print(f"SUCCESS: Downloaded to {result}")
        # Clean up
        try:
            os.remove(result)
            os.rmdir(library_path)
            print("Cleanup successful.")
        except Exception:
            pass
    else:
        print("FAILURE: Download failed.")

if __name__ == "__main__":
    test_download()
