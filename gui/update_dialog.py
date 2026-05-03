"""
Update notification dialog for Playlist Administrator
Dark theme design with Spotify green accent
"""

import tkinter as tk
from tkinter import ttk
import webbrowser
from utils.version_checker import format_release_notes
from utils.i18n import _


# Dark theme color system
COLORS = {
    'bg': '#121212',
    'surface': '#1e1e1e',
    'elevated': '#2a2a2a',
    'text': '#ffffff',
    'text_secondary': '#b3b3b3',
    'text_muted': '#6a6a6a',
    'border': '#2a2a2a',
    'accent': '#1DB954',  # Spotify green
    'accent_hover': '#1ed760',
    'error': '#e22134',
    'warning': '#f59b23',
}

# Fonts
FONT_FAMILY = "Noto Sans TC"
FONT_FALLBACK = "Microsoft JhengHei"


def get_font(size=10, bold=False, mono=False):
    """Get font with fallback"""
    weight = "bold" if bold else "normal"
    family = "JetBrains Mono" if mono else FONT_FAMILY
    return (family, size, weight)


class UpdateDialog:
    """Dialog to notify user about available updates - Dark Theme (Non-modal)"""

    def __init__(self, parent, update_info, on_close_callback=None):
        """
        Args:
            parent: Parent Tkinter widget
            update_info: Dict with keys from check_for_updates()
            on_close_callback: Optional callback function when dialog closes
        """
        self.parent = parent
        self.update_info = update_info
        self.download_url = update_info.get('download_url', '')
        self.on_close_callback = on_close_callback

        self.dialog = tk.Toplevel(parent)
        self.dialog.title(_('update_dialog_title'))
        self.dialog.geometry("500x420")
        self.dialog.resizable(False, False)
        # Make dialog stay on top but NOT modal (no grab_set)
        # Note: transient makes the dialog stay on top of parent but NOT block interaction
        self.dialog.transient(parent)
        self.dialog.configure(bg=COLORS['bg'])
        # Keep dialog on top so user sees it
        self.dialog.attributes('-topmost', True)

        # Handle dialog close event
        self.dialog.protocol("WM_DELETE_WINDOW", self._close)

        self._create_widgets()

        # Center and show dialog AFTER widget creation to avoid any blocking
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (500 // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (420 // 2)
        self.dialog.geometry(f"500x420+{x}+{y}")

        # Ensure dialog is visible and focused but doesn't block parent
        self.dialog.lift()
        self.dialog.focus_set()

    def _create_widgets(self):
        """Create dialog widgets with dark theme"""
        # Main frame
        main_frame = tk.Frame(self.dialog, bg=COLORS['bg'], padx=24, pady=24)
        main_frame.pack(fill="both", expand=True)

        # Title with accent color
        title_label = tk.Label(
            main_frame,
            text=_('update_dialog_title'),
            font=get_font(20, bold=True),
            fg=COLORS['accent'],
            bg=COLORS['bg']
        )
        title_label.pack(pady=(0, 4))

        # English subtitle
        eng_title = tk.Label(
            main_frame,
            text=_('update_dialog_subtitle'),
            font=get_font(12),
            fg=COLORS['text_secondary'],
            bg=COLORS['bg']
        )
        eng_title.pack(pady=(0, 20))

        # Version info card
        version_card = tk.Frame(main_frame, bg=COLORS['surface'], padx=16, pady=12)
        version_card.pack(fill="x", pady=(0, 16))

        current = self.update_info.get('current_version', 'Unknown')
        latest = self.update_info.get('latest_version', 'Unknown')

        tk.Label(
            version_card,
            text=_('update_current_version', current),
            font=get_font(11),
            fg=COLORS['text_secondary'],
            bg=COLORS['surface']
        ).pack(anchor="w")

        tk.Label(
            version_card,
            text=_('update_latest_version', latest),
            font=get_font(12, bold=True),
            fg=COLORS['accent'],
            bg=COLORS['surface']
        ).pack(anchor="w", pady=(4, 0))

        # Release notes frame
        notes_frame = tk.LabelFrame(
            main_frame,
            text=_('update_release_notes'),
            font=get_font(11, bold=True),
            fg=COLORS['text'],
            bg=COLORS['surface'],
            padx=12,
            pady=12,
            highlightbackground=COLORS['border'],
            highlightthickness=1,
            bd=0
        )
        notes_frame.pack(fill="both", expand=True, pady=(0, 16))

        notes_text = format_release_notes(self.update_info.get('release_notes', ''))
        if not notes_text or notes_text == "No release notes available.":
            notes_text = _('update_no_notes')

        notes_label = tk.Label(
            notes_frame,
            text=notes_text,
            font=get_font(10),
            fg=COLORS['text_secondary'],
            bg=COLORS['surface'],
            justify="left",
            wraplength=420
        )
        notes_label.pack(anchor="nw", fill="both", expand=True)

        # Buttons
        button_frame = tk.Frame(main_frame, bg=COLORS['bg'])
        button_frame.pack(fill="x")

        # Download button (primary - accent color)
        download_btn = tk.Button(
            button_frame,
            text=_('update_download_btn'),
            font=get_font(11, bold=True),
            bg=COLORS['accent'],
            fg=COLORS['bg'],
            activebackground=COLORS['accent_hover'],
            activeforeground=COLORS['bg'],
            cursor="hand2",
            relief="flat",
            padx=16,
            pady=8,
            command=self._open_download
        )
        download_btn.pack(side="left", padx=(0, 8))

        # Later button (secondary)
        later_btn = tk.Button(
            button_frame,
            text=_('update_later_btn'),
            font=get_font(11),
            bg=COLORS['elevated'],
            fg=COLORS['text'],
            activebackground=COLORS['surface'],
            activeforeground=COLORS['text'],
            cursor="hand2",
            relief="flat",
            padx=12,
            pady=8,
            command=self._close
        )
        later_btn.pack(side="left", padx=(0, 8))

        # Skip button (tertiary)
        skip_btn = tk.Button(
            button_frame,
            text=_('update_skip_btn'),
            font=get_font(10),
            bg=COLORS['bg'],
            fg=COLORS['text_muted'],
            activebackground=COLORS['surface'],
            activeforeground=COLORS['text_secondary'],
            cursor="hand2",
            relief="flat",
            padx=8,
            pady=8,
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
        """Close dialog and call callback if provided"""
        self.dialog.destroy()
        if self.on_close_callback:
            self.on_close_callback()
