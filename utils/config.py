import os
import json

CONFIG_FILE = 'config.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Default values
            if 'audio_format' not in config:
                config['audio_format'] = 'mp3'
            if 'language' not in config:
                config['language'] = 'zh-TW'
            if 'url_names' not in config:
                config['url_names'] = {}
            if 'last_updated' not in config:
                config['last_updated'] = {}
            
            from utils.i18n import I18N
            I18N.set_language(config['language'])
            return config
    return {
        "library_path": "./Library",
        "playlists_path": "./Playlists",
        "export_path": "./USB_Export",
        "spotify_urls": [],
        "url_names": {},
        "last_updated": {},
        "audio_format": "mp3",
        "language": "zh-TW"
    }

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def ensure_dirs(config):
    for key in ['library_path', 'playlists_path', 'export_path']:
        path = config.get(key)
        if path and isinstance(path, str):
            if not os.path.exists(path):
                os.makedirs(path)
