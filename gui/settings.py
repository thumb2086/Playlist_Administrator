import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from utils.config import save_config, prompt_and_set_base_path
from utils.i18n import I18N, _

class SettingsWindow:
    def __init__(self, parent, config, on_close_callback=None):
        self.top = tk.Toplevel(parent)
        self.top.title("設定 (Settings)")
        self.top.geometry("500x900")
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
        # Container (simplified without scrolling for now)
        container = tk.Frame(self.top, padx=20, pady=20)
        container.pack(fill="both", expand=True)
        
        # 1. General Section (Language)
        lf_general = tk.LabelFrame(container, text="一般 (General)", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=10)
        lf_general.pack(fill="x", pady=(0, 15))
        
        tk.Label(lf_general, text="語言 (Language):", font=("Microsoft JhengHei", 10)).grid(row=0, column=0, sticky="w", padx=5)
        self.lang_var = tk.StringVar(value=self.config.get('language', 'zh-TW'))
        lang_cb = ttk.Combobox(lf_general, textvariable=self.lang_var, values=['zh-TW', 'en'], state="readonly", width=15)
        lang_cb.grid(row=0, column=1, sticky="w", padx=5)
        
        # 2. Storage Section
        lf_storage = tk.LabelFrame(container, text="儲存 (Storage)", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=10)
        lf_storage.pack(fill="x", pady=(0, 15))
        
        tk.Label(lf_storage, text="資料夾 (Base Folder):", font=("Microsoft JhengHei", 10)).pack(anchor="w", padx=5)
        
        path_frame = tk.Frame(lf_storage)
        path_frame.pack(fill="x", pady=5)
        
        self.path_var = tk.StringVar(value=self.config.get('base_path', ''))
        path_entry = tk.Entry(path_frame, textvariable=self.path_var, state="readonly", font=("Consolas", 9))
        path_entry.pack(side="left", fill="x", expand=True, padx=5)
        
        btn_browse = tk.Button(path_frame, text="...", command=self.browse_path, width=3)
        btn_browse.pack(side="left")

        # 3. Conversion Section
        lf_conv = tk.LabelFrame(container, text="轉檔 (Conversion)", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=10)
        lf_conv.pack(fill="x", pady=(0, 15))
        
        tk.Label(lf_conv, text="ffmpeg 路徑:", font=("Microsoft JhengHei", 10)).pack(anchor="w", padx=5)
        self.ffmpeg_var = tk.StringVar(value=self.config.get('ffmpeg_path', 'bin/ffmpeg.exe'))
        tk.Entry(lf_conv, textvariable=self.ffmpeg_var, font=("Consolas", 9)).pack(fill="x", padx=5, pady=5)

        # 4. Spotube Section
        lf_spotube = tk.LabelFrame(container, text="Spotube", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=10)
        lf_spotube.pack(fill="x", pady=(0, 15))
        
        tk.Label(lf_spotube, text="Spotube 資料夾:", font=("Microsoft JhengHei", 10)).pack(anchor="w", padx=5)
        self.spotube_folder_var = tk.StringVar(value=self.config.get('spotube_folder_name', 'spotube'))
        tk.Entry(lf_spotube, textvariable=self.spotube_folder_var, font=("Consolas", 9)).pack(fill="x", padx=5, pady=5)

        tk.Label(lf_spotube, text="MP3 子資料夾:", font=("Microsoft JhengHei", 10)).pack(anchor="w", padx=5)
        self.spotube_mp3_var = tk.StringVar(value=self.config.get('spotube_mp3_subfolder', 'mp3'))
        tk.Entry(lf_spotube, textvariable=self.spotube_mp3_var, font=("Consolas", 9)).pack(fill="x", padx=5, pady=5)

        tk.Label(lf_spotube, text="Conversion Threads:", font=("Microsoft JhengHei", 10)).pack(anchor="w", padx=5)
        self.spotube_workers_var = tk.StringVar(value=str(self.config.get('spotube_convert_workers', 4)))
        tk.Entry(lf_spotube, textvariable=self.spotube_workers_var, font=("Consolas", 9)).pack(fill="x", padx=5, pady=5)

        self.prefer_mp3_var = tk.BooleanVar(value=self.config.get('prefer_mp3_playlists', True))
        tk.Checkbutton(lf_spotube, text="播放清單優先 MP3", variable=self.prefer_mp3_var, font=("Microsoft JhengHei", 10)).pack(anchor="w", padx=5)

        # 5. Metadata Section
        lf_meta = tk.LabelFrame(container, text="Metadata", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=10)
        lf_meta.pack(fill="x", pady=(0, 15))
        
        self.metadata_enrichment_var = tk.BooleanVar(value=self.config.get('enable_metadata_enrichment', False))
        tk.Checkbutton(lf_meta, text="自動補充 Metadata (Auto Metadata)", variable=self.metadata_enrichment_var, font=("Microsoft JhengHei", 10)).pack(anchor="w", padx=5)

        # Buttons (outside scrollable area)
        btn_frame = tk.Frame(self.top)
        btn_frame.pack(side="bottom", fill="x", pady=10)
        
        tk.Button(btn_frame, text="儲存 (Save)", command=self.save_settings, bg="#d0f0c0", width=10, font=("Microsoft JhengHei", 10)).pack(side="right", padx=5)
        tk.Button(btn_frame, text="取消 (Cancel)", command=self.top.destroy, width=10, font=("Microsoft JhengHei", 10)).pack(side="right", padx=5)

    def browse_path(self):
        new_path = filedialog.askdirectory(initialdir=self.path_var.get())
        if new_path:
            self.path_var.set(new_path)

    def save_settings(self):
        # 1. Detect Changes
        new_lang = self.lang_var.get()
        new_path = self.path_var.get()
        new_ffmpeg = self.ffmpeg_var.get()
        new_spotube_folder = self.spotube_folder_var.get()
        new_spotube_mp3 = self.spotube_mp3_var.get()
        new_spotube_workers = self.spotube_workers_var.get()
        new_prefer_mp3 = self.prefer_mp3_var.get()
        new_metadata_enrichment = self.metadata_enrichment_var.get()
            
        lang_changed = new_lang != self.config.get('language')
        path_changed = new_path != self.config.get('base_path')
        
        # 2. Update Config
        self.config['language'] = new_lang
        self.config['base_path'] = new_path
        self.config['ffmpeg_path'] = new_ffmpeg
        self.config['spotube_folder_name'] = new_spotube_folder
        self.config['spotube_mp3_subfolder'] = new_spotube_mp3
        try:
            self.config['spotube_convert_workers'] = max(1, int(new_spotube_workers))
        except Exception:
            self.config['spotube_convert_workers'] = 4
        self.config['prefer_mp3_playlists'] = new_prefer_mp3
        self.config['enable_metadata_enrichment'] = new_metadata_enrichment
        
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
