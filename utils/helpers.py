import re
from zhconv import convert

def sanitize_filename(name):
    """Sanitize string to be a valid filename"""
    if not name: return name
    # Remove non-breaking spaces and other weird whitespace
    name = name.replace('\xa0', ' ').replace('\u200b', '').strip()
    # Windows forbidden characters: < > : " / \ | ? *
    # Also removing potential control characters or trailing dots/spaces
    name = re.sub(r'[<>:"/\\|?*]', '_', name)
    name = name.strip('. ')
    return name[:250]  # Max path length safety

def normalize_name(name):
    """Normalize string for fuzzy matching comparison"""
    # 1. Convert to Simplified Chinese (for consistent comparison)
    name = convert(name, 'zh-cn')
    # 2. Replace brackets with space.
    name = re.sub(r"[\(\[【\)\]】]", " ", name)
    # 3. Clean up
    return name.lower().strip().replace('_', ' ').replace('-', ' ').replace(' ', '')
