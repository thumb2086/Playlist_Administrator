import tkinter as tk
from gui.app import PlaylistApp
import sys
import os

def main():
    # Set current directory to file location to ensure assets are found
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    root = tk.Tk()
    app = PlaylistApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
