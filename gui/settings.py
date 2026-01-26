import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from utils.config import save_config, prompt_and_set_base_path
from utils.i18n import I18N, _

class SettingsWindow:
    def __init__(self, parent, config, on_close_callback=None):
        self.top = tk.Toplevel(parent)
        self.top.title("設定 (Settings)")
        self.top.geometry("500x650")
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
        # Container
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

        # 3. Performance Section (Threads)
        lf_perf = tk.LabelFrame(container, text="效能 (Performance)", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=10)
        lf_perf.pack(fill="x", pady=(0, 15))
        
        tk.Label(lf_perf, text="下載線程數 (Threads):", font=("Microsoft JhengHei", 10)).pack(anchor="w", padx=5)
        
        thread_frame = tk.Frame(lf_perf)
        thread_frame.pack(fill="x", pady=5)
        
        self.thread_var = tk.IntVar(value=self.config.get('max_threads', 4))
        self.thread_lbl = tk.Label(thread_frame, text=str(self.thread_var.get()), width=3, font=("Consolas", 10, "bold"))
        self.thread_lbl.pack(side="right", padx=5)
        
        scale = tk.Scale(thread_frame, from_=1, to=16, orient="horizontal", variable=self.thread_var, showvalue=False, command=self.update_thread_lbl)
        scale.pack(side="left", fill="x", expand=True, padx=5)

        # 4. Features Section (Lyrics)
        lf_feat = tk.LabelFrame(container, text="功能 (Features)", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=10)
        lf_feat.pack(fill="x", pady=(0, 15))
        
        self.lyrics_var = tk.BooleanVar(value=self.config.get('enable_retroactive_lyrics', True))
        tk.Checkbutton(lf_feat, text="自動補抓歌詞 (Auto Lyrics)", variable=self.lyrics_var, font=("Microsoft JhengHei", 10)).pack(anchor="w", padx=5)

        # 5. Advanced Section
        lf_adv = tk.LabelFrame(container, text="進階 (Advanced)", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=10)
        lf_adv.pack(fill="x", pady=(0, 15))
        
        self.retry_var = tk.BooleanVar(value=self.config.get('retry_failed_lyrics', False))
        tk.Checkbutton(lf_adv, text="重試失敗歌曲 (Retry Failed Scans)", variable=self.retry_var, font=("Microsoft JhengHei", 10)).pack(anchor="w", padx=5)

        # Buttons
        btn_frame = tk.Frame(container)
        btn_frame.pack(side="bottom", fill="x", pady=10)
        
        tk.Button(btn_frame, text="儲存 (Save)", command=self.save_settings, bg="#d0f0c0", width=10, font=("Microsoft JhengHei", 10)).pack(side="right", padx=5)
        tk.Button(btn_frame, text="取消 (Cancel)", command=self.top.destroy, width=10, font=("Microsoft JhengHei", 10)).pack(side="right", padx=5)

    def update_thread_lbl(self, val):
        self.thread_lbl.config(text=str(val))

    def browse_path(self):
        new_path = filedialog.askdirectory(initialdir=self.path_var.get())
        if new_path:
            self.path_var.set(new_path)

    def save_settings(self):
        # 1. Detect Changes
        new_lang = self.lang_var.get()
        new_path = self.path_var.get()
        new_threads = self.thread_var.get()
        new_lyrics = self.lyrics_var.get()
        new_retry = self.retry_var.get()
        
        lang_changed = new_lang != self.config.get('language')
        path_changed = new_path != self.config.get('base_path')
        
        # 2. Update Config
        self.config['language'] = new_lang
        self.config['base_path'] = new_path
        self.config['max_threads'] = new_threads
        self.config['enable_retroactive_lyrics'] = new_lyrics
        self.config['retry_failed_lyrics'] = new_retry
        
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
