import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from utils.config import save_config, prompt_and_set_base_path
from utils.i18n import I18N, _

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

        # 4. Spotube Section
        lf_spotube = tk.LabelFrame(left_column, text="Spotube", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=8)
        lf_spotube.pack(fill="x", pady=(0, 10))
        
        tk.Label(lf_spotube, text="Spotube 資料夾:", font=("Microsoft JhengHei", 10)).pack(anchor="w")
        self.spotube_folder_var = tk.StringVar(value=self.config.get('spotube_folder_name', 'spotube'))
        tk.Entry(lf_spotube, textvariable=self.spotube_folder_var, font=("Consolas", 9)).pack(fill="x", pady=2)

        tk.Label(lf_spotube, text="M4A 子資料夾 (原始音檔):", font=("Microsoft JhengHei", 10)).pack(anchor="w")
        self.spotube_m4a_var = tk.StringVar(value=self.config.get('spotube_m4a_subfolder', 'm4a'))
        tk.Entry(lf_spotube, textvariable=self.spotube_m4a_var, font=("Consolas", 9)).pack(fill="x", pady=2)

        tk.Label(lf_spotube, text="MP3 子資料夾 (轉換後):", font=("Microsoft JhengHei", 10)).pack(anchor="w")
        self.spotube_mp3_var = tk.StringVar(value=self.config.get('spotube_mp3_subfolder', 'mp3'))
        tk.Entry(lf_spotube, textvariable=self.spotube_mp3_var, font=("Consolas", 9)).pack(fill="x", pady=2)

        tk.Label(lf_spotube, text="Conversion Threads:", font=("Microsoft JhengHei", 10)).pack(anchor="w")
        self.spotube_workers_var = tk.StringVar(value=str(self.config.get('spotube_convert_workers', 4)))
        tk.Entry(lf_spotube, textvariable=self.spotube_workers_var, font=("Consolas", 9), width=10).pack(anchor="w", pady=2)

        self.prefer_mp3_var = tk.BooleanVar(value=self.config.get('prefer_mp3_playlists', True))
        tk.Checkbutton(lf_spotube, text="播放清單優先 MP3", variable=self.prefer_mp3_var, font=("Microsoft JhengHei", 10)).pack(anchor="w", pady=2)

        # ===== RIGHT COLUMN =====
        
        # 5. Folder Structure Section
        lf_structure = tk.LabelFrame(right_column, text="資料夾結構說明", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=8)
        lf_structure.pack(fill="x", pady=(0, 10))
        
        structure_text = """📁 Music/ (音樂庫根目錄)
  📁 playlists/ (播放清單檔案)
    📝 _Unsorted.m3u8 (未分類歌曲播放清單)
  📁 spotube/ (Spotube 下載目錄)
    📁 m4a/ (原始 M4A 檔案)
    📁 mp3/ (轉換後 MP3 檔案)"""
        
        tk.Label(lf_structure, text=structure_text, font=("Consolas", 9), fg="#333333", justify="left").pack(anchor="w", pady=5)
        
        tk.Label(lf_structure, text="💡 提示：M4A 是 Spotube 下載的原始格式，" \
                 "建議獨立存放後再轉換為 MP3 到播放清單使用", 
                 font=("Microsoft JhengHei", 9), fg="#0066cc", wraplength=350).pack(anchor="w", pady=(5, 0))
        
        # 5. Spotify OAuth Section
        lf_spotify_api = tk.LabelFrame(right_column, text="Spotify 使用者授權 (OAuth)", font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=8)
        lf_spotify_api.pack(fill="x", pady=(0, 10))
        
        # Hint label
        hint_text = "🔐 使用 OAuth 使用者授權登入 Spotify\n可取得個人化播放清單如 Daily Mix / Discover Weekly\n\n⚠️ 重要：在 Spotify Dashboard 設定 Redirect URI 為：\nhttp://localhost:8888/callback"
        tk.Label(lf_spotify_api, text=hint_text, font=("Microsoft JhengHei", 9), fg="#666666", wraplength=350).pack(anchor="w", pady=(0, 5))
        
        # Client ID
        tk.Label(lf_spotify_api, text="Client ID:", font=("Microsoft JhengHei", 10)).pack(anchor="w")
        self.spotify_client_id_var = tk.StringVar(value=self.config.get('spotify_client_id', ''))
        tk.Entry(lf_spotify_api, textvariable=self.spotify_client_id_var, font=("Consolas", 9)).pack(fill="x", pady=2)
        
        # Client Secret
        tk.Label(lf_spotify_api, text="Client Secret:", font=("Microsoft JhengHei", 10)).pack(anchor="w")
        self.spotify_client_secret_var = tk.StringVar(value=self.config.get('spotify_client_secret', ''))
        tk.Entry(lf_spotify_api, textvariable=self.spotify_client_secret_var, font=("Consolas", 9), show="*").pack(fill="x", pady=2)
        
        # Fetch Method
        tk.Label(lf_spotify_api, text="取得方式:", font=("Microsoft JhengHei", 10)).pack(anchor="w", pady=(5, 0))
        self.spotify_fetch_method_var = tk.StringVar(value=self.config.get('spotify_fetch_method', 'embed'))
        method_frame = tk.Frame(lf_spotify_api)
        method_frame.pack(fill="x", pady=2)
        tk.Radiobutton(method_frame, text="📄 Embed 頁面抓取（無需登入，較舊資料）", variable=self.spotify_fetch_method_var, value="embed", font=("Microsoft JhengHei", 9)).pack(anchor="w")
        tk.Radiobutton(method_frame, text="🔐 OAuth 使用者授權（登入 Spotify，最新動態清單）", variable=self.spotify_fetch_method_var, value="api", font=("Microsoft JhengHei", 9)).pack(anchor="w")
        tk.Radiobutton(method_frame, text="⚡ 自動選擇（有 Client ID 用 OAuth）", variable=self.spotify_fetch_method_var, value="auto", font=("Microsoft JhengHei", 9)).pack(anchor="w")
        
        # Login button
        self.spotify_login_btn = tk.Button(lf_spotify_api, text="🔐 登入 Spotify", command=self.spotify_oauth_login, bg="#1DB954", fg="white", font=("Microsoft JhengHei", 9, "bold"))
        self.spotify_login_btn.pack(fill="x", pady=(10, 0))
        
        # Login status label
        access_token = self.config.get('spotify_access_token')
        if access_token:
            self.spotify_login_status = tk.Label(lf_spotify_api, text="✅ 已登入", font=("Microsoft JhengHei", 9), fg="#1DB954")
        else:
            self.spotify_login_status = tk.Label(lf_spotify_api, text="尚未登入", font=("Microsoft JhengHei", 9), fg="#999999")
        self.spotify_login_status.pack(anchor="w", pady=(5, 0))

        # Buttons (outside scrollable area)
        btn_frame = tk.Frame(self.top)
        btn_frame.pack(side="bottom", fill="x", pady=10)
        
        tk.Button(btn_frame, text="儲存 (Save)", command=self.save_settings, bg="#d0f0c0", width=10, font=("Microsoft JhengHei", 10)).pack(side="right", padx=5)
        tk.Button(btn_frame, text="取消 (Cancel)", command=self.top.destroy, width=10, font=("Microsoft JhengHei", 10)).pack(side="right", padx=5)

    def browse_path(self):
        new_path = filedialog.askdirectory(initialdir=self.path_var.get())
        if new_path:
            self.path_var.set(new_path)
    
    def spotify_oauth_login(self):
        """Handle Spotify OAuth login"""
        client_id = self.spotify_client_id_var.get().strip()
        client_secret = self.spotify_client_secret_var.get().strip()
        
        if not client_id:
            messagebox.showerror("錯誤", "請先填入 Client ID")
            return
        
        self.spotify_login_status.config(text="正在啟動瀏覽器...", fg="#FFA500")
        self.spotify_login_btn.config(state="disabled")
        self.top.update()
        
        # Run OAuth in a separate thread to avoid blocking UI
        def _oauth_thread():
            try:
                from core.spotify_playlist_fetcher import SpotifyWebAPI
                api = SpotifyWebAPI(client_id, client_secret)
                success = api.authenticate_with_user_auth(timeout=120)
                
                if success:
                    # Save tokens to config
                    self.config['spotify_access_token'] = api._access_token
                    self.config['spotify_refresh_token'] = api._refresh_token
                    from utils.config import save_config
                    save_config(self.config)
                    
                    self.top.after(0, lambda: self.spotify_login_status.config(text="✅ 已登入", fg="#1DB954"))
                    self.top.after(0, lambda: messagebox.showinfo("成功", "Spotify 授權成功！"))
                else:
                    self.top.after(0, lambda: self.spotify_login_status.config(text="❌ 登入失敗", fg="#FF0000"))
                    self.top.after(0, lambda: messagebox.showerror("失敗", "Spotify 授權失敗，請重試"))
            except Exception as e:
                self.top.after(0, lambda: self.spotify_login_status.config(text="❌ 錯誤", fg="#FF0000"))
                self.top.after(0, lambda: messagebox.showerror("錯誤", f"發生錯誤: {str(e)}"))
            finally:
                self.top.after(0, lambda: self.spotify_login_btn.config(state="normal"))
        
        import threading
        threading.Thread(target=_oauth_thread, daemon=True).start()

    def save_settings(self):
        # 1. Detect Changes
        new_lang = self.lang_var.get()
        new_path = self.path_var.get()
        new_ffmpeg = self.ffmpeg_var.get()
        new_spotube_folder = self.spotube_folder_var.get()
        new_spotube_m4a = self.spotube_m4a_var.get()
        new_spotube_mp3 = self.spotube_mp3_var.get()
        new_spotube_workers = self.spotube_workers_var.get()
        new_prefer_mp3 = self.prefer_mp3_var.get()
        new_spotify_client_id = self.spotify_client_id_var.get().strip()
        new_spotify_client_secret = self.spotify_client_secret_var.get().strip()
        new_spotify_fetch_method = self.spotify_fetch_method_var.get()
            
        lang_changed = new_lang != self.config.get('language')
        path_changed = new_path != self.config.get('base_path')
        
        # 2. Update Config
        self.config['language'] = new_lang
        self.config['base_path'] = new_path
        self.config['ffmpeg_path'] = new_ffmpeg
        self.config['spotube_folder_name'] = new_spotube_folder
        self.config['spotube_m4a_subfolder'] = new_spotube_m4a
        self.config['spotube_mp3_subfolder'] = new_spotube_mp3
        try:
            self.config['spotube_convert_workers'] = max(1, int(new_spotube_workers))
        except Exception:
            self.config['spotube_convert_workers'] = 4
        self.config['prefer_mp3_playlists'] = new_prefer_mp3
        self.config['spotify_client_id'] = new_spotify_client_id
        self.config['spotify_client_secret'] = new_spotify_client_secret
        self.config['spotify_fetch_method'] = new_spotify_fetch_method
        
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
