import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from utils.config import save_config, prompt_and_set_base_path
from utils.i18n import I18N, _
from utils.version import __version__, GITHUB_OWNER, GITHUB_REPO

# Import dark theme colors from app module
from gui.app import COLORS, get_font, FONT_MONO

class SettingsWindow:
    def __init__(self, parent, config, on_close_callback=None):
        self.top = tk.Toplevel(parent)
        self.top.title("設定 (Settings)")
        self.top.geometry("900x780")  # Increased height to show all content and buttons
        self.top.resizable(False, False)
        self.top.configure(bg=COLORS['bg'])

        # Configure ttk styles for dark theme
        self._configure_ttk_styles()

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

    def _configure_ttk_styles(self):
        """Configure ttk widget styles for dark theme"""
        style = ttk.Style()

        # Use 'clam' theme for better customization support on Windows
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass  # Fallback to default if clam not available

        # Configure Combobox (language selector) - Fix white background
        style.configure("TCombobox",
                       fieldbackground=COLORS['elevated'],
                       background=COLORS['elevated'],
                       foreground=COLORS['text'],
                       arrowcolor=COLORS['text'],
                       borderwidth=0,
                       relief='flat')
        style.map("TCombobox",
                 fieldbackground=[('readonly', COLORS['elevated']),
                                 ('disabled', COLORS['surface'])],
                 selectbackground=[('readonly', COLORS['accent'])],
                 selectforeground=[('readonly', COLORS['bg'])],
                 foreground=[('readonly', COLORS['text'])])

        # Fix combobox dropdown list colors
        style.configure('ComboboxPopdownFrame',
                       background=COLORS['elevated'],
                       foreground=COLORS['text'])
        style.map('ComboboxPopdownFrame',
                 background=[('active', COLORS['surface'])])

    def center_window(self):
        self.top.update_idletasks()
        width = self.top.winfo_width()
        height = self.top.winfo_height()
        x = (self.top.winfo_screenwidth() // 2) - (width // 2)
        y = (self.top.winfo_screenheight() // 2) - (height // 2)
        self.top.geometry(f'{width}x{height}+{x}+{y}')

    def create_widgets(self):
        # Main container with padding - Dark theme
        container = tk.Frame(self.top, bg=COLORS['bg'], padx=24, pady=20)
        container.pack(fill="both", expand=True)

        # Two-column layout using grid for better control
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=1)

        left_column = tk.Frame(container, bg=COLORS['bg'])
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 12))

        right_column = tk.Frame(container, bg=COLORS['bg'])
        right_column.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        
        # ===== LEFT COLUMN =====

        # 1. General Section (Language) - Dark theme
        lf_general = tk.LabelFrame(left_column, text="一般 (General)",
                                   font=get_font(11, bold=True),
                                   fg=COLORS['text'], bg=COLORS['surface'],
                                   highlightbackground=COLORS['border'],
                                   highlightthickness=1, bd=0,
                                   padx=12, pady=10)
        lf_general.pack(fill="x", pady=(0, 12))

        tk.Label(lf_general, text="語言 (Language):",
                 font=get_font(10), fg=COLORS['text_secondary'], bg=COLORS['surface']).pack(anchor="w")
        self.lang_var = tk.StringVar(value=self.config.get('language', 'zh-TW'))
        lang_combo = ttk.Combobox(lf_general, textvariable=self.lang_var,
                                  values=['zh-TW', 'en'], state="readonly", width=15)
        lang_combo.pack(fill="x", pady=4)

        # Theme selection
        tk.Label(lf_general, text="主題 (Theme):",
                 font=get_font(10), fg=COLORS['text_secondary'], bg=COLORS['surface']).pack(anchor="w", pady=(12, 0))
        self.theme_var = tk.StringVar(value=self.config.get('theme', 'dark'))
        theme_combo = ttk.Combobox(lf_general, textvariable=self.theme_var,
                                   values=['dark', 'light'], state="readonly", width=15)
        theme_combo.pack(fill="x", pady=4)

        # Auto update check option
        self.auto_update_check_var = tk.BooleanVar(value=bool(self.config.get('auto_update_check', True)))
        tk.Checkbutton(
            lf_general,
            text=_('auto_update_check'),
            variable=self.auto_update_check_var,
            font=get_font(10),
            fg=COLORS['text'], bg=COLORS['surface'],
            selectcolor=COLORS['elevated'],
            activebackground=COLORS['surface'],
            activeforeground=COLORS['accent']
        ).pack(anchor="w", pady=(8, 0))
        tk.Label(lf_general, text=_('auto_update_check_desc'),
                 font=get_font(9), fg=COLORS['text_muted'], bg=COLORS['surface']).pack(anchor="w")

        # 2. Storage Section - Dark theme
        lf_storage = tk.LabelFrame(left_column, text="儲存 (Storage)",
                                   font=get_font(11, bold=True),
                                   fg=COLORS['text'], bg=COLORS['surface'],
                                   highlightbackground=COLORS['border'],
                                   highlightthickness=1, bd=0,
                                   padx=12, pady=10)
        lf_storage.pack(fill="x", pady=(0, 12))

        tk.Label(lf_storage, text="資料夾 (Base Folder):",
                 font=get_font(10), fg=COLORS['text_secondary'], bg=COLORS['surface']).pack(anchor="w")

        path_frame = tk.Frame(lf_storage, bg=COLORS['surface'])
        path_frame.pack(fill="x", pady=4)

        self.path_var = tk.StringVar(value=self.config.get('base_path', ''))
        path_entry = tk.Entry(path_frame, textvariable=self.path_var, state="readonly",
                              font=(FONT_MONO, 10),
                              bg=COLORS['elevated'], fg=COLORS['text'],
                              disabledbackground=COLORS['elevated'],
                              disabledforeground=COLORS['text'],
                              readonlybackground=COLORS['elevated'],
                              relief="flat", highlightthickness=1,
                              highlightbackground=COLORS['border'])
        path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = tk.Button(path_frame, text="...", command=self.browse_path, width=3,
                               font=get_font(10),
                               bg=COLORS['elevated'], fg=COLORS['text'],
                               activebackground=COLORS['surface'],
                               relief="flat", cursor="hand2")
        browse_btn.pack(side="right")

        # 3. Conversion Section - Dark theme
        lf_conv = tk.LabelFrame(left_column, text="轉檔 (Conversion)",
                                font=get_font(11, bold=True),
                                fg=COLORS['text'], bg=COLORS['surface'],
                                highlightbackground=COLORS['border'],
                                highlightthickness=1, bd=0,
                                padx=12, pady=10)
        lf_conv.pack(fill="x", pady=(0, 12))

        tk.Label(lf_conv, text="ffmpeg 路徑:",
                 font=get_font(10), fg=COLORS['text_secondary'], bg=COLORS['surface']).pack(anchor="w")
        self.ffmpeg_var = tk.StringVar(value=self.config.get('ffmpeg_path', 'bin/ffmpeg.exe'))
        ffmpeg_entry = tk.Entry(lf_conv, textvariable=self.ffmpeg_var,
                                font=(FONT_MONO, 10),
                                bg=COLORS['elevated'], fg=COLORS['text'],
                                insertbackground=COLORS['text'],
                                selectbackground=COLORS['accent'],
                                selectforeground=COLORS['bg'],
                                relief="flat", highlightthickness=1,
                                highlightbackground=COLORS['border'])
        ffmpeg_entry.pack(fill="x", pady=4)

        self.convert_matched_only_var = tk.BooleanVar(value=bool(self.config.get('spotube_convert_matched_only', False)))
        tk.Checkbutton(
            lf_conv,
            text="只轉換有匹配歌單的歌曲",
            variable=self.convert_matched_only_var,
            font=get_font(10),
            fg=COLORS['text'], bg=COLORS['surface'],
            selectcolor=COLORS['elevated'],
            activebackground=COLORS['surface'],
            activeforeground=COLORS['accent']
        ).pack(anchor="w", pady=(8, 0))

        self.strict_matching_var = tk.BooleanVar(value=bool(self.config.get('spotube_strict_matching', True)))
        tk.Checkbutton(
            lf_conv,
            text="嚴格檔名匹配 (只轉換沒有同檔名 MP3 的 M4A)",
            variable=self.strict_matching_var,
            font=get_font(10),
            fg=COLORS['text'], bg=COLORS['surface'],
            selectcolor=COLORS['elevated'],
            activebackground=COLORS['surface'],
            activeforeground=COLORS['accent']
        ).pack(anchor="w", pady=(4, 0))
        tk.Label(lf_conv, text="(關閉允許智能匹配，可能跳過部分轉換)",
                 font=get_font(9), fg=COLORS['text_muted'], bg=COLORS['surface']).pack(anchor="w")

        # 4. Lyrics Section - Dark theme
        lf_lyrics = tk.LabelFrame(left_column, text="Lyrics",
                                  font=get_font(11, bold=True),
                                  fg=COLORS['text'], bg=COLORS['surface'],
                                  highlightbackground=COLORS['border'],
                                  highlightthickness=1, bd=0,
                                  padx=12, pady=10)
        lf_lyrics.pack(fill="x", pady=(0, 12))

        self.enable_retro_lyrics_var = tk.BooleanVar(value=bool(self.config.get('enable_retroactive_lyrics', False)))
        tk.Checkbutton(
            lf_lyrics,
            text="Enable lyric download",
            variable=self.enable_retro_lyrics_var,
            font=get_font(10),
            fg=COLORS['text'], bg=COLORS['surface'],
            selectcolor=COLORS['elevated'],
            activebackground=COLORS['surface'],
            activeforeground=COLORS['accent']
        ).pack(anchor="w")
        tk.Label(
            lf_lyrics,
            text="Download synced lyrics for songs that do not already have .lrc files.",
            font=get_font(9),
            fg=COLORS['text_muted'],
            bg=COLORS['surface']
        ).pack(anchor="w")

        tk.Label(lf_lyrics, text="Lyrics folder name:",
                 font=get_font(10), fg=COLORS['text_secondary'], bg=COLORS['surface']).pack(anchor="w", pady=(8, 0))
        self.lyrics_folder_var = tk.StringVar(value=self.config.get('lyrics_folder_name', 'Lyrics'))
        self.lyrics_folder_entry = tk.Entry(lf_lyrics, textvariable=self.lyrics_folder_var,
                                            font=get_font(10),
                                            bg=COLORS['elevated'], fg=COLORS['text'],
                                            insertbackground=COLORS['text'],
                                            selectbackground=COLORS['accent'],
                                            selectforeground=COLORS['bg'],
                                            relief="flat", highlightthickness=1,
                                            highlightbackground=COLORS['border'])
        self.lyrics_folder_entry.pack(fill="x", pady=4)
        tk.Label(
            lf_lyrics,
            text="Lyrics will be stored inside the music library under this folder.",
            font=get_font(9),
            fg=COLORS['text_muted'],
            bg=COLORS['surface']
        ).pack(anchor="w")

        # ===== RIGHT COLUMN =====
        # 4. Sync Section - Moved to right column for balance
        lf_sync_right = tk.LabelFrame(right_column, text="同步 (Sync)",
                                      font=get_font(11, bold=True),
                                      fg=COLORS['text'], bg=COLORS['surface'],
                                      highlightbackground=COLORS['border'],
                                      highlightthickness=1, bd=0,
                                      padx=12, pady=10)
        lf_sync_right.pack(fill="x", pady=(0, 12))

        self.auto_sync_on_add_var = tk.BooleanVar(value=bool(self.config.get('auto_sync_on_add', False)))
        tk.Checkbutton(
            lf_sync_right,
            text="新增歌單時自動掃描音樂庫同步",
            variable=self.auto_sync_on_add_var,
            font=get_font(10),
            fg=COLORS['text'], bg=COLORS['surface'],
            selectcolor=COLORS['elevated'],
            activebackground=COLORS['surface'],
            activeforeground=COLORS['accent']
        ).pack(anchor="w")
        tk.Label(lf_sync_right, text="(關閉可加快新增歌單速度，同步將在「全部更新」時執行)",
                 font=get_font(9), fg=COLORS['text_muted'], bg=COLORS['surface']).pack(anchor="w")

        # 5. Folder Structure Section - Dark theme
        lf_structure = tk.LabelFrame(right_column, text="資料夾結構說明",
                                     font=get_font(11, bold=True),
                                     fg=COLORS['text'], bg=COLORS['surface'],
                                     highlightbackground=COLORS['border'],
                                     highlightthickness=1, bd=0,
                                     padx=12, pady=10)
        lf_structure.pack(fill="x", pady=(0, 12))

        structure_text = """📁 Music/ (音樂庫根目錄)
  📁 playlists/ (播放清單檔案，MP3)
    📝 _Unsorted.m3u8 (未分類歌曲播放清單)"""

        tk.Label(lf_structure, text=structure_text,
                 font=(FONT_MONO, 10), fg=COLORS['text_secondary'],
                 bg=COLORS['surface'], justify="left").pack(anchor="w", pady=4)

        # 5. About Section (at bottom of right column) - Dark theme
        lf_about = tk.LabelFrame(right_column, text="關於 (About)",
                                 font=get_font(11, bold=True),
                                 fg=COLORS['text'], bg=COLORS['surface'],
                                 highlightbackground=COLORS['border'],
                                 highlightthickness=1, bd=0,
                                 padx=12, pady=10)
        lf_about.pack(fill="x", pady=(0, 12))

        # Version
        tk.Label(lf_about, text=f"版本: v{__version__}",
                 font=get_font(11), fg=COLORS['text'], bg=COLORS['surface']).pack(anchor="w")

        # Repository link
        repo_url = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
        repo_label = tk.Label(lf_about, text=f"儲存庫: {repo_url}",
                              font=(FONT_MONO, 10), fg=COLORS['accent'],
                              bg=COLORS['surface'], cursor="hand2")
        repo_label.pack(anchor="w")
        repo_label.bind("<Button-1>", lambda e: self._open_url(repo_url))

        # Author link
        author_url = f"https://github.com/{GITHUB_OWNER}"
        author_label = tk.Label(lf_about, text=f"作者: {GITHUB_OWNER}",
                                font=get_font(10), fg=COLORS['accent'],
                                bg=COLORS['surface'], cursor="hand2")
        author_label.pack(anchor="w")
        author_label.bind("<Button-1>", lambda e: self._open_url(author_url))

        # 6. Debug Section - Moved to right column (Dark theme)
        lf_debug = tk.LabelFrame(right_column, text="除錯 (Debug)",
                                 font=get_font(11, bold=True),
                                 fg=COLORS['text'], bg=COLORS['surface'],
                                 highlightbackground=COLORS['border'],
                                 highlightthickness=1, bd=0,
                                 padx=12, pady=10)
        lf_debug.pack(fill="x", pady=(0, 12))

        self.debug_mode_var = tk.BooleanVar(value=bool(self.config.get('debug_mode', False)))
        tk.Checkbutton(
            lf_debug,
            text="啟用除錯輸出 (顯示詳細除錯資訊)",
            variable=self.debug_mode_var,
            font=get_font(10),
            fg=COLORS['text'], bg=COLORS['surface'],
            selectcolor=COLORS['elevated'],
            activebackground=COLORS['surface'],
            activeforeground=COLORS['accent']
        ).pack(anchor="w")

        # Buttons row - spans both columns at bottom
        btn_frame = tk.Frame(container, bg=COLORS['bg'])
        btn_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(16, 0))

        # Center the buttons
        btn_inner = tk.Frame(btn_frame, bg=COLORS['bg'])
        btn_inner.pack(side="right")

        # Cancel button - Secondary
        cancel_btn = tk.Button(btn_inner, text="✕ 取消 (Cancel)",
                               command=self.top.destroy,
                               bg=COLORS['elevated'], fg=COLORS['text'],
                               activebackground=COLORS['surface'],
                               activeforeground=COLORS['text'],
                               width=12, font=get_font(11),
                               relief="flat", cursor="hand2", padx=16, pady=8)
        cancel_btn.pack(side="right", padx=(8, 0))

        # Save button - Accent color
        save_btn = tk.Button(btn_inner, text="💾 儲存 (Save)",
                             command=self.save_settings,
                             bg=COLORS['accent'], fg=COLORS['bg'],
                             activebackground=COLORS['accent_hover'],
                             activeforeground=COLORS['bg'],
                             width=12, font=get_font(11, bold=True),
                             relief="flat", cursor="hand2", padx=16, pady=8)
        save_btn.pack(side="right")

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
        new_theme = self.theme_var.get()
        new_lyrics_folder = self.lyrics_folder_var.get().strip() or 'Lyrics'

        lang_changed = new_lang != self.config.get('language')
        path_changed = new_path != self.config.get('base_path')
        lyrics_folder_changed = new_lyrics_folder != self.config.get('lyrics_folder_name', 'Lyrics')
        theme_changed = new_theme != self.config.get('theme', 'dark')

        # 2. Update Config
        self.config['language'] = new_lang
        self.config['base_path'] = new_path
        self.config['ffmpeg_path'] = new_ffmpeg
        self.config['lyrics_folder_name'] = new_lyrics_folder
        self.config['enable_retroactive_lyrics'] = bool(self.enable_retro_lyrics_var.get())
        self.config['spotube_convert_matched_only'] = bool(self.convert_matched_only_var.get())
        self.config['spotube_strict_matching'] = bool(self.strict_matching_var.get())
        self.config['auto_sync_on_add'] = bool(self.auto_sync_on_add_var.get())
        self.config['debug_mode'] = bool(self.debug_mode_var.get())
        self.config['auto_update_check'] = bool(self.auto_update_check_var.get())
        self.config['theme'] = new_theme

        # Apply debug mode immediately
        from utils.config import set_debug_mode
        set_debug_mode(self.config['debug_mode'])
        
        # Special handling for path change
        if path_changed or lyrics_folder_changed:
            from utils.config import derive_paths, ensure_dirs
            derive_paths(self.config)
            ensure_dirs(self.config)
        
        # Apply Language immediately
        if lang_changed:
            I18N.set_language(new_lang)

        save_config(self.config)

        # Callback to main app to refresh UI
        if self.on_close:
            self.on_close(lang_changed=lang_changed, path_changed=path_changed, theme_changed=theme_changed)

        self.top.destroy()
