import os
import shutil
import sys
import subprocess

def check_env():
    print(f"Python Version: {sys.version}")
    print(f"CWD: {os.getcwd()}")
    print("-" * 20)
    
    deno_path = shutil.which('deno')
    node_path = shutil.which('node')
    
    print(f"Deno found: {deno_path}")
    print(f"Node found: {node_path}")
    
    if deno_path:
        try:
            res = subprocess.run(['deno', '--version'], capture_output=True, text=True)
            print(f"Deno version output: {res.stdout.splitlines()[0]}")
        except Exception as e:
            print(f"Error running deno: {e}")

    if node_path:
        try:
            res = subprocess.run(['node', '-v'], capture_output=True, text=True)
            print(f"Node version output: {res.stdout.strip()}")
        except Exception as e:
            print(f"Error running node: {e}")

    print("-" * 20)
    # Test a simple yt-dlp extraction with remote components enabled
    try:
        import yt_dlp
        print(f"yt-dlp version: {yt_dlp.version.__version__}")
        
        ydl_opts = {
            'quiet': False,
            'extractor_args': {
                'youtube': {
                    'player_client': ['tv'],
                    'remote_components': 'ejs:github'
                }
            }
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
             # Just a small test with a known video to see if JS challenge warnings appear
             print("Testing extraction for a short video...")
             ydl.extract_info("https://www.youtube.com/watch?v=X_B9nxhaMUQ", download=False)
             print("Extraction successful!")
    except Exception as e:
        print(f"yt-dlp test failed: {e}")

if __name__ == "__main__":
    check_env()
