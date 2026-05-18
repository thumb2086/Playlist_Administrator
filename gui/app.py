import os
import glob
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from collections import deque
from utils.config import load_config, save_config, ensure_dirs, prompt_and_set_base_path, derive_paths
from utils.i18n import I18N, _
from utils.version_checker import should_check_for_updates, perform_update_check
from utils.version import get_version
from core.library import UpdateStats, update_library_logic, export_usb_logic, get_detailed_stats
from core.library import is_internal_playlist_name

# ===== Dark Theme Color System (Spotify-inspired) =====
COLORS_DARK = {
    'bg': '#121212',             # Main background
    'surface': '#1e1e1e',       # Card/panel background
    'elevated': '#2a2a2a',      # Elevated elements
    'text': '#ffffff',          # Primary text
    'text_secondary': '#b3b3b3', # Secondary text
    'text_muted': '#6a6a6a',    # Muted/disabled text
    'border': '#2a2a2a',        # Borders
    'accent': '#1DB954',        # Spotify green (primary accent)
    'accent_hover': '#1ed760',   # Accent hover state
    'accent_pressed': '#169c46', # Accent pressed state
    'error': '#e22134',         # Error red
    'warning': '#f59b23',       # Warning orange
    'success': '#1DB954',       # Success (same as accent)
    'lyrics_bg': '#0a0a0a',     # Lyrics display background
    'lyrics_text': '#1DB954',    # Lyrics text (green on black)
}

# ===== Light Theme Color System =====
COLORS_LIGHT = {
    'bg': '#f5f5f5',             # Main background
    'surface': '#ffffff',       # Card/panel background
    'elevated': '#eeeeee',      # Elevated elements
    'text': '#212121',          # Primary text
    'text_secondary': '#616161', # Secondary text
    'text_muted': '#9e9e9e',    # Muted/disabled text
    'border': '#e0e0e0',        # Borders
    'accent': '#1DB954',        # Keep Spotify green
    'accent_hover': '#1ed760',   # Accent hover state
    'accent_pressed': '#169c46', # Accent pressed state
    'error': '#e22134',         # Error red
    'warning': '#f59b23',       # Warning orange
    'success': '#1DB954',       # Success
    'lyrics_bg': '#fafafa',     # Lyrics display background
    'lyrics_text': '#1DB954',    # Lyrics text
}

# Default to dark theme
COLORS = COLORS_DARK

# Font Configuration
FONT_PRIMARY = "Noto Sans TC"
FONT_FALLBACK = "Microsoft JhengHei"
FONT_MONO = "JetBrains Mono"


def get_font(size=10, bold=False, mono=False):
    """Get font with proper fallback"""
    weight = "bold" if bold else "normal"
    if mono:
        return (FONT_MONO, size, weight)
    return (FONT_PRIMARY, size, weight)


def style_button(btn, primary=False, danger=False):
    """Apply consistent button styling"""
    if danger:
        btn.config(
            bg=COLORS['error'],
            fg=COLORS['text'],
            activebackground='#ff4557',
            activeforeground=COLORS['text'],
            relief="flat",
            cursor="hand2"
        )
    elif primary:
        btn.config(
            bg=COLORS['accent'],
            fg=COLORS['bg'],
            activebackground=COLORS['accent_hover'],
            activeforeground=COLORS['bg'],
            relief="flat",
            cursor="hand2"
        )
    else:
        btn.config(
            bg=COLORS['elevated'],
            fg=COLORS['text'],
            activebackground=COLORS['surface'],
            activeforeground=COLORS['text'],
            relief="flat",
            cursor="hand2"
        )


def style_frame(frame, is_card=False):
    """Apply consistent frame styling"""
    frame.config(bg=COLORS['surface'] if is_card else COLORS['bg'])
    return frame

class PlaylistApp:
    def __init__(self, root):
        self.root = root
        self.app_version = get_version()
        self.root.title(f"{_('app_title')} v{self.app_version}")
        self.root.geometry("1400x850")
        self.root.configure(bg=COLORS['bg'])

        # --- UI Throttling & Batching ---
        self.last_progress_update = 0
        self.last_speed_update = 0
        self.progress_update_job = None
        self.pending_progress = None
        self.log_queue = deque()
        self.log_update_job = None
        self.last_full_refresh = 0
        self.songs_since_last_refresh = 0
        self.last_song_status_update = 0
        self.pending_song_updates = {}  # Batch song status updates

        self.config = load_config()

        # Load theme from config (default to dark)
        self.current_theme = self.config.get('theme', 'dark')
        self._apply_theme_colors()
        self.root.configure(bg=COLORS['bg'])

        # --- Configure ttk styles after theme is known ---
        self._configure_ttk_styles()

        # Load language from config (fix: ensure language is restored after restart/cancel)
        lang = self.config.get('language', 'zh-TW')
        I18N.set_language(lang)
        
        # Enable file logging and log startup
        from utils.logger import enable_file_logging
        from utils.config import CONFIG_FILE
        if self.config.get('base_path'):
            log_path = enable_file_logging(self.config['base_path'], max_files=10)
            self.log(f"--- 系統啟動 | 日誌檔案: {log_path} ---", immediate=True)
        else:
            self.log(f"--- 系統啟動 | 設定檔路徑: {CONFIG_FILE} ---", immediate=True)

        # Prompt for base path if not set
        if 'base_path' not in self.config or not self.config['base_path']:
            if not prompt_and_set_base_path(self.config):
                messagebox.showerror(_('error_critical_title'), _('base_folder_not_set_error'))
                self.root.destroy()
                return
        
        ensure_dirs(self.config)
        
        self.pause_event = threading.Event()
        self.pause_event.set() 
        self.stop_event = threading.Event()
        
        self.create_widgets()
        # 异步执行列表刷新（可选：如果不需要启动时显示状态图标，可设为 False）
        auto_refresh_on_startup = False  # 设为 True 则在启动时自动扫描音乐库
        if auto_refresh_on_startup:
            self.root.after(100, lambda: threading.Thread(target=self._async_refresh_url_list, daemon=True).start())
        else:
            # 只更新基础列表，不扫描音乐库（更快启动）
            self._update_basic_list()
        # 注意：不再於啟動時呼叫 update_stats_ui()，改為延遲到使用者切換到統計頁面時才載入

        # First Run Check
        if not self.config.get('setup_completed', False):
            self.first_run_wizard()

        # Delay background tasks until UI is fully loaded and responsive
        # Proactively fetch names on startup for URLs without names (delayed for faster startup)
        self.root.after(500, lambda: threading.Thread(target=self.proactive_name_fetch, daemon=True).start())

        # Check for updates on startup (after UI is fully loaded and user can interact)
        # Only check if user has enabled auto_update_check (default: True)
        if self.config.get('auto_update_check', True) and should_check_for_updates(self.config):
            # Use longer delay (5 seconds) to ensure UI is fully responsive
            self.root.after(5000, lambda: threading.Thread(target=self._background_update_check, daemon=True).start())

    def _background_update_check(self):
        """Background thread: Check for updates without blocking UI"""
        # Use a flag to prevent multiple update dialogs
        if hasattr(self, '_update_check_in_progress') and self._update_check_in_progress:
            return
        self._update_check_in_progress = True

        try:
            result = perform_update_check(self.config, log_func=self.log, silent=True)

            # Skip if user chose to skip this version
            skipped_version = self.config.get('skipped_version')
            if skipped_version and result.get('latest_version') == skipped_version:
                return

            # Show dialog if update available (using after to ensure UI thread)
            if result.get('has_update'):
                # Schedule dialog show on main UI thread
                self.root.after(0, lambda: self._show_update_dialog(result))
        finally:
            self._update_check_in_progress = False

    def _show_update_dialog(self, update_info):
        """Show update notification dialog (non-modal so UI remains usable)"""
        # Prevent multiple update dialogs
        if hasattr(self, '_update_dialog_open') and self._update_dialog_open:
            return
        self._update_dialog_open = True

        def on_dialog_close():
            self._update_dialog_open = False

        from gui.update_dialog import UpdateDialog
        dialog = UpdateDialog(self.root, update_info, on_close_callback=on_dialog_close)

    def _configure_ttk_styles(self):
        """Configure ttk widget styles for the current theme"""
        self.style = ttk.Style()

        # Use 'clam' theme for better customization support on Windows
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            pass  # Fallback to default if clam not available

        # Notebook / tab chrome
        self.style.configure("TNotebook",
                       background=COLORS['bg'],
                       borderwidth=0,
                       tabmargins=(8, 4, 8, 0))
        self.style.configure("TNotebook.Tab",
                       background=COLORS['surface'],
                       foreground=COLORS['text_secondary'],
                       padding=(14, 6),
                       borderwidth=0)
        self.style.map("TNotebook.Tab",
                 background=[('selected', COLORS['elevated']),
                            ('active', COLORS['surface'])],
                 foreground=[('selected', COLORS['text']),
                            ('active', COLORS['text'])])

        # Configure Treeview (song status list) - Dark theme
        self.style.configure("Treeview",
                       background=COLORS['elevated'],
                       foreground=COLORS['text'],
                       fieldbackground=COLORS['elevated'],
                       rowheight=24,
                       borderwidth=0,
                       relief='flat')
        self.style.configure("Treeview.Heading",
                       background=COLORS['surface'],
                       foreground=COLORS['text'],
                       font=get_font(10, bold=True),
                       borderwidth=0,
                       relief='flat')
        self.style.map("Treeview",
                 background=[('selected', COLORS['accent']),
                            ('!selected', COLORS['elevated'])],
                 foreground=[('selected', COLORS['bg']),
                            ('!selected', COLORS['text'])],
                 fieldbackground=[('selected', COLORS['accent']),
                                 ('!selected', COLORS['elevated'])])

        # Configure Combobox (player playlist selector)
        self.style.configure("TCombobox",
                       fieldbackground=COLORS['elevated'],
                       background=COLORS['elevated'],
                       foreground=COLORS['text'],
                       arrowcolor=COLORS['text'],
                       borderwidth=0,
                       relief='flat')
        self.style.map("TCombobox",
                 fieldbackground=[('readonly', COLORS['elevated']),
                                 ('disabled', COLORS['surface'])],
                 selectbackground=[('readonly', COLORS['accent'])],
                 selectforeground=[('readonly', COLORS['bg'])],
                 foreground=[('readonly', COLORS['text'])])

        # Configure Progressbar
        self.style.configure("Horizontal.TProgressbar",
                       background=COLORS['accent'],
                       troughcolor=COLORS['elevated'],
                       borderwidth=0,
                       lightcolor=COLORS['accent'],
                       darkcolor=COLORS['accent'],
                       thickness=8)

    def _apply_theme_colors(self):
        """Apply the current theme to the global COLORS dictionary"""
        global COLORS
        if self.current_theme == 'light':
            COLORS = COLORS_LIGHT
        else:
            COLORS = COLORS_DARK

    def apply_theme_to_all_widgets(self):
        """Apply current theme to all widgets dynamically (no restart needed)"""
        global COLORS

        # Reload theme from config
        self.current_theme = self.config.get('theme', 'dark')
        self._apply_theme_colors()

        # Reconfigure ttk styles
        self._configure_ttk_styles()

        # Update root
        self.root.configure(bg=COLORS['bg'])

        def widget_class(widget):
            try:
                return widget.winfo_class().lower()
            except tk.TclError:
                return ""

        # Helper to update widget colors
        def update_widget_colors(widget):
            try:
                widget_type = widget_class(widget)

                if widget_type in ('frame', 'tk', 'toplevel', 'panedwindow'):
                    widget.configure(bg=COLORS['bg'])
                elif widget_type == 'label':
                    # Determine background and text color based on parent and current config
                    parent = widget.master
                    parent_type = widget_class(parent) if parent else None
                    # If inside LabelFrame, use surface background
                    if parent_type == 'labelframe':
                        bg_color = COLORS['surface']
                    else:
                        bg_color = COLORS['bg']
                    
                    if hasattr(widget, '_is_secondary_text'):
                        widget.configure(bg=bg_color, fg=COLORS['text_secondary'])
                    elif hasattr(widget, '_is_muted_text'):
                        widget.configure(bg=bg_color, fg=COLORS['text_muted'])
                    else:
                        widget.configure(bg=bg_color, fg=COLORS['text'])
                elif widget_type == 'button':
                    # Check if primary/accent button by checking current bg
                    current_bg = widget.cget('bg')
                    if current_bg in [COLORS_DARK['accent'], COLORS_LIGHT['accent'], '#1DB954', '#1ed760']:
                        widget.configure(bg=COLORS['accent'], fg=COLORS['bg'],
                                       activebackground=COLORS['accent_hover'],
                                       activeforeground=COLORS['bg'])
                    elif current_bg in [COLORS_DARK['error'], COLORS_LIGHT['error'], '#e22134']:
                        widget.configure(bg=COLORS['error'], fg=COLORS['text'])
                    else:
                        widget.configure(bg=COLORS['elevated'], fg=COLORS['text'],
                                       activebackground=COLORS['surface'],
                                       activeforeground=COLORS['text'])
                elif widget_type == 'entry':
                    widget.configure(bg=COLORS['elevated'], fg=COLORS['text'],
                                   insertbackground=COLORS['text'],
                                   highlightbackground=COLORS['border'],
                                   highlightcolor=COLORS['accent'],
                                   readonlybackground=COLORS['elevated'])
                elif widget_type == 'listbox':
                    widget.configure(bg=COLORS['elevated'], fg=COLORS['text'],
                                   selectbackground=COLORS['accent'],
                                   selectforeground=COLORS['bg'],
                                   highlightbackground=COLORS['border'],
                                   highlightcolor=COLORS['accent'])
                elif widget_type == 'text':
                    widget.configure(bg=COLORS['elevated'], fg=COLORS['text_secondary'])
                elif widget_type == 'scale':
                    widget.configure(bg=COLORS['surface'], fg=COLORS['accent'],
                                   troughcolor=COLORS['elevated'])
                elif widget_type == 'checkbutton':
                    widget.configure(bg=COLORS['surface'], fg=COLORS['text'],
                                   selectcolor=COLORS['elevated'],
                                   activebackground=COLORS['surface'],
                                   activeforeground=COLORS['text'])
                elif widget_type == 'labelframe':
                    widget.configure(bg=COLORS['surface'], fg=COLORS['text'],
                                   highlightbackground=COLORS['border'],
                                   highlightcolor=COLORS['border'],
                                   bd=0, relief='flat')
                elif widget_type == 'scrollbar':
                    widget.configure(bg=COLORS['surface'], troughcolor=COLORS['elevated'],
                                   highlightbackground=COLORS['border'],
                                   activebackground=COLORS['surface'],
                                   relief='flat')
                elif widget_type in ('panedwindow', 'separator'):
                    widget.configure(bg=COLORS['bg'])
                elif widget_type in ('combobox', 'tcombobox'):
                    # ttk widgets are handled by style reconfiguration
                    pass
                elif widget_type in ('treeview', 'tview'):
                    # ttk widgets are handled by style reconfiguration
                    pass
            except tk.TclError:
                pass  # Widget might be destroyed

            # Recursively update children
            try:
                for child in widget.winfo_children():
                    update_widget_colors(child)
            except tk.TclError:
                pass

        # Update all tabs
        update_widget_colors(self.tab_library)
        update_widget_colors(self.tab_player)
        update_widget_colors(self.tab_stats)

        # Update top bar and other direct children of root
        for child in self.root.winfo_children():
            update_widget_colors(child)

        # Update header specifically
        self.header_lbl.configure(bg=COLORS['bg'], fg=COLORS['text'])

        # Update settings button
        self.settings_btn.configure(bg=COLORS['elevated'], fg=COLORS['text'],
                                    activebackground=COLORS['surface'])

        # Update progress label
        self.progress_label.configure(bg=COLORS['bg'], fg=COLORS['accent'])
        self.speed_label.configure(bg=COLORS['bg'], fg=COLORS['text_secondary'])

        # Update lyrics card
        for widget in self.player_frame.winfo_children():
            for w in widget.winfo_children():
                try:
                    w.configure(bg=COLORS['surface'])
                except:
                    pass

        # Update lyrics display
        try:
            lyrics_card = self.lyrics_lbl.winfo_parent()
            self.lyrics_lbl.configure(bg=COLORS['lyrics_bg'], fg=COLORS['lyrics_text'])
        except:
            pass

    def first_run_wizard(self):
        """Prompt for language on first run - Dark theme"""
        def set_lang(lang):
            self.config['language'] = lang
            self.config['setup_completed'] = True
            save_config(self.config)
            I18N.set_language(lang)
            self.update_ui_text()
            top.destroy()
            # If base path not set, it will be handled by regular logic in init or next loop

        top = tk.Toplevel(self.root)
        top.title("Welcome / 歡迎")
        top.geometry("500x420")
        top.resizable(False, False)
        top.transient(self.root)
        top.grab_set()
        top.state('normal')
        top.lift()
        top.focus_force()
        top.configure(bg=COLORS['bg'])

        # Center dialog
        screen_width = top.winfo_screenwidth()
        screen_height = top.winfo_screenheight()
        x = (screen_width // 2) - (500 // 2)
        y = (screen_height // 2) - (420 // 2)
        top.geometry(f'500x420+{x}+{y}')

        top.deiconify()
        top.lift()
        top.focus_force()

        # Main frame with dark background
        main_frame = tk.Frame(top, bg=COLORS['bg'], padx=30, pady=30)
        main_frame.pack(fill="both", expand=True)

        # Title with accent color
        tk.Label(main_frame, text="🎵", font=get_font(48), fg=COLORS['accent'], bg=COLORS['bg']).pack(pady=(10, 0))
        tk.Label(main_frame, text="Playlist Administrator", font=get_font(22, bold=True), fg=COLORS['text'], bg=COLORS['bg']).pack(pady=(5, 5))
        tk.Label(main_frame, text="播放清單管理工具", font=get_font(14), fg=COLORS['text_secondary'], bg=COLORS['bg']).pack(pady=(0, 20))

        # Language selection prompt
        tk.Label(main_frame, text="請選擇語言 / Select Language", font=get_font(12), fg=COLORS['text_secondary'], bg=COLORS['bg']).pack(pady=(10, 20))

        # Button frame
        btn_frame = tk.Frame(main_frame, bg=COLORS['bg'])
        btn_frame.pack(fill="x", pady=20)

        # Chinese button (primary)
        zh_btn = tk.Button(btn_frame, text="繁體中文", command=lambda: set_lang('zh-TW'),
                          font=get_font(12, bold=True), height=2, width=12,
                          bg=COLORS['accent'], fg=COLORS['bg'],
                          activebackground=COLORS['accent_hover'],
                          activeforeground=COLORS['bg'],
                          relief="flat", cursor="hand2")
        zh_btn.pack(side="left", padx=10, expand=True)

        # English button (secondary)
        en_btn = tk.Button(btn_frame, text="English", command=lambda: set_lang('en'),
                          font=get_font(12), height=2, width=12,
                          bg=COLORS['elevated'], fg=COLORS['text'],
                          activebackground=COLORS['surface'],
                          activeforeground=COLORS['text'],
                          relief="flat", cursor="hand2")
        en_btn.pack(side="right", padx=10, expand=True)

        # Footer text
        tk.Label(main_frame, text="版本 / Version " + self.app_version,
                font=get_font(10), fg=COLORS['text_muted'], bg=COLORS['bg']).pack(side="bottom", pady=(20, 0))

        # Block until closed
        self.root.wait_window(top)

    def open_settings_window(self):
        from gui.settings import SettingsWindow

        def on_settings_close(lang_changed=False, path_changed=False, theme_changed=False):
            if lang_changed:
                self.update_ui_text()
                self.refresh_url_list()
                self.update_stats_ui()
            if path_changed:
                self.log(_('base_folder_changed'))
                self.refresh_url_list()
                self.update_stats_ui()
            if theme_changed:
                self.apply_theme_to_all_widgets()

        SettingsWindow(self.root, self.config, on_settings_close)

    def proactive_name_fetch(self):
        from core.spotify import scrape_via_spotify_embed
        
        urls = [u for u in self.config.get('spotify_urls', []) if "playlist/" in u]
        # Playlists only
        self.pl_urls = [u for u in urls if "playlist/" in u]
        url_names = self.config.get('url_names', {})
        missing = [u for u in urls if u not in url_names]
        if not missing:
            return

        scrape_via_spotify_embed(self.config, None, self.log, target_urls=missing)
        self.root.after(0, self.refresh_url_list)

    def _init_pygame_async(self):
        """在后台线程异步初始化 Pygame，避免阻塞主线程"""
        def _init():
            try:
                import os
                # 必须在 pygame 导入前设置
                os.environ['SDL_VIDEODRIVER'] = 'dummy'
                import pygame
                pygame.init()
                pygame.mixer.init()
                pygame.mixer.music.set_volume(0.7)
                if pygame.display.get_init():
                    pygame.display.set_mode((1, 1))
                self._pygame_initialized = True
                print("[Pygame] 初始化完成")
            except Exception as e:
                print(f"[Pygame] 初始化失败: {e}")
        threading.Thread(target=_init, daemon=True).start()

    def _ensure_pygame_init(self):
        """确保 Pygame 已初始化（同步等待，用于播放前）"""
        if not self._pygame_initialized:
            import os
            os.environ['SDL_VIDEODRIVER'] = 'dummy'
            import pygame
            pygame.init()
            pygame.mixer.init()
            pygame.mixer.music.set_volume(self.vol_var.get() / 100.0)
            if pygame.display.get_init():
                pygame.display.set_mode((1, 1))
            self._pygame_initialized = True

    def _create_action_buttons(self):
        """创建操作按钮（放在 action_frame 中）"""
        # Action buttons with dark theme styling
        buttons_row = tk.Frame(self.action_frame, bg=COLORS['surface'])
        buttons_row.pack(fill="x", padx=6, pady=6)
        buttons_row.columnconfigure(0, weight=1, uniform="action")
        buttons_row.columnconfigure(1, weight=1, uniform="action")
        buttons_row.columnconfigure(2, weight=1, uniform="action")
        buttons_row.columnconfigure(3, weight=1, uniform="action")

        self.update_btn = tk.Button(buttons_row, text=_('update_all_btn'),
                                    command=self.run_update,
                                    bg=COLORS['accent'], fg=COLORS['bg'],
                                    activebackground=COLORS['accent_hover'],
                                    activeforeground=COLORS['bg'],
                                    font=get_font(10, bold=True),
                                    relief="flat", cursor="hand2",
                                    padx=10, pady=5,
                                    height=1)
        self.update_btn.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.pause_btn = tk.Button(buttons_row, text=_('pause_btn'),
                                   command=self.toggle_pause,
                                   bg=COLORS['elevated'], fg=COLORS['text'],
                                   activebackground=COLORS['surface'],
                                   activeforeground=COLORS['text'],
                                   state="disabled",
                                   font=get_font(10, bold=True),
                                   relief="flat", cursor="hand2",
                                   padx=10, pady=5,
                                   height=1)
        self.pause_btn.grid(row=0, column=1, sticky="ew", padx=6)

        self.cancel_btn = tk.Button(buttons_row, text=_('cancel_btn'),
                                    command=self.run_cancel,
                                    bg=COLORS['error'], fg=COLORS['text'],
                                    activebackground='#ff4557',
                                    activeforeground=COLORS['text'],
                                    state="disabled",
                                    font=get_font(10, bold=True),
                                    relief="flat", cursor="hand2",
                                    padx=10, pady=5,
                                    height=1)
        self.cancel_btn.grid(row=0, column=2, sticky="ew", padx=6)

        self.export_btn = tk.Button(buttons_row, text=_('export_usb_btn'),
                                    command=self.open_export_window,
                                    bg=COLORS['elevated'], fg=COLORS['text'],
                                    activebackground=COLORS['surface'],
                                    activeforeground=COLORS['text'],
                                    font=get_font(10, bold=True),
                                    relief="flat", cursor="hand2",
                                    padx=10, pady=5,
                                    height=1)
        self.export_btn.grid(row=0, column=3, sticky="ew", padx=(6, 0))

    def _update_basic_list(self):
        """只更新基础列表显示，不扫描音乐库（快速启动模式）"""
        url_names = self.config.get('url_names', {})
        last_updated = self.config.get('last_updated', {})
        import datetime
        today = datetime.datetime.now().strftime('%Y-%m-%d')

        urls = self.config.get('spotify_urls', [])
        self.pl_urls = [u for u in urls if "artist/" not in u and "album/" not in u and "track/" not in u]
        self.al_urls = [u for u in urls if "album/" in u]
        self.ar_urls = [u for u in urls if "artist/" in u]
        self.st_urls = [u for u in urls if "track/" in u]

        # 清空列表
        self.pl_listbox.delete(0, tk.END)

        # 只显示名称，不检查文件状态
        all_names = []
        for url in urls:
            name = url_names.get(url, url)
            is_synced_today = last_updated.get(url) == today
            # 简化显示，不扫描文件
            if is_synced_today:
                status_text = f"🔄 {name} ({_('synced_today')})"
            else:
                status_text = f"📋 {name}"
            self.pl_listbox.insert(tk.END, status_text)
            all_names.append(name)

        # 更新播放器下拉列表
        all_names.sort()
        self.player_playlist_combo['values'] = all_names
        if all_names and not self.player_playlist_combo.get():
            self.player_playlist_combo.set(all_names[0])

    def _async_refresh_url_list(self):
        """在后台线程异步刷新 URL 列表，避免阻塞主线程造成白屏"""
        try:
            # 在后台线程执行耗时的文件扫描
            data = self._collect_url_list_data()
            # 在主线程更新UI
            self.root.after(0, lambda: self._update_url_list_ui(data))
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"Error in async refresh: {e}")

    def _collect_url_list_data(self):
        """收集 URL 列表数据（在后台线程执行，可能耗时几秒）"""
        url_names = self.config.get('url_names', {})
        last_updated = self.config.get('last_updated', {})

        import datetime
        import os
        today = datetime.datetime.now().strftime('%Y-%m-%d')

        if 'playlists_path' not in self.config or 'library_path' not in self.config:
            from utils.config import derive_paths
            derive_paths(self.config)

        from core.library import get_playlist_completeness_report
        playlists_path = self.config.get('playlists_path')
        library_path = self.config.get('library_path')

        if not playlists_path or not os.path.exists(playlists_path):
            return None

        urls = self.config.get('spotify_urls', [])

        pl_urls = [u for u in urls if "artist/" not in u and "album/" not in u and "track/" not in u]
        al_urls = [u for u in urls if "album/" in u]
        ar_urls = [u for u in urls if "artist/" in u]
        st_urls = [u for u in urls if "track/" in u]

        pl_files = []
        for ext in ['.m3u', '.m3u8', '.txt']:
            pl_files.extend(glob.glob(os.path.join(playlists_path, f"*{ext}")))

        # 耗时的操作：扫描整个音乐库
        report = get_playlist_completeness_report(pl_files, library_path)

        # 构建所有项目数据
        items = []
        for url in urls:
            name = url_names.get(url, url)
            is_synced_today = last_updated.get(url) == today

            if "track/" in url:
                mp3_file = os.path.join(library_path, f"{name}.mp3")
                if os.path.exists(mp3_file):
                    status_text = f"✅ {name}" if is_synced_today else f"📦 {name} ({_('local_complete')})"
                else:
                    status_text = f"🔄 {name}" if is_synced_today else f"⏳ {name} ({_('wait_download')})"
            else:
                pl_file = None
                for ext in ['.m3u', '.m3u8']:
                    test_file = os.path.join(playlists_path, f"{name}{ext}")
                    if os.path.exists(test_file):
                        pl_file = test_file
                        break

                if pl_file and os.path.exists(pl_file):
                    is_complete, missing, total = report.get(pl_file, (True, 0, 0))
                    if is_complete:
                        status_text = f"✅ {name}" if is_synced_today else f"📦 {name} ({_('local_complete')})"
                    else:
                        if is_synced_today:
                            status_text = f"🔄 {name} ({_('incomplete_warning_title')}, {_('missing_songs', missing)})"
                        else:
                            status_text = f"⚠️ {name} ({_('wait_download')}, {_('missing_songs', missing)})"
                else:
                    if is_synced_today:
                        status_text = f"🔄 {name} ({_('synced_today')})"
                    else:
                        status_text = f"⏳ {name} ({_('wait_sync')})"
            items.append({'url': url, 'text': status_text, 'category': 'playlist'})

        # 本地播放列表
        processed_names = [url_names.get(u, u) for u in urls]
        local_items = []
        for pl_file in pl_files:
            name = os.path.splitext(os.path.basename(pl_file))[0]
            if name in processed_names or is_internal_playlist_name(name):
                continue
            is_complete, missing, total = report.get(pl_file, (True, 0, 0))
            if is_complete:
                status_text = f"📦 {name} ({_('local_complete')})"
            else:
                status_text = f"⚠️ {name} ({_('wait_download')}, 缺 {missing} 首)"
            local_items.append({'name': name, 'text': status_text})

        # 播放器下拉列表数据
        all_playlist_names = []
        for url in urls:
            all_playlist_names.append(url_names.get(url, url))
        for pl_file in pl_files:
            name = os.path.splitext(os.path.basename(pl_file))[0]
            if name not in all_playlist_names and not is_internal_playlist_name(name):
                all_playlist_names.append(name)
        all_playlist_names.sort()

        return {
            'items': items,
            'local_items': local_items,
            'pl_urls': pl_urls,
            'al_urls': al_urls,
            'ar_urls': ar_urls,
            'st_urls': st_urls,
            'all_playlist_names': all_playlist_names
        }

    def _update_url_list_ui(self, data):
        """在主线程更新 UI（线程安全）"""
        if data is None:
            self.log(_('playlist_path_missing', self.config.get('playlists_path')))
            return

        # 保存当前选择和滚动位置
        saves = [{'selection': self.pl_listbox.curselection(), 'yview': self.pl_listbox.yview()}]

        self.pl_listbox.delete(0, tk.END)

        # 更新 URL 列表
        for item in data['items']:
            self.pl_listbox.insert(tk.END, item['text'])

        # 更新本地播放列表
        for item in data['local_items']:
            self.pl_listbox.insert(tk.END, item['text'])

        self.pl_urls = data['pl_urls'] + ["local:" + item['name'] for item in data['local_items']]
        self.al_urls = data['al_urls']
        self.ar_urls = data['ar_urls']
        self.st_urls = data['st_urls']

        # 恢复选择和滚动位置
        for idx in saves[0]['selection']:
            if idx < self.pl_listbox.size():
                self.pl_listbox.selection_set(idx)
        self.pl_listbox.yview_moveto(saves[0]['yview'][0])

        # 更新播放器下拉列表
        self.player_playlist_combo['values'] = data['all_playlist_names']
        current_val = self.player_playlist_combo.get()
        if current_val and current_val not in data['all_playlist_names']:
            self.player_playlist_combo.set('')
        elif not current_val and data['all_playlist_names']:
            self.player_playlist_combo.set(data['all_playlist_names'][0])

    def create_widgets(self):
        # Top Bar (Settings Button only) - Dark theme
        top_bar = tk.Frame(self.root, bg=COLORS['bg'])
        top_bar.pack(fill="x", padx=16, pady=(8, 0))

        # Title label on the left
        self.header_lbl = tk.Label(top_bar, text=f"🎵 {_('app_title')}",
                                   font=get_font(14, bold=True),
                                   fg=COLORS['text'], bg=COLORS['bg'])
        self.header_lbl.pack(side="left")

        # Settings Button (Right aligned) - Styled
        self.settings_btn = tk.Button(top_bar, text=_('settings_btn'),
                                      command=self.open_settings_window,
                                      font=get_font(10),
                                      bg=COLORS['elevated'], fg=COLORS['text'],
                                      activebackground=COLORS['surface'],
                                      activeforeground=COLORS['text'],
                                      relief="flat", cursor="hand2",
                                      padx=12, pady=4)
        self.settings_btn.pack(side="right", padx=5)

        # Tabs container (Root) - Dark theme background
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=16, pady=(8, 16))

        # Tab 1: Library - Dark theme (全面固定布局，不可拖动)
        self.tab_library = tk.Frame(self.notebook, bg=COLORS['bg'])
        self.notebook.add(self.tab_library, text=_('tab_library'))

        # Tab 2: Player - Dark theme
        self.tab_player = tk.Frame(self.notebook, bg=COLORS['bg'])
        self.notebook.add(self.tab_player, text=_('tab_player'))

        # Tab 3: Statistics - Dark theme
        self.tab_stats = tk.Frame(self.notebook, bg=COLORS['bg'])
        self.notebook.add(self.tab_stats, text=_('tab_statistics'))

        # 綁定頁面切換事件，首次切換到統計頁面時才載入數據
        self._stats_tab_loaded = False
        self.notebook.bind('<<NotebookTabChanged>>', self._on_tab_changed)

        # 主容器：內部標籤頁（節省高度空間）
        self.library_top_frame = tk.Frame(self.tab_library, bg=COLORS['surface'])
        self.library_top_frame.pack(fill="both", expand=True, padx=12, pady=(8, 8))

        # 建立內部標籤頁：播放清單管理
        self.inner_notebook = ttk.Notebook(self.library_top_frame)
        self.inner_notebook.pack(fill="both", expand=True)
        # 配置內部標籤頁樣式
        self.style.configure("Inner.TNotebook", background=COLORS['surface'], borderwidth=0)
        self.style.configure("Inner.TNotebook.Tab",
                       background=COLORS['surface'],
                       foreground=COLORS['text_secondary'],
                       padding=(10, 4),
                       borderwidth=0)
        self.style.map("Inner.TNotebook.Tab",
                 background=[('selected', COLORS['elevated']),
                            ('active', COLORS['surface'])],
                 foreground=[('selected', COLORS['text']),
                            ('active', COLORS['text'])])
        self.inner_notebook.configure(style="Inner.TNotebook")

        # 內部標籤頁 1：URL 管理
        self.inner_tab_urls = tk.Frame(self.inner_notebook, bg=COLORS['surface'])
        self.inner_notebook.add(self.inner_tab_urls, text="Spotify 網址管理")

        # 內部標籤頁 2：播放清單列表
        self.inner_tab_playlists = tk.Frame(self.inner_notebook, bg=COLORS['surface'])
        self.inner_notebook.add(self.inner_tab_playlists, text="播放清單與歌曲狀態")

        # 1. URL Section (In inner tab 1) - Dark theme card
        self.url_frame = tk.LabelFrame(self.inner_tab_urls, text=_('step_1_title'),
                                       font=get_font(11, bold=True),
                                       fg=COLORS['text'], bg=COLORS['surface'],
                                       highlightbackground=COLORS['border'],
                                       highlightthickness=1, bd=0)
        # Don't expand vertically - only take needed space for URL input
        self.url_frame.pack(fill="x", expand=False, padx=12, pady=8)
        
        # URL Entry - Dark theme styled
        self.url_entry = tk.Entry(self.url_frame, font=get_font(11),
                                  bg=COLORS['elevated'], fg=COLORS['text'],
                                  insertbackground=COLORS['text'],
                                  relief="flat", highlightthickness=1,
                                  highlightbackground=COLORS['border'],
                                  highlightcolor=COLORS['accent'])
        self.url_entry.pack(side="top", fill="x", padx=12, pady=8)

        btn_frame = tk.Frame(self.url_frame, bg=COLORS['surface'])
        btn_frame.pack(fill="x", padx=12, pady=8)
        btn_frame.columnconfigure(0, weight=0)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=0)

        left_btns = tk.Frame(btn_frame, bg=COLORS['surface'])
        left_btns.grid(row=0, column=0, sticky="w")

        self.add_btn = tk.Button(left_btns, text=_('add_url_btn'),
                                 command=self.add_url, font=get_font(10),
                                 bg=COLORS['accent'], fg=COLORS['bg'],
                                 activebackground=COLORS['accent_hover'],
                                 activeforeground=COLORS['bg'],
                                 relief="flat", cursor="hand2",
                                 padx=12, pady=4)
        self.add_btn.pack(side="left", padx=(0, 8))

        self.remove_btn = tk.Button(left_btns, text=_('remove_url_btn'),
                                    command=self.remove_url, font=get_font(10),
                                    bg=COLORS['elevated'], fg=COLORS['text'],
                                    activebackground=COLORS['surface'],
                                    activeforeground=COLORS['text'],
                                    relief="flat", cursor="hand2",
                                    padx=12, pady=4)
        self.remove_btn.pack(side="left", padx=(0, 8))

        self.reset_btn = tk.Button(btn_frame, text=_('reset_status_btn'),
                                   command=self.reset_update_status, font=get_font(10),
                                   bg=COLORS['elevated'], fg=COLORS['text_secondary'],
                                   activebackground=COLORS['surface'],
                                   activeforeground=COLORS['text'],
                                   relief="flat", cursor="hand2",
                                   padx=12, pady=4)
        self.reset_btn.grid(row=0, column=2, sticky="e")

        # 標籤頁 2：播放清單列表和歌曲狀態
        list_container = tk.Frame(self.inner_tab_playlists, bg=COLORS['surface'])
        list_container.pack(fill="both", expand=True, padx=8, pady=8)

        self.list_paned = tk.PanedWindow(
            list_container,
            orient="horizontal",
            bg=COLORS['surface'],
            bd=0,
            sashwidth=8,
            opaqueresize=True,
            showhandle=False,
        )
        self.list_paned.pack(fill="both", expand=True)

        # Left side: Playlists
        pl_side = tk.Frame(self.list_paned, bg=COLORS['surface'])
        self.list_paned.add(pl_side, minsize=550)
        tk.Label(pl_side, text="🎵 播放清單",
                 font=get_font(11, bold=True),
                 fg=COLORS['text'], bg=COLORS['surface']).pack(anchor="w", pady=(0, 4))

        # Styled listbox with dark theme
        self.pl_listbox = tk.Listbox(pl_side, height=10, font=get_font(11),
                                     exportselection=False,
                                     bg=COLORS['elevated'], fg=COLORS['text'],
                                     selectbackground=COLORS['accent'],
                                     selectforeground=COLORS['bg'],
                                     relief="flat", highlightthickness=1,
                                     highlightbackground=COLORS['border'])
        self.pl_listbox.pack(side="left", fill="both", expand=True)

        # Add scrollbar to listbox
        pl_scroll = tk.Scrollbar(pl_side, orient="vertical", command=self.pl_listbox.yview,
                                  bg=COLORS['surface'], troughcolor=COLORS['elevated'])
        pl_scroll.pack(side="right", fill="y")
        self.pl_listbox.config(yscrollcommand=pl_scroll.set)

        # Button to view songs in selected playlist - Dark theme
        self.view_songs_btn = tk.Button(pl_side, text=_('view_songs_btn'),
                                        command=self.view_playlist_songs,
                                        font=get_font(10),
                                        bg=COLORS['surface'], fg=COLORS['accent'],
                                        activebackground=COLORS['elevated'],
                                        activeforeground=COLORS['accent_hover'],
                                        relief="flat", cursor="hand2",
                                        padx=8, pady=4)
        self.view_songs_btn.pack(side="bottom", fill="x", pady=(4, 0))

        # Right side: Song Status List
        self.song_status_frame = tk.LabelFrame(self.list_paned, text=_('song_status_title'),
                                               font=get_font(11, bold=True),
                                               fg=COLORS['text'], bg=COLORS['surface'],
                                               highlightbackground=COLORS['border'],
                                               highlightthickness=1, bd=0)
        self.list_paned.add(self.song_status_frame, minsize=520)

        # Reduce listbox height to ensure action buttons have space
        self.pl_listbox.config(height=10)

        # Create treeview for song status with dark theme
        columns = ('Status', 'Song')
        self.song_status_tree = ttk.Treeview(self.song_status_frame, columns=columns,
                                             show='tree headings', height=10)
        self.song_status_tree.heading('#0', text=_('song_status_no'))
        self.song_status_tree.heading('Status', text=_('song_status_status'))
        self.song_status_tree.heading('Song', text=_('song_status_song'))

        # Configure column widths
        self.song_status_tree.column('#0', width=40)
        self.song_status_tree.column('Status', width=60)
        self.song_status_tree.column('Song', width=280, stretch=True)

        self.root.after(0, self._set_initial_playlist_split)

        # Add scrollbar
        song_scroll = tk.Scrollbar(self.song_status_frame, orient="vertical",
                                   command=self.song_status_tree.yview,
                                   bg=COLORS['surface'], troughcolor=COLORS['elevated'])
        song_scroll.pack(side="right", fill="y")
        self.song_status_tree.pack(side="left", fill="both", expand=True, padx=8, pady=6)
        self.song_status_tree.config(yscrollcommand=song_scroll.set)

        # Initialize song status data
        self.song_status_data = {}

        # Bind Listbox selection for player (automatically switch to Player tab)
        self.pl_listbox.bind('<<ListboxSelect>>', self.on_listbox_select)

        # 2.5 Player Section (In Tab 2) - COMPLETE REDESIGN
        # Structured player layout replacing the "black hole" design
        player_main_container = tk.Frame(self.tab_player, bg=COLORS['bg'])
        player_main_container.pack(fill="both", expand=True, padx=16, pady=16)

        # Playlist Selector at the top
        player_top_bar = tk.Frame(player_main_container, bg=COLORS['bg'])
        player_top_bar.pack(fill="x", pady=(0, 12))
        player_top_bar.columnconfigure(1, weight=1)

        tk.Label(player_top_bar, text=_('player_playlist_label'),
                 font=get_font(11), fg=COLORS['text_secondary'], bg=COLORS['bg']).grid(row=0, column=0, sticky="w", padx=(0, 8))

        # Style the combobox
        self.player_playlist_combo = ttk.Combobox(player_top_bar, state="readonly",
                                                   font=get_font(11), width=35)
        self.player_playlist_combo.grid(row=0, column=1, sticky="ew", padx=8)

        self.player_load_btn = tk.Button(player_top_bar, text=_('player_load_btn'),
                                           command=self.load_selected_playlist,
                                           bg=COLORS['accent'], fg=COLORS['bg'],
                                           activebackground=COLORS['accent_hover'],
                                           activeforeground=COLORS['bg'],
                                           font=get_font(10, bold=True),
                                           relief="flat", cursor="hand2",
                                           padx=16, pady=4)
        self.player_load_btn.grid(row=0, column=2, sticky="e", padx=(8, 0))

        # ===== PLAYER CARD =====
        self.player_frame = tk.Frame(player_main_container, bg=COLORS['surface'],
                                      highlightbackground=COLORS['border'],
                                      highlightthickness=1)
        self.player_frame.pack(fill="both", expand=True)

        # ----- Top: Album Art Placeholder + Song Info -----
        song_info_frame = tk.Frame(self.player_frame, bg=COLORS['surface'])
        song_info_frame.pack(fill="x", padx=20, pady=(20, 12))

        # Album art placeholder (left side)
        self.album_art_lbl = tk.Label(song_info_frame, text="🎵",
                                      font=get_font(64),
                                      fg=COLORS['text_muted'],
                                      bg=COLORS['elevated'],
                                      width=4, height=2)
        self.album_art_lbl.pack(side="left", padx=(0, 20))

        # Song info (right side of album art)
        info_text_frame = tk.Frame(song_info_frame, bg=COLORS['surface'])
        info_text_frame.pack(side="left", fill="both", expand=True)

        # Song title
        self.song_title_lbl = tk.Label(info_text_frame,
                                       text=_('player_select_playlist_hint'),
                                       font=get_font(18, bold=True),
                                       fg=COLORS['text'], bg=COLORS['surface'],
                                       anchor="w")
        self.song_title_lbl.pack(fill="x", pady=(4, 2))

        # Artist
        self.song_artist_lbl = tk.Label(info_text_frame,
                                          text="",
                                          font=get_font(14),
                                          fg=COLORS['text_secondary'],
                                          bg=COLORS['surface'],
                                          anchor="w")
        self.song_artist_lbl.pack(fill="x", pady=(2, 4))

        # Now playing label (accent color)
        self.now_playing_lbl = tk.Label(info_text_frame,
                                        text=_('player_now_playing', _('no_data')),
                                        font=get_font(11),
                                        fg=COLORS['accent'],
                                        bg=COLORS['surface'],
                                        anchor="w")
        self.now_playing_lbl.pack(fill="x", pady=(8, 0))

        # ----- Middle: Lyrics Display (NOT a black hole) -----
        lyrics_card = tk.Frame(self.player_frame, bg=COLORS['lyrics_bg'],
                               highlightbackground=COLORS['border'],
                               highlightthickness=1)
        lyrics_card.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        # Lyrics label - smaller, elegant, not a giant black box
        self.lyrics_lbl = tk.Label(lyrics_card,
                                   text=_('player_no_lyrics'),
                                   font=get_font(20, bold=True),
                                   fg=COLORS['lyrics_text'],
                                   bg=COLORS['lyrics_bg'],
                                   wraplength=700,
                                   justify="center")
        self.lyrics_lbl.pack(expand=True, fill="both", pady=24)

        # ----- Bottom: Controls -----
        controls_container = tk.Frame(self.player_frame, bg=COLORS['surface'])
        controls_container.pack(fill="x", padx=20, pady=(0, 20))

        # Progress bar frame
        progress_frame = tk.Frame(controls_container, bg=COLORS['surface'])
        progress_frame.pack(fill="x", pady=(0, 12))

        # Time labels
        self.current_time_lbl = tk.Label(progress_frame, text="0:00",
                                         font=get_font(10, mono=True),
                                         fg=COLORS['text_secondary'],
                                         bg=COLORS['surface'])
        self.current_time_lbl.pack(side="left")

        # Progress slider (custom styled)
        self.playback_progress_var = tk.DoubleVar(value=0)
        self.progress_slider = tk.Scale(progress_frame, from_=0, to=100,
                                        orient="horizontal",
                                        variable=self.playback_progress_var,
                                        showvalue=False,
                                        bg=COLORS['surface'],
                                        fg=COLORS['accent'],
                                        troughcolor=COLORS['elevated'],
                                        highlightthickness=0,
                                        relief="flat",
                                        sliderrelief="flat",
                                        sliderlength=12,
                                        width=8)
        self.progress_slider.pack(side="left", fill="x", expand=True, padx=12)

        self.total_time_lbl = tk.Label(progress_frame, text="0:00",
                                       font=get_font(10, mono=True),
                                       fg=COLORS['text_secondary'],
                                       bg=COLORS['surface'])
        self.total_time_lbl.pack(side="left")

        # Control buttons frame
        control_buttons = tk.Frame(controls_container, bg=COLORS['surface'])
        control_buttons.pack(pady=(8, 12))

        # Previous button
        self.prev_btn = tk.Button(control_buttons, text="⏮",
                                  command=self.play_prev,
                                  width=4, height=1,
                                  font=get_font(16),
                                  bg=COLORS['elevated'], fg=COLORS['text'],
                                  activebackground=COLORS['surface'],
                                  activeforeground=COLORS['text'],
                                  relief="flat", cursor="hand2")
        self.prev_btn.pack(side="left", padx=8)

        # Play/Pause button (bigger, accent color)
        self.play_btn = tk.Button(control_buttons, text="▶",
                                  command=self.toggle_playback,
                                  width=6, height=1,
                                  font=get_font(20, bold=True),
                                  bg=COLORS['accent'], fg=COLORS['bg'],
                                  activebackground=COLORS['accent_hover'],
                                  activeforeground=COLORS['bg'],
                                  relief="flat", cursor="hand2")
        self.play_btn.pack(side="left", padx=12)

        # Next button
        self.next_btn = tk.Button(control_buttons, text="⏭",
                                  command=self.play_next,
                                  width=4, height=1,
                                  font=get_font(16),
                                  bg=COLORS['elevated'], fg=COLORS['text'],
                                  activebackground=COLORS['surface'],
                                  activeforeground=COLORS['text'],
                                  relief="flat", cursor="hand2")
        self.next_btn.pack(side="left", padx=8)

        # Shuffle checkbox with dark theme
        self.shuffle_var = tk.BooleanVar(value=False)
        self.shuffle_btn = tk.Checkbutton(controls_container,
                                          text=_('player_shuffle'),
                                          variable=self.shuffle_var,
                                          font=get_font(11),
                                          fg=COLORS['text_secondary'],
                                          bg=COLORS['surface'],
                                          selectcolor=COLORS['elevated'],
                                          activebackground=COLORS['surface'],
                                          activeforeground=COLORS['accent'])
        self.shuffle_btn.pack(pady=(4, 0))

        # Volume and Lyrics Offset row
        bottom_controls = tk.Frame(controls_container, bg=COLORS['surface'])
        bottom_controls.pack(fill="x", pady=(12, 0))

        # Volume (left side)
        vol_frame = tk.Frame(bottom_controls, bg=COLORS['surface'])
        vol_frame.pack(side="left", fill="x", expand=True)

        tk.Label(vol_frame, text="🔊", font=get_font(12),
                 fg=COLORS['text_secondary'], bg=COLORS['surface']).pack(side="left", padx=(0, 8))

        self.vol_var = tk.DoubleVar(value=70)
        self.vol_scale = tk.Scale(vol_frame, from_=0, to=100,
                                  orient="horizontal",
                                  variable=self.vol_var,
                                  command=self.change_volume,
                                  showvalue=False,
                                  bg=COLORS['surface'],
                                  fg=COLORS['accent'],
                                  troughcolor=COLORS['elevated'],
                                  highlightthickness=0,
                                  relief="flat",
                                  sliderrelief="flat",
                                  sliderlength=10,
                                  width=6,
                                  length=120)
        self.vol_scale.pack(side="left")

        self.vol_lbl = tk.Label(vol_frame, text=_('player_volume', 70),
                                font=get_font(10, mono=True),
                                fg=COLORS['text_secondary'], bg=COLORS['surface'],
                                width=10)
        self.vol_lbl.pack(side="left", padx=(8, 0))

        # Lyrics Offset (right side)
        offset_frame = tk.Frame(bottom_controls, bg=COLORS['surface'])
        offset_frame.pack(side="right")

        tk.Label(offset_frame, text=_('player_lyrics_offset') + ":",
                 font=get_font(10),
                 fg=COLORS['text_secondary'], bg=COLORS['surface']).pack(side="left", padx=(0, 8))

        offset_dec_btn = tk.Button(offset_frame, text="-0.5s",
                                   command=lambda: self.adjust_lyrics_offset(-0.5),
                                   width=5, font=get_font(9),
                                   bg=COLORS['elevated'], fg=COLORS['text'],
                                   activebackground=COLORS['surface'],
                                   relief="flat", cursor="hand2")
        offset_dec_btn.pack(side="left", padx=2)

        self.offset_lbl = tk.Label(offset_frame, text="0.0s",
                                   font=get_font(10, bold=True, mono=True),
                                   fg=COLORS['accent'], bg=COLORS['surface'],
                                   width=8)
        self.offset_lbl.pack(side="left", padx=4)

        offset_inc_btn = tk.Button(offset_frame, text="+0.5s",
                                   command=lambda: self.adjust_lyrics_offset(0.5),
                                   width=5, font=get_font(9),
                                   bg=COLORS['elevated'], fg=COLORS['text'],
                                   activebackground=COLORS['surface'],
                                   relief="flat", cursor="hand2")
        offset_inc_btn.pack(side="left", padx=2)

        # --- Pygame Setup (延迟到后台线程初始化，避免阻塞UI) ---
        self._pygame_initialized = False
        self.is_playing = False
        self.current_playlist_songs = []
        self.original_playlist_order = []
        self.current_song_idx = -1
        self.current_lyrics = []  # List of (time_ms, text)
        self.lyrics_update_job = None
        self.lyrics_offsets = self.config.get('lyrics_offsets', {})
        self.current_track_duration = 0

        # 延遲初始化 Pygame，確保 UI 完全載入後才執行（避免啟動時阻塞）
        self.root.after(1000, self._init_pygame_async)

        # 3. Statistics Tab Content
        self._create_stats_tab()

        # 4. Statistics - 已移到统计资料分頁
        # (原资料库统计区域已移除，统一在统计资料分頁显示)

        # 底部固定区域（始终可见）
        # 5. Log Section (Fixed at bottom) - Dark theme
        self.log_frame = tk.LabelFrame(self.tab_library, text=_('log_title'),
                                       font=get_font(11, bold=True),
                                       fg=COLORS['text'], bg=COLORS['surface'],
                                       highlightbackground=COLORS['border'],
                                       highlightthickness=1, bd=0, height=180)
        self.log_frame.pack(side="bottom", fill="x", padx=12, pady=(0, 8))
        self.log_frame.pack_propagate(False)  # 固定高度

        # Log with increased height
        self.log_text = scrolledtext.ScrolledText(self.log_frame, state='disabled',
                                                  bg=COLORS['elevated'],
                                                  fg=COLORS['text_secondary'],
                                                  font=(FONT_MONO, 10),
                                                  height=10,
                                                  relief="flat",
                                                  highlightthickness=1,
                                                  highlightbackground=COLORS['border'])
        self.log_text.pack(fill="both", expand=True, padx=8, pady=8)

        # 6. Progress Bar (Fixed above buttons) - Dark theme
        progress_container = tk.Frame(self.tab_library, bg=COLORS['bg'])
        progress_container.pack(side="bottom", fill="x", padx=12, pady=(0, 4))

        progress_frame = tk.Frame(progress_container, bg=COLORS['bg'])
        progress_frame.pack(fill="x")

        self.task_progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.task_progress_var, maximum=100,
                                           style='Dark.Horizontal.TProgressbar')
        self.progress_bar.pack(side="left", fill="x", expand=True)

        self.progress_label = tk.Label(progress_frame, text="",
                                       font=get_font(10, mono=True),
                                       fg=COLORS['accent'], bg=COLORS['bg'],
                                       anchor="e", width=12)
        self.progress_label.pack(side="right", padx=8)

        # Speed Display
        speed_frame = tk.Frame(progress_container, bg=COLORS['bg'])
        speed_frame.pack(fill="x")

        self.speed_label = tk.Label(speed_frame, text=_('speed_ready'),
                                    font=get_font(10),
                                    fg=COLORS['text_secondary'], bg=COLORS['bg'],
                                    anchor="w")
        self.speed_label.pack(fill="x")

        # 7. Action buttons (Fixed at very bottom)
        self.action_frame = tk.LabelFrame(self.tab_library, text=_('step_2_title'),
                                          font=get_font(11, bold=True),
                                          fg=COLORS['text'], bg=COLORS['surface'],
                                          highlightbackground=COLORS['border'],
                                          highlightthickness=1, bd=0)
        self.action_frame.pack(side="bottom", fill="x", padx=12, pady=(0, 8))

        self._create_action_buttons()

    def _set_initial_playlist_split(self):
        """Set an initial split that gives the playlist list more room."""
        # Delay setting the sash position until the inner tab is visible
        self.root.after(100, self._do_set_playlist_split)

    def _do_set_playlist_split(self):
        """Actually set the playlist panel split position."""
        try:
            # Make sure we're on the playlist tab and it's rendered
            self.inner_notebook.select(self.inner_tab_playlists)
            self.inner_tab_playlists.update_idletasks()
            self.list_paned.update_idletasks()
            self.list_paned.sash_place(0, 550, 0)
        except Exception:
            pass

    def log(self, message, immediate=False):
        from utils.logger import log_to_file

        # Filter log messages - only show errors and important messages
        msg_str = str(message)
        msg_lower = msg_str.lower()
        is_error = any(keyword in msg_lower for keyword in ['error', 'failed', 'critical', 'warning', 'missing'])
        is_important = any(keyword in msg_str for keyword in ['---', '->'])

        # Always write to log file (if enabled)
        level = 'ERROR' if is_error else 'INFO'
        log_to_file(msg_str, level)

        # Don't interfere with player panel - keep it for lyrics only

        if is_error or is_important:
            self.log_queue.append(msg_str)
            # Only schedule update if log_text is initialized
            if self.log_update_job is None and hasattr(self, 'log_text') and self.log_text is not None:
                # For important progress messages, use shorter delay
                delay = 50 if immediate and ("left" in msg_lower or "progress" in msg_lower) else 200
                self.log_update_job = self.root.after(delay, self._process_log_queue)

    def update_song_status(self, song_index, status, song_name):
        """Update song status in the treeview"""
        from utils.config import debug_print
        def update_ui():
            try:
                debug_print(f"[DEBUG UI] 更新歌曲狀態: index={song_index}, status={status}, name={song_name[:20]}")
                debug_print(f"[DEBUG UI] 現有項目數: {len(self.song_status_data)}")
                # Update or add song in treeview
                if song_index in self.song_status_data:
                    item = self.song_status_data[song_index]
                    self.song_status_tree.item(item, values=(status, song_name))
                    debug_print(f"[DEBUG UI] 更新現有項目: {item}")
                else:
                    item = self.song_status_tree.insert('', 'end', text=str(song_index + 1), values=(status, song_name))
                    self.song_status_data[song_index] = item
                    debug_print(f"[DEBUG UI] 新增項目: {item}")
            except Exception as e:
                debug_print(f"[DEBUG UI] Error updating song status: {e}")

        # Schedule UI update from main thread
        self.root.after(0, update_ui)

    def clear_song_status(self):
        """Clear all song status data"""
        def clear_ui():
            for item in self.song_status_tree.get_children():
                self.song_status_tree.delete(item)
            self.song_status_data.clear()
        
        self.root.after(0, clear_ui)

    def update_progress(self, current, total, eta=None):
        now = time.time()
        if now - self.last_progress_update < 0.1 and current is not None and total is not None and current < total: # Throttle, but always show final update
            return
        self.last_progress_update = now

        # Validate current and total parameters first
        try:
            current_val = float(current) if current is not None else 0.0
            total_val = float(total) if total is not None else 0.0
        except (ValueError, TypeError):
            current_val = 0.0
            total_val = 0.0
        
        # Ensure reasonable values
        if current_val < 0:
            current_val = 0.0
        if total_val <= 0:
            total_val = 0.0
        if current_val > total_val and total_val > 0:
            current_val = total_val

        self.pending_progress = (current_val, total_val, eta)
        if self.progress_update_job is None:
            self.progress_update_job = self.root.after(0, self._apply_pending_progress)

    def _apply_pending_progress(self):
        self.progress_update_job = None
        if not self.pending_progress:
            return

        current_val, total_val, eta = self.pending_progress
        self.pending_progress = None

        if total_val > 0:
            pct = (current_val / total_val) * 100
            self.task_progress_var.set(pct)
            
            # Format progress text with ETA
            progress_text = f"{int(round(current_val))}/{int(round(total_val))}"
            
            # Ensure eta is numeric before comparison
            try:
                eta_numeric = float(eta) if eta else 0
            except (ValueError, TypeError):
                eta_numeric = 0
            
            if eta_numeric > 0 and current_val < total_val:
                eta_seconds = eta_numeric
                eta_min = int(eta_seconds // 60)
                eta_sec = int(eta_seconds % 60)
                if eta_min > 0:
                    progress_text += f" ({eta_min}:{eta_sec:02d})"
                else:
                    progress_text += f" ({eta_sec}s)"
            elif current_val >= total_val and total_val > 0:
                progress_text += f" {_('progress_done')}"
            
            self.progress_label.config(text=progress_text)
            
            # Update speed label with ETA when available
            if eta_numeric > 0 and current_val < total_val:
                eta_seconds = eta_numeric
                eta_min = int(eta_seconds // 60)
                eta_sec = int(eta_seconds % 60)
                if eta_min > 0:
                    eta_text = f"{_('speed_eta_prefix')} {eta_min}:{eta_sec:02d}"
                else:
                    eta_text = f"{_('speed_eta_prefix')} {eta_sec}s"
                self.speed_label.config(text=eta_text)
            elif current_val >= total_val:
                self.speed_label.config(text=_('speed_done'))
            elif current_val == 0:
                # Starting state - show task info
                self.speed_label.config(text=_('speed_starting', total_val))
            else:
                self.speed_label.config(text=_('speed_ready'))
        else:
            self.task_progress_var.set(0)
            self.progress_label.config(text="")
            self.speed_label.config(text=_('speed_ready'))
    
    def update_speed_display(self, speed_text):
        now = time.time()
        if now - self.last_speed_update < 0.5: # Throttle to 2fps
            return
        self.last_speed_update = now
        # Only update speed display if not showing ETA or completion
        current_text = self.speed_label.cget("text")
        if (not current_text.startswith(_('speed_eta_prefix')) and 
            current_text != _('speed_done') and
            not current_text.startswith(_('speed_starting_prefix'))):
            self.root.after(0, lambda: self.speed_label.config(text=_('speed_value', speed_text)))

    def _process_log_queue(self):
        self.log_update_job = None
        if not self.log_queue:
            return
        
        # Safety check: ensure log_text is initialized
        if not hasattr(self, 'log_text') or self.log_text is None:
            return

        self.log_text.config(state='normal')
        # Batch insert
        messages = "\n".join(self.log_queue) + "\n"
        self.log_text.insert(tk.END, messages)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.log_queue.clear()



    def update_ui_text(self):
        self.root.title(_('app_title'))
        self.header_lbl.config(text=f"🎵 {_('app_title')}")
        self.url_frame.config(text=_('step_1_title'))
        self.add_btn.config(text=_('add_url_btn'))
        self.remove_btn.config(text=_('remove_url_btn'))
        self.reset_btn.config(text=_('reset_status_btn'))
        self.view_songs_btn.config(text=_('view_songs_btn'))
        self.action_frame.config(text=_('step_2_title'))
        self.update_btn.config(text=_('update_all_btn'))
        self.pause_btn.config(text=_('pause_btn') if self.pause_event.is_set() else _('resume_btn'))
        self.cancel_btn.config(text=_('cancel_btn'))
        self.export_btn.config(text=_('export_usb_btn'))
        self.stats_frame.config(text=_('stats_title'))
        self.log_frame.config(text=_('log_title'))
        self.settings_btn.config(text=_('settings_btn'))
        self.song_status_frame.config(text=_('song_status_title'))
        self.vol_lbl.config(text=_('player_volume', int(self.vol_var.get())))
        # Update song status treeview headers
        self.song_status_tree.heading('#0', text=_('song_status_no'))
        self.song_status_tree.heading('Status', text=_('song_status_status'))
        self.song_status_tree.heading('Song', text=_('song_status_song'))

    def _is_zh(self):
        return self.config.get('language', 'zh-TW') == 'zh-TW'

    def _format_time(self, seconds):
        try:
            total_seconds = max(0, int(seconds))
        except (TypeError, ValueError):
            total_seconds = 0
        minutes, secs = divmod(total_seconds, 60)
        return f"{minutes}:{secs:02d}"

    def _playlist_loaded_text(self, playlist_name):
        if self._is_zh():
            return f"\u5df2\u8f09\u5165\u64ad\u653e\u6e05\u55ae\uff1a{playlist_name}"
        return f"Loaded Playlist: {playlist_name}"

    def _playlist_loaded_songs_text(self, count):
        if self._is_zh():
            return f"\u5df2\u8f09\u5165 {count} \u9996\u6b4c\u66f2"
        return f"{count} songs loaded"

    def _resolve_lyrics_path(self, song_path):
        from utils.config import get_lyrics_file_path, get_legacy_lyrics_file_path
        new_path = get_lyrics_file_path(self.config, song_path)
        if os.path.exists(new_path):
            return new_path
        legacy_path = get_legacy_lyrics_file_path(song_path)
        if os.path.exists(legacy_path):
            return legacy_path
        return new_path

    def _get_track_duration_seconds(self, song_path):
        duration = 0
        try:
            from mutagen import File as MutagenFile
            audio = MutagenFile(song_path)
            if audio and getattr(audio, 'info', None) and getattr(audio.info, 'length', None):
                duration = int(round(audio.info.length))
        except Exception:
            duration = 0

        if duration <= 0:
            try:
                import pygame
                duration = int(round(pygame.mixer.Sound(song_path).get_length()))
            except Exception:
                duration = 0

        return duration

    def refresh_url_list(self, audio_cache=None):
        """刷新 URL 列表 - 同步版本（会阻塞UI，适合小数据量）"""
        # 异步版本，立即返回，在后台执行
        threading.Thread(target=self._async_refresh_url_list, daemon=True).start()
            
    def load_selected_playlist(self):
        selected = self.player_playlist_combo.get()
        if selected:
            self.load_playlist_into_player(selected)
        else:
            messagebox.showwarning("提示", "請先選擇一個播放清單")

    def load_playlist_into_player(self, playlist_name):
        """Load a playlist into the player with proper URL decoding"""
        import urllib.parse
        
        playlists_path = self.config.get('playlists_path', '')
        playlist_file = None
        
        # Find playlist file
        for ext in ['.m3u8', '.m3u']:
            candidate = os.path.join(playlists_path, f"{playlist_name}{ext}")
            if os.path.exists(candidate):
                playlist_file = candidate
                break
        
        if not playlist_file:
            self.log(f"-> 找不到播放清單檔案: {playlist_name}")
            return
        
        # Load songs from playlist
        songs = []
        try:
            with open(playlist_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # This is a file path - decode URL encoding
                    if line.endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm')):
                        # Decode URL-encoded path (e.g., %20 -> space, %E6%98%9F -> 星)
                        decoded_path = urllib.parse.unquote(line)
                        
                        # Convert relative path to absolute path
                        if decoded_path.startswith('../'):
                            # Relative to playlists folder
                            abs_path = os.path.normpath(os.path.join(playlists_path, decoded_path))
                        elif decoded_path.startswith('./'):
                            abs_path = os.path.normpath(os.path.join(playlists_path, decoded_path))
                        else:
                            abs_path = os.path.normpath(decoded_path)
                        
                        # Check if file exists
                        if os.path.exists(abs_path):
                            songs.append(abs_path)
                        else:
                            # Try the original encoded path as fallback
                            if os.path.exists(line):
                                songs.append(line)
                            else:
                                # Try with just filename
                                base_name = os.path.basename(decoded_path)
                                library_path = self.config.get('library_path', '')
                                alt_path = os.path.join(library_path, base_name)
                                if os.path.exists(alt_path):
                                    songs.append(alt_path)
        except Exception as e:
            self.log(f"-> 載入播放清單失敗: {e}")
            return
        
        if songs:
            self.current_playlist_songs = songs
            self.original_playlist_order = list(songs)
            self.current_song_idx = 0
            self.song_title_lbl.config(text=self._playlist_loaded_text(playlist_name))
            self.song_artist_lbl.config(text=self._playlist_loaded_songs_text(len(songs)))
            self.log(f"-> 已載入 {len(songs)} 首歌曲到播放器")
            
            # Auto-start playing first song
            self.play_song(songs[0])
        else:
            self.log(f"-> 播放清單中沒有可播放的歌曲")

    def reset_update_status(self):
        self.config['last_updated'] = {}
        from utils.config import save_config
        save_config(self.config)

    def view_playlist_songs(self):
        """Open a window showing all songs in the selected playlist"""
        selection = self.pl_listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "請先選擇一個播放清單")
            return
        
        index = selection[0]
        if index >= len(self.pl_urls):
            messagebox.showwarning("提示", "無效的選擇")
            return
        
        url = self.pl_urls[index]
        url_names = self.config.get('url_names', {})
        
        # Get playlist name
        if url.startswith("local:"):
            playlist_name = url[6:]
        else:
            playlist_name = url_names.get(url, url)
        
        # Find playlist file
        playlists_path = self.config.get('playlists_path', '')
        playlist_file = None
        for ext in ['.m3u8', '.m3u', '.txt']:
            candidate = os.path.join(playlists_path, f"{playlist_name}{ext}")
            if os.path.exists(candidate):
                playlist_file = candidate
                break
        
        # Create window
        win = tk.Toplevel(self.root)
        win.title(f"歌曲列表 - {playlist_name}")
        win.geometry("500x650")
        win.transient(self.root)
        
        # Title label
        tk.Label(win, text=f"📀 {playlist_name}", font=("Microsoft JhengHei", 14, "bold")).pack(pady=10)
        
        # Fetch method info
        fetch_method = self.config.get('spotify_fetch_method', 'embed')
        has_client_id = bool(self.config.get('spotify_client_id'))
        
        method_text = {
            'embed': '📄 Embed 頁面抓取（無需登入）',
            'api': '🔐 OAuth 使用者授權（登入 Spotify）',
            'auto': '⚡ 自動選擇'
        }.get(fetch_method, f'📄 {fetch_method}')
        
        if fetch_method == 'auto':
            actual_method = 'api' if has_client_id else 'embed'
            method_detail = 'OAuth 登入' if has_client_id else 'Embed 頁面'
            method_text += f" → 使用 {method_detail}"
        
        tk.Label(win, text=f"取得方式: {method_text}", font=("Microsoft JhengHei", 9), fg="#666666").pack()
        
        # Last updated info
        last_updated = self.config.get('last_updated', {})
        if url in last_updated:
            tk.Label(win, text=f"上次同步: {last_updated[url]}", font=("Microsoft JhengHei", 9), fg="#666666").pack(pady=(0, 5))
        
        # Song count label
        self.song_count_lbl = tk.Label(win, text="載入中...", font=("Microsoft JhengHei", 10))
        self.song_count_lbl.pack()
        
        # Listbox with scrollbar
        frame = tk.Frame(win)
        frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        scrollbar = tk.Scrollbar(frame)
        scrollbar.pack(side="right", fill="y")
        
        song_listbox = tk.Listbox(frame, font=("Microsoft JhengHei", 10), yscrollcommand=scrollbar.set)
        song_listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=song_listbox.yview)
        
        songs = []
        if playlist_file and os.path.exists(playlist_file):
            try:
                with open(playlist_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        # Skip empty lines and comments
                        if not line or line.startswith('#'):
                            # Parse #EXTINF for song name
                            if line.startswith('#EXTINF:'):
                                if ',' in line:
                                    song_name = line.split(',', 1)[1]
                                    songs.append(song_name)
                            continue
                        # Skip file paths
                        if not line.endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm')):
                            if line and not line.startswith('http'):
                                songs.append(line)
            except Exception as e:
                self.log(f"讀取播放清單失敗: {e}")
        
        # If no songs parsed from file, try debug file or show message
        if not songs:
            debug_file = os.path.join(playlists_path, '_spotify_debug.txt')
            if os.path.exists(debug_file):
                try:
                    with open(debug_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith('#'):
                                # Remove numbering like "1. "
                                if '. ' in line[:5]:
                                    parts = line.split('. ', 1)
                                    if len(parts) == 2 and parts[0].isdigit():
                                        line = parts[1]
                                songs.append(line)
                except Exception as e:
                    self.log(f"讀取 debug 檔案失敗: {e}")
        
        # Update listbox
        for song in songs:
            song_listbox.insert(tk.END, song)
        
        # Update count label
        self.song_count_lbl.config(text=f"共 {len(songs)} 首歌曲")
        
        # Close button
        tk.Button(win, text="關閉", command=win.destroy, width=10).pack(pady=10)

    def _create_stats_tab(self):
        """Create the Statistics tab content with dark theme"""
        stats_container = tk.Frame(self.tab_stats, padx=20, pady=20, bg=COLORS['bg'])
        stats_container.pack(fill="both", expand=True)

        # Title
        tk.Label(stats_container, text="📊 統計資料", font=get_font(16, bold=True),
                 fg=COLORS['text'], bg=COLORS['bg']).pack(anchor="w", pady=(0, 20))

        # Library Statistics Section
        lib_frame = tk.LabelFrame(stats_container, text="音樂庫統計", font=get_font(11, bold=True),
                                  padx=15, pady=10, bg=COLORS['surface'], fg=COLORS['text'],
                                  highlightbackground=COLORS['border'], highlightthickness=1, bd=0)
        lib_frame.pack(fill="x", pady=(0, 15))

        self.stats_tab_total_lbl = tk.Label(lib_frame, text="歌曲總數: 載入中...", font=get_font(11),
                                            fg=COLORS['text'], bg=COLORS['surface'])
        self.stats_tab_total_lbl.pack(anchor="w", pady=2)

        # 歌曲格式分布（依唯一歌曲計算，不是檔案數）
        self.stats_tab_song_format_lbl = tk.Label(lib_frame, text="  ├ 純MP3: 載入中...", font=get_font(10),
                                                  fg=COLORS['text_secondary'], bg=COLORS['surface'])
        self.stats_tab_song_format_lbl.pack(anchor="w", pady=(2, 0), padx=(10, 0))

        self.stats_tab_unconverted_lbl = tk.Label(lib_frame, text="  ├ 純M4A: 載入中...", font=get_font(10),
                                                    fg=COLORS['accent'], bg=COLORS['surface'])
        self.stats_tab_unconverted_lbl.pack(anchor="w", pady=0, padx=(10, 0))

        self.stats_tab_dual_format_lbl = tk.Label(lib_frame, text="  └ 雙格式: 載入中...", font=get_font(10),
                                                    fg=COLORS['text_secondary'], bg=COLORS['surface'])
        self.stats_tab_dual_format_lbl.pack(anchor="w", pady=(0, 2), padx=(10, 0))

        # 檔案統計（實際檔案數量）
        self.stats_tab_files_lbl = tk.Label(lib_frame, text="檔案統計: 載入中...", font=get_font(11),
                                            fg=COLORS['text'], bg=COLORS['surface'])
        self.stats_tab_files_lbl.pack(anchor="w", pady=(8, 2))

        self.stats_tab_file_breakdown_lbl = tk.Label(lib_frame, text="  MP3: 載入中... | M4A: 載入中...", font=get_font(10),
                                                       fg=COLORS['text_secondary'], bg=COLORS['surface'])
        self.stats_tab_file_breakdown_lbl.pack(anchor="w", pady=0, padx=(10, 0))

        self.stats_tab_size_lbl = tk.Label(lib_frame, text="總容量: 載入中...", font=get_font(11),
                                           fg=COLORS['text'], bg=COLORS['surface'])
        self.stats_tab_size_lbl.pack(anchor="w", pady=(8, 2))

        # Playlist Statistics Section
        pl_frame = tk.LabelFrame(stats_container, text="播放清單統計", font=get_font(11, bold=True),
                                 padx=15, pady=10, bg=COLORS['surface'], fg=COLORS['text'],
                                 highlightbackground=COLORS['border'], highlightthickness=1, bd=0)
        pl_frame.pack(fill="x", pady=(0, 15))

        self.stats_tab_pl_count_lbl = tk.Label(pl_frame, text="清單數量: 載入中...", font=get_font(11),
                                               fg=COLORS['text'], bg=COLORS['surface'])
        self.stats_tab_pl_count_lbl.pack(anchor="w", pady=2)

        self.stats_tab_pl_songs_lbl = tk.Label(pl_frame, text="清單歌曲總數: 載入中...", font=get_font(11),
                                               fg=COLORS['text_secondary'], bg=COLORS['surface'])
        self.stats_tab_pl_songs_lbl.pack(anchor="w", pady=2)

        self.stats_tab_unique_pl_lbl = tk.Label(pl_frame, text="清單唯一歌曲: 載入中...", font=get_font(11),
                                                fg=COLORS['text_secondary'], bg=COLORS['surface'])
        self.stats_tab_unique_pl_lbl.pack(anchor="w", pady=2)

        # Savings Section
        savings_frame = tk.LabelFrame(stats_container, text="空間統計", font=get_font(11, bold=True),
                                      padx=15, pady=10, bg=COLORS['surface'], fg=COLORS['text'],
                                      highlightbackground=COLORS['border'], highlightthickness=1, bd=0)
        savings_frame.pack(fill="x", pady=(0, 15))

        self.stats_tab_savings_lbl = tk.Label(savings_frame, text="重複歌曲節省空間: 載入中...", font=get_font(11),
                                              fg=COLORS['accent'], bg=COLORS['surface'])
        self.stats_tab_savings_lbl.pack(anchor="w", pady=2)

        self.stats_tab_not_in_pl_lbl = tk.Label(savings_frame, text="未收錄在清單的歌曲: 載入中...", font=get_font(11),
                                                fg=COLORS['text_secondary'], bg=COLORS['surface'])
        self.stats_tab_not_in_pl_lbl.pack(anchor="w", pady=2)

        # Refresh Button
        self.stats_refresh_btn = tk.Button(
            stats_container,
            text="🔄 重新整理",
            command=lambda: self._refresh_stats_tab(force=True),
            font=get_font(10), bg=COLORS['accent'], fg=COLORS['bg'],
            activebackground=COLORS['accent_hover'], padx=20, pady=5,
            relief="flat", cursor="hand2"
        )
        self.stats_refresh_btn.pack(anchor="w", pady=(10, 0))

        # 標記 stats 尚未初始化，避免啟動時自動載入造成阻塞
        self._stats_initialized = False
        self._stats_loading = False
        self._stats_refresh_generation = 0

    def _refresh_stats_tab(self, force=False):
        """Refresh statistics displayed in the stats tab (改為背景執行緒計算)"""
        from core.library import get_detailed_stats

        # 如果不是強制刷新，且已經初始化過，則跳過
        if not force and getattr(self, '_stats_initialized', False):
            return
        if getattr(self, '_stats_loading', False) and not force:
            return

        self._stats_refresh_generation = getattr(self, '_stats_refresh_generation', 0) + 1
        generation = self._stats_refresh_generation
        self._stats_loading = True

        def set_loading_state():
            try:
                self.stats_refresh_btn.config(state="disabled", text="載入中...")
                self.stats_tab_total_lbl.config(text="歌曲總數: 掃描中...")
                self.stats_tab_files_lbl.config(text="檔案統計: 掃描中...")
                self.stats_tab_pl_count_lbl.config(text="清單數量: 掃描中...")
            except Exception:
                pass

        set_loading_state()

        def update_ui(stats):
            try:
                if generation != getattr(self, '_stats_refresh_generation', 0):
                    return
                self._stats_initialized = True
                self._stats_loading = False

                # Library stats
                total_size_gb = stats['total_size_mb'] / 1024
                size_str = f"{total_size_gb:.2f} GB" if total_size_gb >= 1 else f"{stats['total_size_mb']:.1f} MB"

                # 歌曲統計（唯一歌曲數，不是檔案數）
                self.stats_tab_total_lbl.config(text=f"歌曲總數: {stats['total_songs']} 首（唯一）")

                # 歌曲格式分布 - 純MP3、純M4A（未轉換）、雙格式
                mp3_only = stats.get('mp3_only_count', 0)
                m4a_only = stats.get('m4a_only_count', 0)
                dual_format = stats.get('dual_format_count', 0)

                self.stats_tab_song_format_lbl.config(text=f"  ├ 純 MP3: {mp3_only} 首")

                # 純 M4A 格式統計（不表示轉換狀態）
                self.stats_tab_unconverted_lbl.config(
                    text=f"  ├ 純 M4A: {m4a_only} 首",
                    fg=COLORS['text_secondary'] if 'text_secondary' in COLORS else COLORS['text']
                )

                self.stats_tab_dual_format_lbl.config(text=f"  └ 雙格式: {dual_format} 首（同時有MP3和M4A）")

                # 檔案統計（與歌曲統計保持一致）
                expected_mp3_files = mp3_only + dual_format
                expected_m4a_files = m4a_only + dual_format
                total_files = expected_mp3_files + expected_m4a_files
                
                self.stats_tab_files_lbl.config(text=f"檔案統計: {total_files} 個檔案")
                self.stats_tab_file_breakdown_lbl.config(
                    text=f"  MP3: {expected_mp3_files} 個 | M4A: {expected_m4a_files} 個"
                )

                # 容量統計
                self.stats_tab_size_lbl.config(text=f"總容量: {size_str}")

                # Playlist stats
                pl_files = stats.get('playlist_file_count', 0)
                self.stats_tab_pl_count_lbl.config(text=f"清單數量: {pl_files} 個")
                self.stats_tab_pl_songs_lbl.config(text=f"清單歌曲總數: {stats['total_playlist_entries']} 首")
                self.stats_tab_unique_pl_lbl.config(text=f"清單唯一歌曲: {stats['unique_playlist_entries']} 首")

                # Savings stats
                savings_gb = stats['savings_mb'] / 1024
                savings_str = f"{savings_gb:.2f} GB" if savings_gb >= 1 else f"{stats['savings_mb']:.1f} MB"
                self.stats_tab_savings_lbl.config(text=f"重複歌曲節省空間: {savings_str}")
                self.stats_tab_not_in_pl_lbl.config(text=f"未收錄在清單的歌曲: {stats['not_in_playlists_count']} 首")
                self.stats_refresh_btn.config(state="normal", text="🔄 重新整理")

            except Exception as e:
                print(f"Error refreshing stats tab: {e}")
                self._stats_loading = False
                self._stats_initialized = True  # 標記為已初始化，避免卡住
                try:
                    self.stats_refresh_btn.config(state="normal", text="🔄 重新整理")
                except Exception:
                    pass

        def update_error(message):
            if generation != getattr(self, '_stats_refresh_generation', 0):
                return
            self._stats_loading = False
            self._stats_initialized = True
            self.stats_tab_total_lbl.config(text="歌曲總數: 載入失敗")
            self.stats_tab_files_lbl.config(text=f"檔案統計: {message}")
            self.stats_refresh_btn.config(state="normal", text="🔄 重新整理")

        def thread_update():
            try:
                # 統計頁在背景執行緒用 metadata 匹配 MP3/M4A，
                # 才能正確顯示已轉檔但檔名不同的歌曲。
                stats = get_detailed_stats(
                    self.config,
                    None,
                    use_cache=not force,
                    include_metadata_format=True
                )
                # 完成後再更新 UI（在主執行緒）
                self.root.after(0, lambda s=stats: update_ui(s))
            except Exception as e:
                print(f"Error computing stats: {e}")
                self.root.after(0, lambda msg=str(e): update_error(msg))

        threading.Thread(target=thread_update, daemon=True).start()

    def update_stats_ui(self, audio_cache=None, force=False):
        """更新统计资料分頁（改為延遲載入，只在需要時刷新）"""
        # 啟動時不自動刷新，避免阻塞 UI
        if not force and getattr(self, '_stats_initialized', False):
            return

        def _bg_update():
            try:
                # 使用更長的延遲確保 UI 已完全載入
                self.root.after(1000, lambda f=force: self._refresh_stats_tab(f))
            except Exception as e:
                print(f"Error triggering stats refresh: {e}")

        threading.Thread(target=_bg_update, daemon=True).start()

    def _on_tab_changed(self, event=None):
        """處理頁面切換事件，首次切換到統計頁面時載入數據"""
        try:
            # 取得當前選中的頁面索引
            current_tab = self.notebook.index(self.notebook.select())
            # 取得統計頁面的索引（第3個頁面，索引為2）
            stats_tab_idx = 2  # Library=0, Player=1, Statistics=2

            if current_tab == stats_tab_idx and not self._stats_tab_loaded:
                self._stats_tab_loaded = True
                # 延遲載入統計數據，確保頁面切換流暢
                self.root.after(100, lambda: self._refresh_stats_tab(force=False))
        except Exception as e:
            print(f"Tab change error: {e}")

    def add_url(self):
        url = self.url_entry.get().strip()
        if not url: return
        
        # 1. Normalize and check ID collision
        if "playlist/" in url:
            url = url.split('?')[0]
        else:
            self.log(_('only_playlist_url'))
            return
            
        urls = self.config.get('spotify_urls', [])
        if url in urls:
            self.log(_('duplicate_name_warning', url, "")) # Minor hack: reuse warning or add new key
            return

        # 2. Fetch name and check name collision
        self.update_btn.config(state="disabled", text=_('loading'))
        
        def _check_and_add():
            from core.spotify import scrape_via_spotify_embed
            # Check if auto_sync_on_add is enabled (default: False for faster add)
            auto_sync = self.config.get('auto_sync_on_add', False)
            skip_sync = not auto_sync  # If auto_sync is False, skip the library scan
            # Use skip_sync to control whether to scan library immediately
            scrape_via_spotify_embed(self.config, None, self.log, target_urls=[url], skip_sync=skip_sync)
            name = self.config.get('url_names', {}).get(url)
            
            def _ui_final():
                if not name:
                    self.log(_('error_no_name'))
                else:
                    url_names = self.config.get('url_names', {})
                    # Check if name is already tracked by another URL
                    existing_url = next((u for u, n in url_names.items() if n == name), None)

                    if existing_url and existing_url != url:
                        self.log(_('duplicate_name_warning', name, existing_url))
                        if not messagebox.askyesno(_('duplicate_confirm_title'), _('duplicate_confirm_msg', name)):
                            if url in url_names:
                                del url_names[url]
                                self.config['url_names'] = url_names
                                from utils.config import save_config
                                save_config(self.config)
                            self.update_btn.config(state="normal", text=_('update_all_btn'), bg="#d0f0c0")
                            return

                    urls.append(url)
                    url_names[url] = name
                    self.config['spotify_urls'] = urls
                    self.config['url_names'] = url_names
                    from utils.config import save_config
                    save_config(self.config)
                    
                    self.refresh_url_list()
                    self.url_entry.delete(0, tk.END)
                    
                    # 根據 URL 類型顯示不同的成功訊息
                    self.log(_('added_playlist', name))
                
                self.update_btn.config(state="normal", text=_('update_all_btn'), bg="#d0f0c0")

            self.root.after(0, _ui_final)

        threading.Thread(target=_check_and_add, daemon=True).start()

    def deduplicate_urls(self):
        """Removes duplicate Spotify URLs by normalizing them and keeping only the first occurrence."""
        urls = self.config.get('spotify_urls', [])
        if not urls: return
        
        new_urls = []
        seen = set()
        changed = False
        
        for url in urls:
            normalized = url
            if "playlist/" in url:
                normalized = url.split('?')[0]
            
            if normalized not in seen:
                seen.add(normalized)
                new_urls.append(normalized)
                if normalized != url:
                    changed = True
            else:
                changed = True
                
        if changed:
            self.config['spotify_urls'] = new_urls
            
            # Clean up metadata for removed/duplicate URLs
            url_names = self.config.get('url_names', {})
            last_updated = self.config.get('last_updated', {})
            
            current_keys = set(new_urls)
            for k in list(url_names.keys()):
                if k not in current_keys: del url_names[k]
            for k in list(last_updated.keys()):
                if k not in current_keys: del last_updated[k]
                
            save_config(self.config)
            self.log(_('auto_cleaned'))

    def remove_url(self):
        pl_sel = self.pl_listbox.curselection()
        if not pl_sel:
            return
        
        urls = self.config.get('spotify_urls', [])
        url_names = self.config.get('url_names', {})
        last_updated = self.config.get('last_updated', {})
        
        idx = pl_sel[0]
        url = self.pl_urls[idx]

        if url.startswith("local:"):
            name = url.split("local:", 1)[1]
            for ext in ['.m3u8', '.m3u']:
                pl_file = os.path.join(self.config['playlists_path'], f"{name}{ext}")
                if os.path.exists(pl_file):
                    try:
                        os.remove(pl_file)
                    except: pass
            
            self.refresh_url_list()
            self.update_stats_ui()
            self.log(_('removed_url', name))
            return

        if url in urls:
            # Get name before removing from url_names
            name = url_names.get(url)
            
            urls.remove(url)
            
            # Also remove name mapping if it exists
            if url in url_names:
                del url_names[url]
            
            last_updated = self.config.get('last_updated', {})
            if url in last_updated:
                del last_updated[url]
                
            self.config['spotify_urls'] = urls
            save_config(self.config)
            self.refresh_url_list()
            self.update_stats_ui()
            
            # Delete corresponding M3U/M3U8 file if it exists
            if name:
                for ext in ['.m3u8', '.m3u']:
                    pl_file = os.path.join(self.config['playlists_path'], f"{name}{ext}")
                    if os.path.exists(pl_file):
                        try:
                            os.remove(pl_file)
                        except: pass
            
            self.log(_('removed_url', url))

    def toggle_pause(self):
        if self.pause_event.is_set():
            self.pause_event.clear()
            self.pause_btn.config(text=_('resume_btn'), bg="#8BC34A")
            self.log(f"--- {_('pause_btn')} ---")
        else:
            self.pause_event.set()
            self.pause_btn.config(text=_('pause_btn'), bg="#FFEB3B")
            self.log(f"--- {_('resume_btn')} ---")

    def run_update(self):
        self.update_btn.config(state="disabled", text=_('loading'), bg="#cccccc")
        self.pause_btn.config(state="normal", text=_('pause_btn'), bg="#FFEB3B")
        self.cancel_btn.config(state="normal")
        self.pause_event.set()
        self.stop_event.clear()
        # Clear song status tree when starting new update
        self.clear_song_status()
        threading.Thread(target=self._update_thread, daemon=True).start()

    def run_cancel(self):
        if messagebox.askyesno(_('cancel_confirm_title'), _('cancel_confirm_msg')):
            self.stop_event.set()
            self.pause_event.set() # Unpause if it was paused to let it exit
            self.cancel_btn.config(state="disabled", text=_('loading'))
            self.log(_('cancelling'))

    def _update_thread(self):
        self.log(_('update_start'))
        stats = UpdateStats() # Initialize stats object
        stats.pause_event = self.pause_event 
        stats.stop_event = self.stop_event
        stats.app = self  # Add app reference for UI updates
        
        def post_dl_throttle_callback(cache):
            self.songs_since_last_refresh += 1
            now = time.time()
            # Refresh every 5 songs OR every 5 seconds, whichever comes first
            if self.songs_since_last_refresh >= 5 or (now - self.last_full_refresh > 5):
                self.root.after(0, lambda: self.refresh_url_list(cache))
                self.root.after(0, lambda: self.update_stats_ui(cache))
                self.songs_since_last_refresh = 0
                self.last_full_refresh = now

        try:
            # Create a wrapper function for immediate progress logging
            def log_with_immediate(message):
                self.log(message, immediate=True)
            
            update_library_logic(
                self.config, stats, log_with_immediate, self.update_progress,
                post_scrape_callback=lambda: self.root.after(0, self.refresh_url_list),
                post_download_callback=post_dl_throttle_callback,
                speed_display_callback=self.update_speed_display
            )
            
            # Reset counters for next run
            self.songs_since_last_refresh = 0
            self.last_full_refresh = 0
            self.root.after(0, self.show_stats_window, stats)
            if self.stop_event.is_set():
                self.log(_('task_cancelled'))
        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            self.log(_('error_critical', f"{e}\n{tb_str}"))
            
        self.log(_('update_end'))
        self.root.after(0, lambda: self.speed_label.config(text=_('speed_ready')))
        self.root.after(0, lambda: self.progress_label.config(text=""))
        self.root.after(0, lambda: self.task_progress_var.set(0))
        
        # Final refresh with updated audio cache
        def final_refresh():
            # Get fresh audio files list after download completion
            import glob
            import os
            library_path = self.config['library_path']
            search_pattern = os.path.join(library_path, "**", "*")
            all_files = glob.glob(search_pattern, recursive=True)
            audio_files_cache = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]
            
            self.refresh_url_list(audio_files_cache)
            self.update_stats_ui(audio_files_cache)
        
        self.root.after(0, final_refresh)
        
        # --- Cleanup phase (ONLY clean up confirmed temporary backups) ---
        try:
            playlists_path = self.config.get('playlists_path')
            if playlists_path and os.path.exists(playlists_path):
                # Clean up ONLY known temporary backup files
                for pattern in ['*.path_backup', '*.relative_backup']:
                    for f in glob.glob(os.path.join(playlists_path, pattern)):
                        try: os.remove(f)
                        except: pass
        except: pass

        self.root.after(0, lambda: self.update_btn.config(state="normal", text=_('update_all_btn'), bg="#d0f0c0"))
        self.root.after(0, lambda: self.pause_btn.config(state="disabled", text=_('pause_btn'), bg="#FFEB3B"))
        self.root.after(0, lambda: self.cancel_btn.config(state="disabled", text=_('cancel_btn')))

    def show_stats_window(self, stats):
        total_downloaded = len(stats.songs_downloaded)
        # Calculate total playlist changes (added + removed)
        total_added = sum(len(changes.get('added', [])) for changes in stats.playlist_changes.values())
        total_removed = sum(len(changes.get('removed', [])) for changes in stats.playlist_changes.values())

        # Show "no new songs" only if both downloaded and playlist changes are empty
        if total_downloaded == 0 and total_added == 0 and total_removed == 0:
            messagebox.showinfo(_('stats_win_title'), _('no_new_songs_downloaded'))
            return

        win = tk.Toplevel(self.root)
        win.title(_('stats_win_title'))
        win.geometry("550x450")

        txt = scrolledtext.ScrolledText(win, font=("Microsoft JhengHei", 10), wrap=tk.WORD)
        txt.pack(fill="both", expand=True, padx=10, pady=10)

        report = []
        report.append(f"=== {_('update_stats_title')} ===")
        report.append(_('stats_playlists_scanned', stats.playlists_scanned))
        # For Spotube users, show playlist-added count; for downloaders, show downloaded count
        total_new_songs = max(total_downloaded, total_added)
        report.append(_('stats_songs_downloaded', total_new_songs) + "\n")
        
        # --- Category Summary (from playlist changes, not just downloads) ---
        summary = {'華語': set(), '日語': set(), '韓語': set(), '西洋': set(), '其他': set()}

        # Use playlist_changes which tracks all added songs, not just downloaded ones
        for pl_name, changes in stats.playlist_changes.items():
            lower_pl = pl_name.lower()
            cat = '其他'
            if any(k in lower_pl for k in ['華語', '中文', 'chinese', 'mandarin']):
                cat = '華語'
            elif any(k in lower_pl for k in ['日', 'japan', 'anime', '東洋', 'j-pop']):
                cat = '日語'
            elif any(k in lower_pl for k in ['韓', 'korea', 'k-pop']):
                cat = '韓語'
            elif any(k in lower_pl for k in ['西洋', 'english', 'edm', 'western']):
                cat = '西洋'

            # Add songs from the 'added' list in playlist_changes
            for song in changes.get('added', []):
                summary[cat].add(song)

        report.append(f"--- {_('dl_summary_title')} ---")
        report.append(_('dl_summary_chinese', len(summary['華語'])))
        report.append(_('dl_summary_japanese', len(summary['日語'])))
        report.append(_('dl_summary_korean', len(summary['韓語'])))
        report.append(_('dl_summary_western', len(summary['西洋'])))
        report.append(_('dl_summary_other', len(summary['其他'])) + "\n")

        # --- Playlist Update Statistics ---
        # Combine playlist_updates (downloaded) with playlist_changes (added to playlist)
        updated_playlists = {name: songs for name, songs in stats.playlist_updates.items() if songs}
        # Also include playlists with changes (for Spotube users with existing library files)
        changed_playlists = {name: changes.get('added', []) for name, changes in stats.playlist_changes.items() if changes.get('added')}
        # Merge both sources
        all_updated = dict(updated_playlists)
        for pl_name, songs in changed_playlists.items():
            if pl_name in all_updated:
                # Combine and deduplicate
                all_updated[pl_name] = list(set(all_updated[pl_name]) | set(songs))
            else:
                all_updated[pl_name] = songs

        total_updated_playlists = len(all_updated)
        total_playlists = self.config.get('spotify_urls', [])

        report.append(f"--- {_('playlist_update_summary')} ---")
        report.append(_('playlist_update_counts', total_updated_playlists, len(total_playlists)))
        # Show playlist changes (added/removed) for Spotube users
        if total_added > 0 or total_removed > 0:
            report.append(f"  + 播放清單新增: {total_added} 首")
            report.append(f"  - 播放清單移除: {total_removed} 首")
        report.append(_('stats_songs_downloaded', total_new_songs))

        # Show detailed playlist updates (from both downloads and playlist changes)
        for pl_name, songs in sorted(all_updated.items(), key=lambda item: len(item[1]), reverse=True):
            report.append(f"  - {pl_name}: {_('stats_added_songs', len(songs))}")

        # Add detailed song list
        if all_updated:
            report.append(f"\n{_('song_list_title')}")
            for pl_name, songs in sorted(all_updated.items(), key=lambda item: len(item[1]), reverse=True):
                if songs:  # Only show playlists that have songs
                    report.append(f"{pl_name}:")
                    for song in sorted(songs):
                        report.append(f"  {song}")
                    report.append("")  # Add empty line between playlists

        txt.insert(tk.END, "\n".join(report))
        txt.config(state='disabled')

    def open_export_window(self):
        win = tk.Toplevel(self.root)
        win.title(_('export_win_title'))
        win.geometry("500x600")
        
        tk.Label(win, text=_('export_win_label')).pack(pady=5)
        
        # Quality Selection Section
        quality_frame = tk.LabelFrame(win, text=_('export_quality_label'), font=("Microsoft JhengHei", 10, "bold"), padx=10, pady=10)
        quality_frame.pack(fill='x', padx=10, pady=5)
        
        self.export_quality_var = tk.StringVar(value="original")
        tk.Radiobutton(quality_frame, text=_('export_quality_original'), variable=self.export_quality_var, value="original", font=("Microsoft JhengHei", 10)).pack(anchor="w", padx=5)
        tk.Radiobutton(quality_frame, text=_('export_quality_mp3'), variable=self.export_quality_var, value="mp3", font=("Microsoft JhengHei", 10)).pack(anchor="w", padx=5)
        tk.Radiobutton(quality_frame, text=_('export_quality_flac'), variable=self.export_quality_var, value="flac", font=("Microsoft JhengHei", 10)).pack(anchor="w", padx=5)
        
        playlists_path = self.config['playlists_path']
        files = glob.glob(os.path.join(playlists_path, "*.m3u8")) + \
                glob.glob(os.path.join(playlists_path, "*.m3u")) + \
                glob.glob(os.path.join(playlists_path, "*.txt"))
        files = [f for f in files if not is_internal_playlist_name(f)]
        
        # New: Check completeness first
        from core.library import get_playlist_completeness_report
        report = get_playlist_completeness_report(files, self.config['library_path'])

        cb_frame = tk.Frame(win)
        cb_frame.pack(fill='both', expand=True, padx=10)
        
        self.export_lb = tk.Listbox(cb_frame, selectmode=tk.MULTIPLE, font=("Microsoft JhengHei", 10))
        self.export_lb.pack(side="left", fill="both", expand=True)
        
        scrollbar = tk.Scrollbar(cb_frame)
        scrollbar.pack(side="right", fill="y")
        
        self.export_lb.config(yscrollcommand=scrollbar.set)
        scrollbar.config(command=self.export_lb.yview)
        
        self.export_files_map = {}
        self.completeness_map = {} # Map index to (is_complete, missing, total)
        for i, f in enumerate(files):
            name = os.path.basename(f)
            is_complete, missing, total = report.get(f, (True, 0, 0))
            
            display_name = name
            if not is_complete:
                display_name = f"⚠️ {name} ({_('missing_songs', missing)})"
                
            self.export_lb.insert(tk.END, display_name)
            self.export_files_map[i] = f
            self.completeness_map[i] = (is_complete, missing, total)

        # 4. Buttons Section
        btn_frame = tk.Frame(win)
        btn_frame.pack(fill='x', padx=10, pady=5)
        
        tk.Button(btn_frame, text=_('export_all'), command=lambda: self.export_lb.selection_set(0, tk.END), font=("Microsoft JhengHei", 9)).pack(side="left", padx=5)
        tk.Button(btn_frame, text=_('export_none'), command=lambda: self.export_lb.selection_clear(0, tk.END), font=("Microsoft JhengHei", 9)).pack(side="left", padx=5)
 
        btn = tk.Button(win, text=_('start_export_btn'), command=lambda: self.start_selective_export(win), bg="#ffd0d0", font=("Microsoft JhengHei", 11, "bold"))
        btn.pack(fill='x', padx=20, pady=10)
        
    def on_listbox_select(self, event):
        # Removed automatic playlist loading - user must click the Load button explicitly
        pass
        
    def start_selective_export(self, win):
        from tkinter import messagebox
        selections = self.export_lb.curselection()
        
        incompletes = []
        for i in selections:
            is_complete, missing, total = self.completeness_map[i]
            if not is_complete:
                name = os.path.basename(self.export_files_map[i])
                incompletes.append(f" - {name} ({_('missing_songs', missing)})")
        
        if incompletes:
            msg = _('incomplete_warning_msg', "\n".join(incompletes))
            if not messagebox.askyesno(_('incomplete_warning_title'), msg):
                return

        selected_files = [self.export_files_map[i] for i in selections]
        export_quality = self.export_quality_var.get()
        win.destroy()
        
        threading.Thread(target=self._export_thread_selective, args=(selected_files, export_quality), daemon=True).start()

    def _export_thread_selective(self, selected_files, export_quality):
        try:
            export_usb_logic(self.config, selected_files, export_quality, self.log, self.update_progress)
        except Exception as e:
            self.log(f"Export Error: {e}")
        finally:
            self.root.after(0, lambda: self.export_btn.config(state="normal", text=_('start_export_btn'), bg="#ffd0d0"))

    def play_song(self, song_path):
        try:
            # 确保 Pygame 已初始化
            self._ensure_pygame_init()
            import pygame
            if self.lyrics_update_job:
                self.root.after_cancel(self.lyrics_update_job)
                self.lyrics_update_job = None

            pygame.mixer.music.load(song_path)
            pygame.mixer.music.set_endevent(pygame.USEREVENT + 1)
            
            # Set volume from slider to ensure consistency
            vol = self.vol_var.get() / 100.0
            pygame.mixer.music.set_volume(vol)
            
            pygame.mixer.music.play()
            self.is_playing = True
            self.play_btn.config(text="⏸")
            self.current_playing = song_path # Track current song for lyrics offset
            self.current_track_duration = self._get_track_duration_seconds(song_path)
            self.current_time_lbl.config(text="0:00")
            self.total_time_lbl.config(text=self._format_time(self.current_track_duration))
            self.progress_slider.config(to=max(self.current_track_duration, 1))
            self.playback_progress_var.set(0)
            # Decode URL-encoded filename for display
            import urllib.parse
            display_name = urllib.parse.unquote(os.path.basename(song_path))
            self.now_playing_lbl.config(text=_('player_now_playing', display_name))
        
            # Update offset label
            current_offset = self.lyrics_offsets.get(song_path, 0.0)
            self.offset_lbl.config(text=f"偏移: {current_offset:+.1f}s")
        
            # Load and parse lyrics
            self.load_lyrics(song_path)
            self.refresh_lyrics()
        except Exception as e:
            self.log(f"Playback Error: {e}")

    def load_lyrics(self, song_path):
        self.current_lyrics = []
        lrc_path = self._resolve_lyrics_path(song_path)
        if os.path.exists(lrc_path):
            try:
                import re
                with open(lrc_path, "r", encoding="utf-8") as f:
                    for line in f:
                        # Match [mm:ss.xx] or [mm:ss:xx] or [mm:ss]
                        match = re.match(r'\[(\d+):(\d+)([:.]\d+)?\](.*)', line)
                        if match:
                            m, s, ms, text = match.groups()
                            time_ms = int(m) * 60000 + int(s) * 1000
                            if ms:
                                ms_val = ms.replace(':', '').replace('.', '')
                                if len(ms_val) == 2: time_ms += int(ms_val) * 10
                                elif len(ms_val) == 3: time_ms += int(ms_val)
                            self.current_lyrics.append((time_ms, text.strip()))
                self.current_lyrics.sort()
            except:
                pass
        
        if not self.current_lyrics:
            self.lyrics_lbl.config(text=_('player_no_lyrics'))
    
    def adjust_lyrics_offset(self, delta):
        """Adjust lyrics timing offset for current song by delta seconds"""
        if not self.current_playing:
            return
        
        # Get current offset or 0.0
        current_offset = self.lyrics_offsets.get(self.current_playing, 0.0)
        new_offset = current_offset + delta
        
        # Round to 1 decimal place
        new_offset = round(new_offset, 1)
        
        # Update offset
        self.lyrics_offsets[self.current_playing] = new_offset
        
        # Save to config
        self.config['lyrics_offsets'] = self.lyrics_offsets
        from utils.config import save_config
        save_config(self.config)
        
        # Update UI
        self.offset_lbl.config(text=f"偏移: {new_offset:+.1f}s")
        
        # Log
        self.log(f"歌詞偏移已調整: {new_offset:+.1f}s")

    def refresh_lyrics(self):
        # 如果 Pygame 未初始化，不执行任何操作
        if not self._pygame_initialized:
            return
        try:
            import pygame
        except:
            return
        # Check if song ended
        ended = False
        for event in pygame.event.get():
            if event.type == pygame.USEREVENT + 1:
                ended = True
                break

        if ended:
            self.play_next()
            return

        if not pygame.mixer.music.get_busy():
            if self.is_playing:
                # Unexpected stop or naturally ended without event caught
                self.play_next()
                return
            self.lyrics_update_job = self.root.after(500, self.refresh_lyrics)
            return

        curr_ms = pygame.mixer.music.get_pos()
        if curr_ms < 0:
            self.lyrics_update_job = self.root.after(200, self.refresh_lyrics)
            return

        current_seconds = max(0, int(curr_ms / 1000))
        self.current_time_lbl.config(text=self._format_time(current_seconds))
        if self.current_track_duration > 0:
            self.playback_progress_var.set(min(current_seconds, self.current_track_duration))
        else:
            self.playback_progress_var.set(current_seconds)
            if current_seconds > 0 and self.progress_slider.cget('to') != str(current_seconds):
                self.progress_slider.config(to=max(current_seconds, 1))
        
        # Only update lyrics if we have lyrics loaded
        if not self.current_lyrics:
            # No lyrics available - keep the "no lyrics" message
            if self.current_track_duration > 0:
                self.total_time_lbl.config(text=self._format_time(self.current_track_duration))
            self.lyrics_update_job = self.root.after(200, self.refresh_lyrics)
            return
        
        # Apply lyrics offset for current song
        offset_ms = 0
        if self.current_playing:
            offset_s = self.lyrics_offsets.get(self.current_playing, 0.0)
            offset_ms = int(offset_s * 1000)

        # Find the current line of lyrics
        current_text = ""
        adjusted_curr_ms = curr_ms + offset_ms
        for i in range(len(self.current_lyrics)):
            if self.current_lyrics[i][0] <= adjusted_curr_ms:
                current_text = self.current_lyrics[i][1]
            else:
                break
        
        if self.lyrics_lbl.cget("text") != current_text:
            self.lyrics_lbl.config(text=current_text)
            
        self.lyrics_update_job = self.root.after(200, self.refresh_lyrics)

    def toggle_playback(self):
        if not self.current_playlist_songs:
            return
        # 确保 Pygame 已初始化
        self._ensure_pygame_init()
        import pygame

        if self.is_playing:
            pygame.mixer.music.pause()
            self.is_playing = False
            self.play_btn.config(text="▶")
        else:
            pygame.mixer.music.unpause()
            self.is_playing = True
            self.play_btn.config(text="⏸")

    def play_next(self):
        if not self.current_playlist_songs: return
        
        # Check if shuffle status changed since last play
        if self.shuffle_var.get() and len(self.current_playlist_songs) > 1:
            # If shuffle is ON but matched original, randomize
            if self.current_playlist_songs == self.original_playlist_order:
                import random
                random.shuffle(self.current_playlist_songs)
                self.current_song_idx = 0
        elif not self.shuffle_var.get():
            # If shuffle is OFF but list is shuffled, restore
            if self.current_playlist_songs != self.original_playlist_order:
                current_song = self.current_playlist_songs[self.current_song_idx]
                self.current_playlist_songs = list(self.original_playlist_order)
                # Find current song in original to maintain continuity
                try:
                    self.current_song_idx = self.current_playlist_songs.index(current_song)
                except ValueError:
                    self.current_song_idx = 0

        self.current_song_idx = (self.current_song_idx + 1) % len(self.current_playlist_songs)
        self.play_song(self.current_playlist_songs[self.current_song_idx])

    def play_prev(self):
        if not self.current_playlist_songs: return
        self.current_song_idx = (self.current_song_idx - 1) % len(self.current_playlist_songs)
        self.play_song(self.current_playlist_songs[self.current_song_idx])

    def change_volume(self, val):
        # 如果 Pygame 未初始化，只更新UI标签
        if not self._pygame_initialized:
            self.vol_lbl.config(text=_('player_volume', int(float(val))))
            return
        try:
            import pygame
            vol = float(val) / 100
            pygame.mixer.music.set_volume(vol)
        except:
            pass
        self.vol_lbl.config(text=_('player_volume', int(float(val))))
