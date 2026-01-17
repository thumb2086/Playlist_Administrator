import re
from zhconv import convert

def sanitize_filename(name):
    """Sanitize string to be a valid filename"""
    # Windows forbidden characters: < > : " / \ | ? *
    return re.sub(r'[<>:"/\\|?*]', '_', name)

def normalize_name(name):
    """Normalize string for fuzzy matching comparison"""
    # 1. Convert to Simplified Chinese (for consistent comparison)
    name = convert(name, 'zh-cn')
    # 2. Replace brackets with space.
    name = re.sub(r"[\(\[【\)\]】]", " ", name)
    # 3. Clean up
    return name.lower().strip().replace('_', ' ').replace('-', ' ').replace(' ', '')
