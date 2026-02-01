import re
from zhconv import convert

def sanitize_filename(name):
    """Sanitize string to be a valid filename while preserving important information"""
    if not name: 
        return name
    
    # Remove non-breaking spaces and other weird whitespace
    name = name.replace('\xa0', ' ').replace('\u200b', '').strip()
    
    # Only remove truly unnecessary publisher/label garbage, preserve meaningful content
    patterns_to_remove = [
        # Remove only obvious publisher prefixes at the very start
        r'^[A-Za-z0-9\s&]+ - (?=[^\-])',  # Publisher prefixes like "Sony Music - "
        # Remove only generic video suffixes, preserve meaningful identifiers
        r'\s*Official\s+Video\s*$',  # Only exact "Official Video"
        r'\s*Music\s+Video\s*$',     # Only exact "Music Video"
        r'\s*MV\s*$',                 # Only exact "MV"
        r'\s*官方.*?MV\s*$',          # Chinese official MV only
        r'\s*Lyrics?\s+Video\s*$',   # Lyrics video variations
        r'\s*動態歌詞版\s*$',         # Dynamic lyrics version
        r'\s*歌詞版\s*$',             # Lyrics version
        # Remove only generic release info, preserve specific identifiers
        r'\s*發行.*?版\s*$',           # Generic release version
        # Remove YouTube-specific garbage
        r'\s*\(Official\)\s*$',       # Official in parentheses
        r'\s*\[Official\]\s*$',      # Official in brackets
    ]
    
    original_name = name
    for pattern in patterns_to_remove:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    
    # Windows forbidden characters: < > : " / \ | ? *
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    
    # Clean up trailing dots, spaces, and hyphens
    name = name.strip('. -')
    
    # Clean up extra spaces and hyphens
    name = re.sub(r'\s+', ' ', name).strip()
    name = re.sub(r'-+', '-', name).strip()
    
    # Ensure we don't end up with empty filename
    if not name or name.isspace():
        # Fallback: use first meaningful part of original name
        fallback = re.sub(r'[<>:"/\\|?*]', '_', original_name).strip('. -')
        name = fallback[:50] if fallback else "Unknown"
    
    # Ensure reasonable length
    return name[:200]  # Reduced from 250 for safety

def normalize_name(name):
    """Normalize string for fuzzy matching comparison"""
    # 1. Convert to Simplified Chinese (for consistent comparison)
    name = convert(name, 'zh-cn')
    # 2. Replace brackets with space.
    name = re.sub(r"[\(\[【\)\]】]", " ", name)
    # 3. Clean up
    return name.lower().strip().replace('_', ' ').replace('-', ' ').replace(' ', '')
