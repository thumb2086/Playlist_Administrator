"""
Version information for Playlist Administrator
"""

# Current version - update this when releasing a new version
# v1.5.2 - Fix M3U8 path encoding: remove URL encoding for Windows/Echo Nightly compatibility
# NOTE: On CI builds, this file is automatically updated from the git tag.
#       Manual changes here are only for development use.
__version__ = "2.6.0"

# GitHub repository info for update checking
GITHUB_OWNER = "thumb2086"
GITHUB_REPO = "Playlist_Administrator"

# Default check interval in days
CHECK_INTERVAL_DAYS = 1


def get_version():
    """Get the current application version"""
    return __version__


def parse_version(version_str):
    """Parse version string to tuple for comparison"""
    try:
        # Remove 'v' prefix if present
        version_str = version_str.lstrip('v')
        parts = version_str.split('.')
        return tuple(int(x) for x in parts[:3])  # Support up to 3 version components
    except (ValueError, AttributeError):
        return (0, 0, 0)


def compare_versions(current, latest):
    """
    Compare two version strings
    Returns: -1 if current < latest, 0 if equal, 1 if current > latest
    """
    current_tuple = parse_version(current)
    latest_tuple = parse_version(latest)

    if current_tuple < latest_tuple:
        return -1
    elif current_tuple > latest_tuple:
        return 1
    else:
        return 0


def is_newer_version_available(current_version, latest_version):
    """Check if a newer version is available"""
    return compare_versions(current_version, latest_version) < 0
