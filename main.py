import tkinter as tk
from gui.app import PlaylistApp, COLORS

def main():
    root = tk.Tk()
    # Set dark background immediately to prevent white flash at startup
    root.configure(bg=COLORS['bg'])
    # Hide window until fully initialized to avoid showing white/default background
    root.withdraw()
    app = PlaylistApp(root)
    # Show window after all widgets are created and styled
    root.deiconify()
    root.mainloop()

if __name__ == "__main__":
    main()
