import tkinter as tk
from gui.app import PlaylistApp

def main():
    root = tk.Tk()
    app = PlaylistApp(root)
    root.mainloop()

if __name__ == "__main__":
    # To run the new Streamlit UI:
    # streamlit run streamlit_app.py
    main()
