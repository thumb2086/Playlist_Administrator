"""
Version checker for Playlist Administrator
Checks GitHub releases for updates
"""

import time
import requests
from datetime import datetime, timedelta
from .version import (
    get_version,
    is_newer_version_available,
    GITHUB_OWNER,
    GITHUB_REPO,
    CHECK_INTERVAL_DAYS
)


def should_check_for_updates(config):
    """
    Check if we should check for updates based on last check time
    Returns True if enough time has passed since last check
    """
    last_check_str = config.get('last_version_check')
    if not last_check_str:
        return True
    
    try:
        last_check = datetime.fromisoformat(last_check_str)
        next_check = last_check + timedelta(days=CHECK_INTERVAL_DAYS)
        return datetime.now() >= next_check
    except (ValueError, TypeError):
        return True


def check_for_updates(silent=False, timeout=5):
    """
    Check GitHub releases for a newer version
    
    Args:
        silent: If True, don't print/log anything (for background checks)
        timeout: Request timeout in seconds
        
    Returns:
        dict with keys: 'has_update' (bool), 'current_version', 'latest_version', 
                        'download_url', 'release_notes', 'error' (if any)
    """
    current_version = get_version()
    result = {
        'has_update': False,
        'current_version': current_version,
        'latest_version': None,
        'download_url': None,
        'release_notes': None,
        'error': None
    }
    
    try:
        # GitHub API endpoint for latest release
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
        
        headers = {
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': f'PlaylistAdministrator/{current_version}'
        }
        
        response = requests.get(url, headers=headers, timeout=timeout)
        
        if response.status_code == 404:
            result['error'] = "No releases found"
            return result
        
        response.raise_for_status()
        
        release_data = response.json()
        latest_version = release_data.get('tag_name', '').lstrip('v')
        
        result['latest_version'] = latest_version
        result['download_url'] = release_data.get('html_url', '')
        result['release_notes'] = release_data.get('body', '')
        
        # Check if newer version exists
        if latest_version and is_newer_version_available(current_version, latest_version):
            result['has_update'] = True
            
            # Find Windows installer asset
            assets = release_data.get('assets', [])
            for asset in assets:
                asset_name = asset.get('name', '').lower()
                if asset_name.endswith('.exe') and 'setup' in asset_name:
                    result['download_url'] = asset.get('browser_download_url', result['download_url'])
                    break
        
        return result
        
    except requests.exceptions.Timeout:
        result['error'] = "Connection timeout"
        if not silent:
            print("[Version Check] Connection timeout")
    except requests.exceptions.RequestException as e:
        result['error'] = f"Network error: {str(e)}"
        if not silent:
            print(f"[Version Check] Network error: {e}")
    except Exception as e:
        result['error'] = f"Error checking for updates: {str(e)}"
        if not silent:
            print(f"[Version Check] Error: {e}")
    
    return result


def perform_update_check(config, log_func=None, silent=False):
    """
    Perform version check and update config with check time
    
    Args:
        config: Application config dict
        log_func: Optional logging function
        silent: If True, perform background check without UI notifications
        
    Returns:
        dict from check_for_updates()
    """
    # Update last check time
    config['last_version_check'] = datetime.now().isoformat()
    from .config import save_config
    save_config(config)
    
    result = check_for_updates(silent=silent)
    
    if log_func and result['has_update']:
        log_func(f"[Update] New version available: {result['latest_version']}")
    elif log_func and result['error'] and not silent:
        log_func(f"[Update Check] {result['error']}")
    
    return result


def format_release_notes(notes, max_length=500):
    """Format release notes for display"""
    if not notes:
        return "No release notes available."
    
    # Remove markdown headers for cleaner display
    import re
    clean_notes = re.sub(r'^#{1,6}\s*', '', notes, flags=re.MULTILINE)
    
    if len(clean_notes) > max_length:
        clean_notes = clean_notes[:max_length] + "..."
    
    return clean_notes.strip()
