import os
import sys
import json
from tkinter import filedialog, messagebox

def get_app_dir():
    """取得應用程式的根目錄（EXE 所在目錄 或 專案根目錄）"""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        # 優先檢查 EXE 同層是否有 data 資料夾
        if os.path.exists(os.path.join(exe_dir, 'data')):
            return exe_dir
        # 如果沒有，檢查上一層目錄（處理在 dist/ 執行 EXE 的情況）
        parent_dir = os.path.dirname(exe_dir)
        if os.path.exists(os.path.join(parent_dir, 'data')):
            return parent_dir
        return exe_dir
    else:
        # 開發模式：使用 config.py 的上層目錄（專案根目錄）
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Store config in data folder for persistence (absolute path for EXE compatibility)
CONFIG_DIR = os.path.join(get_app_dir(), 'data')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

def load_config():
    config = {}
    # Ensure config directory exists
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)

    # Set defaults for missing keys
    defaults = {
        'audio_format': 'mp3',
        'language': 'zh-TW',
        'spotify_urls': [],
        'url_names': {},
        'last_updated': {},
        'enable_retroactive_lyrics': False,  # Lyrics are opt-in
        'max_threads': 4,
        'setup_completed': False,
        'retry_failed_lyrics': False,  # Default to skip failed lyrics
        'retry_failed_flac': False,  # Default to skip failed FLAC downloads
        'lyrics_offsets': {},  # Per-song lyrics timing adjustments
        'dab_use_lossless': False,
        'dab_use_metadata': False,
        'dab_email': "",
        'dab_password': "",
        'auto_metadata': False,
    }
    for key, value in defaults.items():
        config.setdefault(key, value)

    # If base_path is set, derive other paths from it
    if 'base_path' in config and config['base_path']:
        derive_paths(config)

    from utils.i18n import I18N
    I18N.set_language(config['language'])
    
    return config

def derive_paths(config):
    base_path = config['base_path']
    config['library_path'] = os.path.normpath(os.path.join(base_path, 'Music'))
    # Use subfolder for playlists as requested by user
    config['playlists_path'] = os.path.normpath(os.path.join(base_path, 'Playlists'))
    config['export_path'] = os.path.normpath(os.path.join(base_path, 'USB_Output'))
    return config

def get_data_file(filename):
    """Returns the full path for a file inside the application's data directory"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    return os.path.join(CONFIG_DIR, filename)

def prompt_and_set_base_path(config):
    from utils.i18n import _
    new_path = filedialog.askdirectory(title=_('select_base_folder'))
    if new_path:
        config['base_path'] = new_path
        derive_paths(config)
        save_config(config)
        messagebox.showinfo(_('base_folder_set_title'), _('base_folder_set_msg', new_path))
        return True
    return False

def save_config(config):
    # Ensure config directory exists
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)

def ensure_dirs(config):
    if 'base_path' not in config or not config['base_path']:
        return # Can't create dirs if base path is not set
        
    for key in ['library_path', 'playlists_path', 'export_path']:
        path = config.get(key)
        if path and isinstance(path, str):
            if not os.path.exists(path):
                os.makedirs(path)
