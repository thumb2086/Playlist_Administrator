import os
import glob
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from utils.config import load_config, save_config, ensure_dirs
from utils.i18n import I18N, _
from core.library import UpdateStats, update_library_logic, export_usb_logic, get_detailed_stats

class PlaylistApp:
    def __init__(self, root):
        self.root = root
        self.root.title(_('app_title'))
        self.root.geometry("850x930")
        
        self.config = load_config()
        ensure_dirs(self.config)
        # self.deduplicate_urls() # Removed per user preference for more manual control
        
        self.pause_event = threading.Event()
        self.pause_event.set() 
        self.stop_event = threading.Event()
        
        self.create_widgets()
        self.refresh_url_list()
        self.update_stats_ui()
        
        # Proactively fetch names on startup for URLs without names
        threading.Thread(target=self.proactive_name_fetch, daemon=True).start()

    def proactive_name_fetch(self):
        from core.spotify import get_playlist_name
        from utils.config import save_config
        
        urls = self.config.get('spotify_urls', [])
        url_names = self.config.get('url_names', {})
        
        changed = False
        for url in urls:
            if url not in url_names:
                name = get_playlist_name(url)
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
        list_container.pack(fill="x", padx=5, pady=5)
        
        self.url_listbox = tk.Listbox(list_container, height=12, font=("Microsoft JhengHei", 10))
        self.url_listbox.pack(side="left", fill="x", expand=True)
        
        url_scroll = tk.Scrollbar(list_container, orient="vertical", command=self.url_listbox.yview)
        url_scroll.pack(side="right", fill="y")
        self.url_listbox.config(yscrollcommand=url_scroll.set)

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
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.root, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill="x", padx=20, pady=5)
        
        # 3. Log Section
        self.log_frame = tk.LabelFrame(self.root, text=_('log_title'), font=("Microsoft JhengHei", 10, "bold"))
        self.log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(self.log_frame, state='disabled', bg="black", fg="white", font=("Consolas", 10))
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)

    def log(self, message):
        self.root.after(0, self._log_ui, message)

    def update_progress(self, current, total):
        if total == 0: return
        pct = (current / total) * 100
        self.progress_var.set(pct)

    def _log_ui(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, str(message) + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

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

    def refresh_url_list(self):
        self.url_listbox.delete(0, tk.END)
        url_names = self.config.get('url_names', {})
        last_updated = self.config.get('last_updated', {})
        
        import datetime
        import os
        today = datetime.datetime.now().strftime('%Y-%m-%d')
        
        from core.library import get_playlist_completeness_report
        playlists_path = self.config['playlists_path']
        library_path = self.config['library_path']
        
        urls = self.config.get('spotify_urls', [])
        pl_files = []
        for url in urls:
            name = url_names.get(url, url)
            pl_file = os.path.join(playlists_path, f"{name}.m3u")
            if os.path.exists(pl_file):
                pl_files.append(pl_file)
        
        # Batch check completeness
        report = get_playlist_completeness_report(pl_files, library_path)

        for url in urls:
            name = url_names.get(url, url)
            pl_file = os.path.join(playlists_path, f"{name}.m3u")
            
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
                if is_synced_today:
                    status_text = f"🔄 {name} ({_('synced_today')})"
                else:
                    status_text = f"⏳ {name} ({_('wait_sync')})"
            
            self.url_listbox.insert(tk.END, status_text)

    def reset_update_status(self):
        self.config['last_updated'] = {}
        from utils.config import save_config
        save_config(self.config)
        self.refresh_url_list()
        self.update_stats_ui()
        self.log(_('reset_done'))

    def update_stats_ui(self):
        def _bg_update():
            try:
                stats = get_detailed_stats(self.config)
                
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
        if "playlist/" in url:
            url = url.split('?')[0]
            
        urls = self.config.get('spotify_urls', [])
        if url in urls:
            self.log(_('duplicate_name_warning', url, "")) # Minor hack: reuse warning or add new key
            return

        # 2. Fetch name and check name collision
        self.update_btn.config(state="disabled", text=_('loading'))
        
        def _check_and_add():
            from core.spotify import get_playlist_name
            name = get_playlist_name(url)
            
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
        sel = self.url_listbox.curselection()
        if not sel: return
        idx = sel[0]
        urls = self.config.get('spotify_urls', [])
        if 0 <= idx < len(urls):
            url = urls[idx]
            urls.pop(idx)
            
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
        
        try:
            update_library_logic(
                self.config, stats, self.log, self.update_progress,
                post_scrape_callback=lambda: self.root.after(0, self.refresh_url_list),
                post_download_callback=lambda: (
                    self.root.after(0, self.refresh_url_list),
                    self.root.after(0, self.update_stats_ui)
                )
            )
            
            if not self.stop_event.is_set():
                self.root.after(0, self.show_stats_window, stats)
            else:
                self.log(_('task_cancelled'))
        except Exception as e:
            self.log(_('error_critical', e))
            
        self.log(_('update_end'))
        self.root.after(0, self.refresh_url_list)
        self.root.after(0, self.update_stats_ui)
        self.root.after(0, lambda: self.update_btn.config(state="normal", text=_('update_all_btn'), bg="#d0f0c0"))
        self.root.after(0, lambda: self.pause_btn.config(state="disabled", text=_('pause_btn'), bg="#FFEB3B"))
        self.root.after(0, lambda: self.cancel_btn.config(state="disabled", text=_('cancel_btn')))

    def show_stats_window(self, stats):
        win = tk.Toplevel(self.root)
        win.title(_('stats_win_title'))
        win.geometry("500x400")
        
        txt = scrolledtext.ScrolledText(win, font=("Microsoft JhengHei", 10))
        txt.pack(fill="both", expand=True, padx=10, pady=10)
        
        report = []
        report.append(f"=== {_('update_stats_title')} ===\n")
        report.append(_('stats_playlists_scanned', stats.playlists_scanned))
        report.append(_('stats_songs_downloaded', len(stats.songs_downloaded)) + "\n")
        
        if stats.songs_downloaded:
            report.append("--- " + _('stats_new_songs') + " ---")
            for idx, s in enumerate(stats.songs_downloaded, 1):
                report.append(f"{idx}. {s}")
            report.append("")

        if stats.playlist_changes:
            report.append("--- " + _('stats_playlist_changes') + " ---")
            for pl, change in stats.playlist_changes.items():
                added = change['added']
                removed = change['removed']
                if added or removed:
                    report.append(f"[{pl}]")
                    if added:
                        report.append(_('stats_added_songs', len(added)))
                        for s in added: report.append(f"    - {s}")
                    if removed:
                        report.append(_('stats_removed_songs', len(removed)))
                        for s in removed: report.append(f"    - {s}")
                else:
                    report.append(f"[{pl}] " + _('stats_no_change'))
        else:
              report.append(_('no_pl_files'))

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
