import os
import sys
import json
import time
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

# Store app data under user profile to avoid Program Files permission issues
def get_app_data_dir():
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA')
    if base:
        new_dir = os.path.join(base, 'playlist-admin', 'data')
        legacy_dir = os.path.join(base, 'Playlist Administrator', 'data')
        # 遷移：把舊資料目錄整個複製到新目錄（只搬一次）
        if not os.path.exists(new_dir) and os.path.exists(legacy_dir):
            try:
                import shutil
                shutil.copytree(legacy_dir, new_dir, dirs_exist_ok=True)
            except Exception:
                pass
        return new_dir
    # Fallback: use app directory (may be read-only in Program Files)
    return os.path.join(get_app_dir(), 'data')
    base = os.environ.get('LOCALAPPDATA') or os.environ.get('APPDATA')
    if base:
        return os.path.join(base, 'Playlist Administrator', 'data')
    # Fallback: use app directory (may be read-only in Program Files)
    return os.path.join(get_app_dir(), 'data')

# Store config in data folder for persistence (absolute path for EXE compatibility)
_APP_DATA_DIR = get_app_data_dir()
_APP_CONFIG_FILE = os.path.join(_APP_DATA_DIR, 'config.json')

# Global variable to track currently active data directory (starts with app local)
CONFIG_DIR = _APP_DATA_DIR
CONFIG_FILE = _APP_CONFIG_FILE

def get_data_dir(config):
    """取得目前的資料儲存目錄（直接使用主資料夾，不建立 data 子目錄）"""
    if config.get('base_path'):
        # If the user selected a path ending in 'data', use its parent to avoid data/data
        # We don't strictly need to do this, but if they selected the previous 'data' dir,
        # their data will just live inside it normally. We do NOT append 'data'.
        return config['base_path']
    return _APP_DATA_DIR

def load_config():
    # 1. 先讀取 EXE 旁邊的引導設定
    config = {}
    if not os.path.exists(_APP_DATA_DIR):
        os.makedirs(_APP_DATA_DIR)
    
    if os.path.exists(_APP_CONFIG_FILE):
        with open(_APP_CONFIG_FILE, 'r', encoding='utf-8') as f:
            try:
                config = json.load(f)
            except:
                config = {}

    # 2. 如果已設定主資料夾，嘗試切換到主資料夾下的「真正的設定檔」
    if config.get('base_path'):
        primary_data_dir = config['base_path']
        primary_config_file = os.path.join(primary_data_dir, 'config.json')
        
        if os.path.exists(primary_config_file):
            with open(primary_config_file, 'r', encoding='utf-8') as f:
                try:
                    primary_config = json.load(f)
                    # 保留目前的 base_path，但以主資料夾內的設定為主
                    primary_config['base_path'] = config['base_path']
                    config = primary_config
                except:
                    pass
        pass

    # 3. 更新全域路徑指針（讓 get_data_file 能正確運作）
    global CONFIG_DIR, CONFIG_FILE
    CONFIG_DIR = get_data_dir(config)
    CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')

    # Set defaults for missing keys
    defaults = {
        'audio_format': 'mp3',
        'ffmpeg_path': 'bin/ffmpeg.exe',
        'lyrics_folder_name': 'Lyrics',
        'language': 'zh-TW',
        'spotify_urls': [],
        'url_names': {},
        'last_updated': {},
        'enable_retroactive_lyrics': False,
        'max_threads': 4,
        'setup_completed': False,
        'retry_failed_lyrics': False,
        'retry_failed_flac': False,
        'lyrics_offsets': {},
        'dab_use_lossless': False,
        'dab_use_metadata': False,
        'dab_email': "",
        'dab_password': "",
        'auto_metadata': False,
        'spotube_folder_name': 'spotube',
        'spotube_exact_match': True,  # Use simple filename matching for Spotube downloads
        'spotube_convert_matched_only': False,  # Only convert M4A files that match playlist entries
        'spotube_strict_matching': True,  # Strict filename matching for M4A->MP3 conversion (True=exact only, False=allow fuzzy)
        'debug_mode': False,  # Enable debug output for troubleshooting
        'spotube_exe_path': '',  # Path to Spotube.exe (auto-detect if empty)
        'spotube_download_path': '',  # Where Spotube saves downloads (default: ~/Downloads/Spotube)
        'spotube_coords': {},  # UI coordinate overrides for Spotube automation
        'search_names': {},  # Override search terms for specific playlists (e.g. {"日本流行樂合輯": "J-Pop Mix"})
        'podcast_rag_in_music': False,  # Run Podcast RAG index inside the music pipeline (default: off)
    }
    for key, value in defaults.items():
        config.setdefault(key, value)

    # Fallback: derive spotify_urls from url_names keys when empty
    if not config.get('spotify_urls') and config.get('url_names'):
        config['spotify_urls'] = list(config['url_names'].keys())

    # If base_path is set, derive other paths from it
    if 'base_path' in config and config['base_path']:
        derive_paths(config)

    from utils.i18n import I18N
    I18N.set_language(config['language'])
    
    # Set global debug mode flag
    set_debug_mode(config.get('debug_mode', False))
    
    return config

def derive_paths(config):
    base_path = os.path.normpath(config['base_path'])

    def _looks_like_music_root(path):
        if not path or not os.path.isdir(path):
            return False
        try:
            entries = os.listdir(path)
        except Exception:
            return False

        lower_entries = {e.lower() for e in entries}
        if 'spotube' in lower_entries:
            return True
        if {'m4a', 'mp3'} & lower_entries and 'playlists' in lower_entries:
            return True
        # If there's a playlists folder, consider it a music root
        if 'playlists' in lower_entries:
            return True

        for name in entries:
            if name.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm')):
                return True
        return False

    library_root = base_path if _looks_like_music_root(base_path) else os.path.join(base_path, 'Music')
    config['library_path'] = os.path.normpath(library_root)
    config['playlists_path'] = os.path.normpath(os.path.join(base_path, 'Playlists'))
    config['export_path'] = os.path.normpath(os.path.join(base_path, 'USB_Output'))
    config['lyrics_path'] = os.path.normpath(os.path.join(library_root, config.get('lyrics_folder_name', 'Lyrics')))
    if os.path.basename(base_path).lower() == 'spotube' and config.get('spotube_folder_name', 'spotube') == 'spotube':
        config['spotube_folder_name'] = ''
    return config

def get_lyrics_dir(config):
    lyrics_path = config.get('lyrics_path')
    if lyrics_path:
        return os.path.normpath(lyrics_path)

    library_path = config.get('library_path') or config.get('base_path') or get_app_data_dir()
    folder_name = config.get('lyrics_folder_name', 'Lyrics')
    return os.path.normpath(os.path.join(library_path, folder_name))

def get_lyrics_file_path(config, audio_path):
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    return os.path.normpath(os.path.join(get_lyrics_dir(config), f"{base_name}.lrc"))

def get_legacy_lyrics_file_path(audio_path):
    return os.path.normpath(os.path.splitext(audio_path)[0] + ".lrc")

def get_data_file(filename):
    """取得資料檔案路徑（會根據當前 CONFIG_DIR 自動導航）"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
    return os.path.join(CONFIG_DIR, filename)

def prompt_and_set_base_path(config):
    from utils.i18n import _
    new_path = filedialog.askdirectory(title=_('select_base_folder'))
    if new_path:
        # 清理可能的路徑格式
        new_path = os.path.normpath(new_path)
        
        # 避免使用者自己點進了 data 資料夾導致 data/data
        if os.path.basename(new_path).lower() == 'data':
            new_path = os.path.dirname(new_path)
            
        config['base_path'] = new_path
        derive_paths(config)
        
        # 切換路徑指針
        global CONFIG_DIR, CONFIG_FILE
        CONFIG_DIR = get_data_dir(config)
        CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')
        
        save_config(config)
        messagebox.showinfo(_('base_folder_set_title'), _('base_folder_set_msg', new_path))
        return True
    return False

def save_config(config):
    # 確保資料目錄存在
    global CONFIG_DIR, CONFIG_FILE
    CONFIG_DIR = get_data_dir(config)
    CONFIG_FILE = os.path.join(CONFIG_DIR, 'config.json')
    
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)
    
    # File lock to prevent concurrent writes from Flutter app
    lock_path = CONFIG_FILE + '.lock'
    for _ in range(100):  # wait up to ~10s
        if not os.path.exists(lock_path):
            break
        time.sleep(0.1)
    if os.path.exists(lock_path):
        # Stale lock: break it
        try: os.remove(lock_path)
        except: pass
    try:
        open(lock_path, 'w').close()
        # 1. 儲存到主資料目錄（包含所有詳細內容）
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)
    finally:
        try: os.remove(lock_path)
        except: pass
    
    # 2. 同步儲存到 EXE 本地目錄（主要作為「路徑指針」）
    if os.path.normpath(CONFIG_DIR) != os.path.normpath(_APP_DATA_DIR):
        # 本地端只需要知道 base_path 就好，其他資料存在主資料夾
        local_pointer = {'base_path': config.get('base_path'), 'language': config.get('language')}
        with open(_APP_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(local_pointer, f, indent=4, ensure_ascii=False)

def ensure_dirs(config):
    if 'base_path' not in config or not config['base_path']:
        return
        
    for key in ['library_path', 'playlists_path', 'export_path', 'lyrics_path']:
        path = config.get(key)
        if path and isinstance(path, str):
            if not os.path.exists(path):
                os.makedirs(path, exist_ok=True)
    
    # 同時確保主資料夾目錄存在
    if not os.path.exists(config['base_path']):
        os.makedirs(config['base_path'], exist_ok=True)


# Global flag for debug mode (set during load_config)
_DEBUG_MODE = False

def set_debug_mode(enabled):
    """Set global debug mode flag"""
    global _DEBUG_MODE
    _DEBUG_MODE = bool(enabled)

def debug_print(*args, **kwargs):
    """Print debug message only if debug mode is enabled"""
    global _DEBUG_MODE
    if _DEBUG_MODE:
        print(*args, **kwargs)

# Global timing storage for task-level timing
_TIMING_DATA = {}

def timing_start(task_name):
    """Start timing a task (only in debug mode)"""
    global _DEBUG_MODE, _TIMING_DATA
    if _DEBUG_MODE:
        _TIMING_DATA[task_name] = time.time()
        debug_print(f"[TIMING] 開始: {task_name}")

def timing_end(task_name, log_func=None):
    """End timing a task and print duration (only in debug mode)"""
    global _DEBUG_MODE, _TIMING_DATA
    if _DEBUG_MODE and task_name in _TIMING_DATA:
        elapsed = time.time() - _TIMING_DATA[task_name]
        msg = f"[TIMING] 完成: {task_name} - 耗時 {elapsed:.3f}s"
        if log_func:
            log_func(msg)
        else:
            debug_print(msg)
        del _TIMING_DATA[task_name]
        return elapsed
    return None
