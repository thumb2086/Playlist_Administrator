import tkinter as tk
from gui.app import PlaylistApp, COLORS

def main():
    root = tk.Tk()
    # Set dark background immediately to prevent white flash at startup
    root.configure(bg=COLORS['bg'])
    # Hide window until fully initialized to avoid showing white/default background
    root.withdraw()
    app = PlaylistApp(root)

    # Setup window close handler to cleanup resources
    def on_closing():
        from utils.logger import disable_file_logging
        disable_file_logging()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)

    # Show window after all widgets are created and styled
    root.deiconify()
    root.mainloop()

if __name__ == "__main__":
    main()
