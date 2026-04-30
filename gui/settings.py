import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from utils.config import save_config, prompt_and_set_base_path
from utils.i18n import I18N, _
from utils.version import __version__, GITHUB_OWNER, GITHUB_REPO

class SettingsWindow:
    def __init__(self, parent, config, on_close_callback=None):
        self.top = tk.Toplevel(parent)
        self.top.title("設定 (Settings)")
        self.top.geometry("900x650")
        self.top.resizable(False, False)

        # Modal window behavior
        self.top.transient(parent)
        self.top.grab_set()

        self.config = config
        self.on_close = on_close_callback
        self.parent = parent

        # Temporary config storage for changes
        self.temp_config = config.copy()

        self.create_widgets()

        # Center the window
        self.center_window()

    def center_window(self):
        self.top.update_idletasks()
        width = self.top.winfo_width()
        height = self.top.winfo_height()
        x = (self.top.winfo_screenwidth() // 2) - (width // 2)
        y = (self.top.winfo_screenheight() // 2) - (height // 2)
        self.top.geometry(f'{width}x{height}+{x}+{y}')

    def create_widgets(self):
        # Main container with padding
        container = tk.Frame(self.top, padx=20, pady=15)
        container.pack(fill="both", expand=True)
        
        # Two-column layout
        left_column = tk.Frame(container)
        left_column.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        right_column = tk.Frame(container)
        right_column.pack(side="right", fill="both", expand=True, padx=(10, 0))
        
        # ===== LEFT COLUMN =====
        
        # 1. General Section (Language)
        lf_general = tk.LabelFrame(left_column, text="一般 (General)", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=8)
        lf_general.pack(fill="x", pady=(0, 10))
        
        tk.Label(lf_general, text="語言 (Language):", font=("Microsoft JhengHei", 10)).pack(anchor="w")
        self.lang_var = tk.StringVar(value=self.config.get('language', 'zh-TW'))
        ttk.Combobox(lf_general, textvariable=self.lang_var, values=['zh-TW', 'en'], state="readonly", width=15).pack(fill="x", pady=2)
        
        # 2. Storage Section
        lf_storage = tk.LabelFrame(left_column, text="儲存 (Storage)", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=8)
        lf_storage.pack(fill="x", pady=(0, 10))
        
        tk.Label(lf_storage, text="資料夾 (Base Folder):", font=("Microsoft JhengHei", 10)).pack(anchor="w")
        
        path_frame = tk.Frame(lf_storage)
        path_frame.pack(fill="x", pady=2)
        
        self.path_var = tk.StringVar(value=self.config.get('base_path', ''))
        tk.Entry(path_frame, textvariable=self.path_var, state="readonly", font=("Consolas", 9)).pack(side="left", fill="x", expand=True, padx=(0, 5))
        tk.Button(path_frame, text="...", command=self.browse_path, width=3).pack(side="right")

        # 3. Conversion Section
        lf_conv = tk.LabelFrame(left_column, text="轉檔 (Conversion)", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=8)
        lf_conv.pack(fill="x", pady=(0, 10))
        
        tk.Label(lf_conv, text="ffmpeg 路徑:", font=("Microsoft JhengHei", 10)).pack(anchor="w")
        self.ffmpeg_var = tk.StringVar(value=self.config.get('ffmpeg_path', 'bin/ffmpeg.exe'))
        tk.Entry(lf_conv, textvariable=self.ffmpeg_var, font=("Consolas", 9)).pack(fill="x", pady=2)

        self.convert_matched_only_var = tk.BooleanVar(value=bool(self.config.get('spotube_convert_matched_only', False)))
        tk.Checkbutton(
            lf_conv,
            text="只轉換有匹配歌單的歌曲",
            variable=self.convert_matched_only_var,
            font=("Microsoft JhengHei", 10)
        ).pack(anchor="w", pady=(8, 0))

        # ===== RIGHT COLUMN =====
        
        # 4. Folder Structure Section
        lf_structure = tk.LabelFrame(right_column, text="資料夾結構說明", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=8)
        lf_structure.pack(fill="x", pady=(0, 10))
        
        structure_text = """📁 Music/ (音樂庫根目錄)
  📁 playlists/ (播放清單檔案，MP3)
    📝 _Unsorted.m3u8 (未分類歌曲播放清單)"""
        
        tk.Label(lf_structure, text=structure_text, font=("Consolas", 9), fg="#333333", justify="left").pack(anchor="w", pady=5)

        # 5. About Section (at bottom of right column)
        lf_about = tk.LabelFrame(right_column, text="關於 (About)", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=8)
        lf_about.pack(fill="x", pady=(0, 10))
        
        # Version
        tk.Label(lf_about, text=f"版本: v{__version__}", font=("Microsoft JhengHei", 10)).pack(anchor="w")
        
        # Repository link
        repo_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
        repo_label = tk.Label(lf_about, text=f"儲存庫: {repo_url}", font=("Consolas", 9), fg="#0066cc", cursor="hand2")
        repo_label.pack(anchor="w")
        repo_label.bind("<Button-1>", lambda e: self._open_url(repo_url))
        
        # Author link
        author_url = f"https://github.com/{GITHUB_OWNER}"
        author_label = tk.Label(lf_about, text=f"作者: {GITHUB_OWNER}", font=("Microsoft JhengHei", 10), fg="#0066cc", cursor="hand2")
        author_label.pack(anchor="w")
        author_label.bind("<Button-1>", lambda e: self._open_url(author_url))

        # Buttons (outside scrollable area)
        btn_frame = tk.Frame(self.top)
        btn_frame.pack(side="bottom", fill="x", pady=10)
        
        tk.Button(btn_frame, text="儲存 (Save)", command=self.save_settings, bg="#d0f0c0", width=10, font=("Microsoft JhengHei", 10)).pack(side="right", padx=5)
        tk.Button(btn_frame, text="取消 (Cancel)", command=self.top.destroy, width=10, font=("Microsoft JhengHei", 10)).pack(side="right", padx=5)

    def browse_path(self):
        new_path = filedialog.askdirectory(initialdir=self.path_var.get())
        if new_path:
            self.path_var.set(new_path)

    def _open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    def save_settings(self):
        # 1. Detect Changes
        new_lang = self.lang_var.get()
        new_path = self.path_var.get()
        new_ffmpeg = self.ffmpeg_var.get()

        lang_changed = new_lang != self.config.get('language')
        path_changed = new_path != self.config.get('base_path')

        # 2. Update Config
        self.config['language'] = new_lang
        self.config['base_path'] = new_path
        self.config['ffmpeg_path'] = new_ffmpeg
        self.config['spotube_convert_matched_only'] = bool(self.convert_matched_only_var.get())
        
        # Special handling for path change
        if path_changed:
            from utils.config import derive_paths, ensure_dirs
            derive_paths(self.config)
            ensure_dirs(self.config)
        
        # Apply Language immediately
        if lang_changed:
            I18N.set_language(new_lang)

        save_config(self.config)
        
        # Callback to main app to refresh UI
        if self.on_close:
            self.on_close(lang_changed=lang_changed, path_changed=path_changed)
            
        self.top.destroy()
