import os
import glob
import time
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from collections import deque
from utils.config import load_config, save_config, ensure_dirs, prompt_and_set_base_path, derive_paths
from utils.i18n import I18N, _
from core.library import UpdateStats, update_library_logic, export_usb_logic, get_detailed_stats

class PlaylistApp:
    def __init__(self, root):
        self.root = root
        self.root.title(_('app_title'))
        self.root.geometry("1100x930")
        
        self.config = load_config()

        # --- UI Throttling & Batching --- 
        self.last_progress_update = 0
        self.last_speed_update = 0
        self.log_queue = deque()
        self.log_update_job = None
        self.last_full_refresh = 0
        self.songs_since_last_refresh = 0

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
        self.refresh_url_list()
        self.update_stats_ui()
        
        # Proactively fetch names on startup for URLs without names
        threading.Thread(target=self.proactive_name_fetch, daemon=True).start()

    def proactive_name_fetch(self):
        from core.spotify import get_spotify_name
        from utils.config import save_config
        
        urls = self.config.get('spotify_urls', [])
        url_names = self.config.get('url_names', {})
        
        changed = False
        for url in urls:
            if url not in url_names:
                name = get_spotify_name(url)
                if name:
                    url_names[url] = name
                    changed = True
                    self.root.after(0, self.refresh_url_list)
        
        if changed:
            save_config(self.config)

    def create_widgets(self):
        # 0. Language Section
        lang_frame = tk.Frame(self.root)
        lang_frame.pack(fill="x", padx=10, pady=(5, 0))
        
        tk.Label(lang_frame, text="Language:").pack(side="left", padx=5)
        self.lang_var = tk.StringVar(value=self.config.get('language', 'zh-TW'))
        lang_cb = ttk.Combobox(lang_frame, textvariable=self.lang_var, values=['zh-TW', 'en'], state="readonly", width=10)
        lang_cb.pack(side="left", padx=5)
        lang_cb.bind("<<ComboboxSelected>>", self.change_language)

        # Base Path Settings Button
        self.settings_btn = tk.Button(lang_frame, text=_('set_base_folder_btn'), command=self.change_base_path, font=("Microsoft JhengHei", 9))
        self.settings_btn.pack(side="right", padx=10)

        # 1. URL Section
        self.url_frame = tk.LabelFrame(self.root, text=_('step_1_title'), font=("Microsoft JhengHei", 10, "bold"))
        self.url_frame.pack(fill="x", padx=10, pady=5)
        
        self.url_entry = tk.Entry(self.url_frame, font=("Microsoft JhengHei", 10))
        self.url_entry.pack(side="top", fill="x", padx=10, pady=5)
        
        btn_frame = tk.Frame(self.url_frame)
        btn_frame.pack(fill="x", padx=5, pady=5)
        
        self.add_btn = tk.Button(btn_frame, text=_('add_url_btn'), command=self.add_url, font=("Microsoft JhengHei", 9))
        self.add_btn.pack(side="left", padx=5)
        self.remove_btn = tk.Button(btn_frame, text=_('remove_url_btn'), command=self.remove_url, font=("Microsoft JhengHei", 9))
        self.remove_btn.pack(side="left", padx=5)
        self.reset_btn = tk.Button(btn_frame, text=_('reset_status_btn'), command=self.reset_update_status, font=("Microsoft JhengHei", 9))
        self.reset_btn.pack(side="right", padx=5)
        
        list_container = tk.Frame(self.url_frame)
        list_container.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Left side: Playlists
        pl_side = tk.Frame(list_container)
        pl_side.pack(side="left", fill="both", expand=True, padx=(0, 5))
        tk.Label(pl_side, text="歌單 (Playlists)", font=("Microsoft JhengHei", 9, "bold")).pack(anchor="w")
        
        self.pl_listbox = tk.Listbox(pl_side, height=12, font=("Microsoft JhengHei", 10), exportselection=False)
        self.pl_listbox.pack(fill="both", expand=True)
        pl_scroll = tk.Scrollbar(pl_side, orient="vertical", command=self.pl_listbox.yview)
        pl_scroll.pack(side="right", fill="y")
        self.pl_listbox.config(yscrollcommand=pl_scroll.set)

        # Middle: Albums
        al_side = tk.Frame(list_container)
        al_side.pack(side="left", fill="both", expand=True, padx=5)
        tk.Label(al_side, text="專輯 (Albums)", font=("Microsoft JhengHei", 9, "bold")).pack(anchor="w")
        
        self.al_listbox = tk.Listbox(al_side, height=12, font=("Microsoft JhengHei", 10), exportselection=False)
        self.al_listbox.pack(fill="both", expand=True)
        al_scroll = tk.Scrollbar(al_side, orient="vertical", command=self.al_listbox.yview)
        al_scroll.pack(side="right", fill="y")
        self.al_listbox.config(yscrollcommand=al_scroll.set)

        # Right side: Artists
        ar_side = tk.Frame(list_container)
        ar_side.pack(side="left", fill="both", expand=True, padx=(5, 0))
        tk.Label(ar_side, text="藝人 (Artists)", font=("Microsoft JhengHei", 9, "bold")).pack(anchor="w")

        self.ar_listbox = tk.Listbox(ar_side, height=12, font=("Microsoft JhengHei", 10), exportselection=False)
        self.ar_listbox.pack(fill="both", expand=True)
        ar_scroll = tk.Scrollbar(ar_side, orient="vertical", command=self.ar_listbox.yview)
        ar_scroll.pack(side="right", fill="y")
        self.ar_listbox.config(yscrollcommand=ar_scroll.set)

        # 2. Action Section
        self.action_frame = tk.LabelFrame(self.root, text=_('step_2_title'), font=("Microsoft JhengHei", 10, "bold"))
        self.action_frame.pack(fill="x", padx=10, pady=5)
        
        self.update_btn = tk.Button(self.action_frame, text=_('update_all_btn'), command=self.run_update, bg="#d0f0c0", height=2, font=("Microsoft JhengHei", 11, "bold"))
        self.update_btn.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        
        self.pause_btn = tk.Button(self.action_frame, text=_('pause_btn'), command=self.toggle_pause, bg="#FFEB3B", height=2, state="disabled", font=("Microsoft JhengHei", 11, "bold"))
        self.pause_btn.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        
        self.cancel_btn = tk.Button(self.action_frame, text=_('cancel_btn'), command=self.run_cancel, bg="#f44336", fg="white", height=2, state="disabled", font=("Microsoft JhengHei", 11, "bold"))
        self.cancel_btn.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        
        self.export_btn = tk.Button(self.action_frame, text=_('export_usb_btn'), command=self.open_export_window, bg="#ffd0d0", height=2, font=("Microsoft JhengHei", 11, "bold"))
        self.export_btn.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        
        # 3. Statistics Section (Fixed)
        self.stats_frame = tk.LabelFrame(self.root, text=_('stats_title'), font=("Microsoft JhengHei", 10, "bold"))
        self.stats_frame.pack(fill="x", padx=10, pady=5)
        
        stats_container = tk.Frame(self.stats_frame)
        stats_container.pack(fill="x", padx=10, pady=5)
        
        self.total_songs_lbl = tk.Label(stats_container, text=_('total_songs', _('loading'), ""), font=("Microsoft JhengHei", 10))
        self.total_songs_lbl.grid(row=0, column=0, sticky="w", padx=5)
        
        self.dup_songs_lbl = tk.Label(stats_container, text=_('duplicate_songs', _('loading')), font=("Microsoft JhengHei", 10))
        self.dup_songs_lbl.grid(row=0, column=1, sticky="w", padx=20)
        
        self.space_saved_lbl = tk.Label(stats_container, text=_('space_saved', _('loading')), font=("Microsoft JhengHei", 10), fg="#4CAF50")
        self.space_saved_lbl.grid(row=0, column=2, sticky="w", padx=20)
        
        self.recent_lbl = tk.Label(self.stats_frame, text=_('recent_added', ""), font=("Microsoft JhengHei", 9), fg="#666")
        self.recent_lbl.pack(side="top", anchor="w", padx=15, pady=(0, 5))
        
        # Progress Bar
        progress_frame = tk.Frame(self.root)
        progress_frame.pack(fill="x", padx=20, pady=5)

        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(side="left", fill="x", expand=True)
        
        self.progress_label = tk.Label(progress_frame, text="", font=("Microsoft JhengHei", 9), anchor="e", width=15)
        self.progress_label.pack(side="right", padx=5)
        
        # Speed Display
        speed_frame = tk.Frame(self.root)
        speed_frame.pack(fill="x", padx=20, pady=(0, 5))
        
        self.speed_label = tk.Label(speed_frame, text="準備就緒", font=("Microsoft JhengHei", 9), fg="#666", anchor="w")
        self.speed_label.pack(fill="x")
        
        # 3. Log Section
        self.log_frame = tk.LabelFrame(self.root, text=_('log_title'), font=("Microsoft JhengHei", 10, "bold"))
        self.log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(self.log_frame, state='disabled', bg="black", fg="white", font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

    def log(self, message, immediate=False):
        self.log_queue.append(str(message))
        if self.log_update_job is None:
            # For important progress messages, use shorter delay
            delay = 50 if immediate and ("剩" in str(message) or "left" in str(message.lower())) else 200
            self.log_update_job = self.root.after(delay, self._process_log_queue)

    def update_progress(self, current, total, eta=None):
        now = time.time()
        if now - self.last_progress_update < 0.1 and current < total: # Throttle, but always show final update
            return
        self.last_progress_update = now
        
        # Validate current and total parameters first
        try:
            current_val = int(current) if current is not None else 0
            total_val = int(total) if total is not None else 0
        except (ValueError, TypeError):
            current_val = 0
            total_val = 0
        
        # Ensure reasonable values
        if current_val < 0:
            current_val = 0
        if total_val <= 0:
            total_val = 0
        if current_val > total_val and total_val > 0:
            current_val = total_val
        
        if total_val > 0:
            pct = (current_val / total_val) * 100
            self.progress_var.set(pct)
            
            # Format progress text with ETA
            progress_text = f"{current_val}/{total_val}"
            
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
                progress_text += " ✓"
            
            self.progress_label.config(text=progress_text)
            
            # Update speed label with ETA when available
            if eta_numeric > 0 and current_val < total_val:
                eta_seconds = eta_numeric
                eta_min = int(eta_seconds // 60)
                eta_sec = int(eta_seconds % 60)
                if eta_min > 0:
                    eta_text = f"剩餘時間: {eta_min}:{eta_sec:02d}"
                else:
                    eta_text = f"剩餘時間: {eta_sec}秒"
                self.speed_label.config(text=eta_text)
            elif current_val >= total_val:
                self.speed_label.config(text="下載完成")
            elif current_val == 0:
                # Starting state - show task info
                self.speed_label.config(text=f"準備下載 {total_val} 首歌曲")
            else:
                self.speed_label.config(text="準備就緒")
        else:
            self.progress_var.set(0)
            self.progress_label.config(text="")
            self.speed_label.config(text="準備就緒")
    
    def update_speed_display(self, speed_text):
        now = time.time()
        if now - self.last_speed_update < 0.5: # Throttle to 2fps
            return
        self.last_speed_update = now
        # Only update speed display if not showing ETA
        current_text = self.speed_label.cget("text")
        if not current_text.startswith("預估時間:") and current_text != "完成":
            self.root.after(0, lambda: self.speed_label.config(text=f"下載速度: {speed_text}"))

    def _process_log_queue(self):
        self.log_update_job = None
        if not self.log_queue:
            return

        self.log_text.config(state='normal')
        # Batch insert
        messages = "\n".join(self.log_queue) + "\n"
        self.log_text.insert(tk.END, messages)
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')
        self.log_queue.clear()

    def change_base_path(self):
        if prompt_and_set_base_path(self.config):
            ensure_dirs(self.config)
            # Refresh UI that depends on paths
            self.refresh_url_list()
            self.update_stats_ui()
            self.log(_('base_folder_changed'))

    def change_language(self, event):
        new_lang = self.lang_var.get()
        self.config['language'] = new_lang
        save_config(self.config)
        I18N.set_language(new_lang)
        self.update_ui_text()
        self.refresh_url_list()
        self.update_stats_ui()

    def update_ui_text(self):
        self.root.title(_('app_title'))
        self.url_frame.config(text=_('step_1_title'))
        self.add_btn.config(text=_('add_url_btn'))
        self.remove_btn.config(text=_('remove_url_btn'))
        self.reset_btn.config(text=_('reset_status_btn'))
        self.action_frame.config(text=_('step_2_title'))
        self.update_btn.config(text=_('update_all_btn'))
        self.pause_btn.config(text=_('pause_btn') if self.pause_event.is_set() else _('resume_btn'))
        self.cancel_btn.config(text=_('cancel_btn'))
        self.export_btn.config(text=_('export_usb_btn'))
        self.stats_frame.config(text=_('stats_title'))
        self.log_frame.config(text=_('log_title'))
        self.settings_btn.config(text=_('set_base_folder_btn'))

    def refresh_url_list(self, audio_cache=None):
        self.pl_listbox.delete(0, tk.END)
        self.al_listbox.delete(0, tk.END)
        self.ar_listbox.delete(0, tk.END)
        url_names = self.config.get('url_names', {})
        last_updated = self.config.get('last_updated', {})
        
        import datetime
        import os
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        
        from core.library import get_playlist_completeness_report
        playlists_path = self.config['playlists_path']
        library_path = self.config['library_path']
        
        urls = self.config.get('spotify_urls', [])
        
        self.pl_urls = [u for u in urls if "artist/" not in u and "album/" not in u]  # 只有播放清單
        self.al_urls = [u for u in urls if "album/" in u]  # 只有專輯
        self.ar_urls = [u for u in urls if "artist/" in u]  # 只有藝人
        
        pl_files = []
        # 直接獲取所有存在的播放清單檔案，不依賴 URL 列表
        for ext in ['.m3u', '.m3u8', '.txt']:
            pl_files.extend(glob.glob(os.path.join(playlists_path, f"*{ext}")))
        
        # Batch check completeness
        report = get_playlist_completeness_report(pl_files, library_path, audio_files_cache=audio_cache)

        for url in urls:
            name = url_names.get(url, url)
            # Try both .m3u and .m3u8 extensions
            pl_file = None
            for ext in ['.m3u', '.m3u8']:
                test_file = os.path.join(playlists_path, f"{name}{ext}")
                if os.path.exists(test_file):
                    pl_file = test_file
                    break
            
            if not pl_file:
                # If no file found, skip this URL
                continue
            
            status_text = ""
            is_synced_today = last_updated.get(url) == today
            
            if os.path.exists(pl_file):
                is_complete, missing, total = report.get(pl_file, (True, 0, 0))
                
                if is_complete:
                    if is_synced_today:
                        status_text = f"✅ {name}"
                    else:
                        status_text = f"📦 {name} ({_('local_complete')})"
                else:
                    if is_synced_today:
                        status_text = f"🔄 {name} ({_('incomplete_warning_title')}, {_('missing_songs', missing)})"
                    else:
                        status_text = f"⚠️ {name} ({_('wait_download')}, {_('missing_songs', missing)})"
            else:
                # No playlist file exists - check if it's an artist that should have one
                if is_synced_today:
                    status_text = f"🔄 {name} ({_('synced_today')})"
                else:
                    status_text = f"⏳ {name} ({_('wait_sync')})"
            
            if url in self.pl_urls:
                self.pl_listbox.insert(tk.END, status_text)
            elif url in self.al_urls:
                self.al_listbox.insert(tk.END, status_text)
            else:
                self.ar_listbox.insert(tk.END, status_text)

    def reset_update_status(self):
        self.config['last_updated'] = {}
        from utils.config import save_config
        save_config(self.config)
        self.refresh_url_list()
        self.update_stats_ui()
        self.log(_('reset_done'))

    def update_stats_ui(self, audio_cache=None):
        def _bg_update():
            try:
                stats = get_detailed_stats(self.config, audio_files=audio_cache)
                
                total_songs = stats['total_songs']
                total_size_mb = stats['total_size_mb']
                dupes = stats['duplicates_count']
                savings = stats['savings_mb']
                recent = stats['recent_5']
                
                size_str = f"{total_size_mb/1024:.2f} GB" if total_size_mb > 1024 else f"{total_size_mb:.1f} MB"
                saving_str = f"{savings/1024:.2f} GB" if savings > 1024 else f"{savings:.1f} MB"
                
                self.root.after(0, lambda: self.total_songs_lbl.config(text=_('total_songs', total_songs, size_str)))
                self.root.after(0, lambda: self.dup_songs_lbl.config(text=_('duplicate_songs', dupes)))
                self.root.after(0, lambda: self.space_saved_lbl.config(text=_('space_saved', saving_str)))
                
                if recent:
                    recent_text = _('recent_added', " | ".join([f"{name[:15]}... ({date})" for name, date in recent]))
                    self.root.after(0, lambda: self.recent_lbl.config(text=recent_text))
                else:
                    self.root.after(0, lambda: self.recent_lbl.config(text=_('recent_added', _('no_data'))))
            except Exception as e:
                print(f"Error updating stats: {e}")

        threading.Thread(target=_bg_update, daemon=True).start()

    def add_url(self):
        url = self.url_entry.get().strip()
        if not url: return
        
        # 1. Normalize and check ID collision
        if "playlist/" in url or "artist/" in url or "album/" in url:
            url = url.split('?')[0]
            
        urls = self.config.get('spotify_urls', [])
        if url in urls:
            self.log(_('duplicate_name_warning', url, "")) # Minor hack: reuse warning or add new key
            return

        # 2. Fetch name and check name collision
        self.update_btn.config(state="disabled", text=_('loading'))
        
        def _check_and_add():
            from core.spotify import get_spotify_name
            name = get_spotify_name(url)
            
            def _ui_final():
                if not name:
                    self.log(_('error_no_name'))
                else:
                    url_names = self.config.get('url_names', {})
                    # Check if name is already tracked by another URL
                    existing_url = next((u for u, n in url_names.items() if n == name), None)
                    
                    if existing_url:
                        self.log(_('duplicate_name_warning', name, existing_url))
                        if not messagebox.askyesno(_('duplicate_confirm_title'), _('duplicate_confirm_msg', name)):
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
                    if "album/" in url:
                        self.log(_('added_album', name))
                    else:
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
            if "playlist/" in url or "artist/" in url or "album/" in url:
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
        al_sel = self.al_listbox.curselection()
        ar_sel = self.ar_listbox.curselection()
        
        if not pl_sel and not al_sel and not ar_sel: return
        
        urls = self.config.get('spotify_urls', [])
        url_names = self.config.get('url_names', {})
        last_updated = self.config.get('last_updated', {})
        
        if pl_sel:
            idx = pl_sel[0]
            url = self.pl_urls[idx]
        elif al_sel:
            idx = al_sel[0]
            url = self.al_urls[idx]
        else:
            idx = ar_sel[0]
            url = self.ar_urls[idx]

        if url in urls:
            urls.remove(url)
            
            # Also remove name mapping if it exists
            url_names = self.config.get('url_names', {})
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
            name = url_names.get(url)
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
        self.root.after(0, lambda: self.speed_label.config(text="準備就緒"))
        self.root.after(0, lambda: self.progress_label.config(text=""))
        
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
        
        # --- Orphaned Playlists & Backups Cleanup ---
        try:
            playlists_path = self.config['playlists_path']
            url_names = self.config.get('url_names', {})
            current_names = set(url_names.values())
            
            # Clean up orphans
            for ext in ['*.m3u8', '*.m3u']:
                for f in glob.glob(os.path.join(playlists_path, ext)):
                    name = os.path.splitext(os.path.basename(f))[0]
                    if name not in current_names:
                        try: os.remove(f)
                        except: pass
            
            # Clean up backups
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
        if total_downloaded == 0:
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
        report.append(_('stats_songs_downloaded', total_downloaded) + "\n")
        
        # --- Download Summary by Category ---
        summary = {'華語': set(), '日語': set(), '韓語': set(), '西洋': set(), '其他': set()}
        
        for pl_name, songs in stats.playlist_updates.items():
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
            
            for song in songs:
                summary[cat].add(song)

        report.append(f"--- {_('dl_summary_title')} ---")
        report.append(_('dl_summary_chinese', len(summary['華語'])))
        report.append(_('dl_summary_japanese', len(summary['日語'])))
        report.append(_('dl_summary_korean', len(summary['韓語'])))
        report.append(_('dl_summary_western', len(summary['西洋'])))
        report.append(_('dl_summary_other', len(summary['其他'])) + "\n")

        # --- Playlist Update Statistics ---
        updated_playlists = {name: songs for name, songs in stats.playlist_updates.items() if songs}
        total_updated_playlists = len(updated_playlists)
        total_playlists = self.config.get('spotify_urls', [])

        report.append(f"--- {_('playlist_update_summary')} ---")
        report.append(_('playlist_update_counts', total_updated_playlists, len(total_playlists)))
        report.append(_('stats_songs_downloaded', total_downloaded))
        
        # Show detailed playlist updates
        for pl_name, songs in sorted(updated_playlists.items(), key=lambda item: len(item[1]), reverse=True):
            report.append(f"  - {pl_name}: {_('stats_added_songs', len(songs))}")
        
        # Add detailed song list
        if updated_playlists:
            report.append(f"\n{_('song_list_title')}")
            for pl_name, songs in sorted(updated_playlists.items(), key=lambda item: len(item[1]), reverse=True):
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
        win.geometry("500x550")
        
        tk.Label(win, text=_('export_win_label')).pack(pady=5)
        
        playlists_path = self.config['playlists_path']
        files = glob.glob(os.path.join(playlists_path, "*.m3u")) + \
                glob.glob(os.path.join(playlists_path, "*.txt"))
        
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
        win.destroy()
        
        threading.Thread(target=self._export_thread_selective, args=(selected_files,), daemon=True).start()

    def _export_thread_selective(self, selected_files):
        try:
            export_usb_logic(self.config, selected_files, self.log)
        except Exception as e:
             self.log(_('export_error', e))
