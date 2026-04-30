"""
Update notification dialog for Playlist Administrator
"""

import tkinter as tk
from tkinter import ttk
import webbrowser
from utils.version_checker import format_release_notes


class UpdateDialog:
    """Dialog to notify user about available updates"""
    
    def __init__(self, parent, update_info):
        """
        Args:
            parent: Parent Tkinter widget
            update_info: Dict with keys from check_for_updates()
        """
        self.parent = parent
        self.update_info = update_info
        self.download_url = update_info.get('download_url', '')
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("新版本可用 / New Version Available")
        self.dialog.geometry("500x400")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Center dialog
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (500 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (400 // 2)
        self.dialog.geometry(f"500x400+{x}+{y}")
        
        self._create_widgets()
        
    def _create_widgets(self):
        """Create dialog widgets"""
        # Main frame with padding
        main_frame = tk.Frame(self.dialog, padx=20, pady=20)
        main_frame.pack(fill="both", expand=True)
        
        # Title
        title_label = tk.Label(
            main_frame,
            text="🎉 新版本可用！",
            font=("Microsoft JhengHei", 18, "bold"),
            fg="#2196F3"
        )
        title_label.pack(pady=(0, 10))
        
        # English subtitle
        eng_title = tk.Label(
            main_frame,
            text="New Version Available!",
            font=("Microsoft JhengHei", 12),
            fg="#666"
        )
        eng_title.pack(pady=(0, 20))
        
        # Version info
        current = self.update_info.get('current_version', 'Unknown')
        latest = self.update_info.get('latest_version', 'Unknown')
        
        version_frame = tk.Frame(main_frame)
        version_frame.pack(fill="x", pady=10)
        
        tk.Label(
            version_frame,
            text=f"目前版本 / Current: {current}",
            font=("Microsoft JhengHei", 11),
            fg="#666"
        ).pack(anchor="w")
        
        tk.Label(
            version_frame,
            text=f"最新版本 / Latest: {latest}",
            font=("Microsoft JhengHei", 11, "bold"),
            fg="#4CAF50"
        ).pack(anchor="w", pady=(5, 0))
        
        # Release notes
        notes_frame = tk.LabelFrame(
            main_frame,
            text="更新內容 / Release Notes",
            font=("Microsoft JhengHei", 10),
            padx=10,
            pady=10
        )
        notes_frame.pack(fill="both", expand=True, pady=15)
        
        notes_text = format_release_notes(self.update_info.get('release_notes', ''))
        
        notes_label = tk.Label(
            notes_frame,
            text=notes_text,
            font=("Microsoft JhengHei", 9),
            fg="#333",
            justify="left",
            wraplength=420
        )
        notes_label.pack(anchor="nw")
        
        # Buttons
        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill="x", pady=(15, 0))
        
        # Download button (primary)
        download_btn = tk.Button(
            button_frame,
            text="下載更新 / Download Update",
            font=("Microsoft JhengHei", 11, "bold"),
            bg="#2196F3",
            fg="white",
            cursor="hand2",
            command=self._open_download
        )
        download_btn.pack(side="left", padx=(0, 10))
        
        # Later button
        later_btn = tk.Button(
            button_frame,
            text="稍後提醒 / Remind Me Later",
            font=("Microsoft JhengHei", 11),
            command=self._close
        )
        later_btn.pack(side="left", padx=(0, 10))
        
        # Skip button
        skip_btn = tk.Button(
            button_frame,
            text="跳過此版本 / Skip This Version",
            font=("Microsoft JhengHei", 10),
            fg="#666",
            command=self._skip_version
        )
        skip_btn.pack(side="right")
        
    def _open_download(self):
        """Open download URL in browser"""
        if self.download_url:
            webbrowser.open(self.download_url)
        self._close()
        
    def _skip_version(self):
        """Skip this version - store in config"""
        from utils.config import load_config, save_config
        config = load_config()
        config['skipped_version'] = self.update_info.get('latest_version')
        save_config(config)
        self._close()
        
    def _close(self):
        """Close dialog"""
        self.dialog.destroy()
