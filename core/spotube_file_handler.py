import os
import glob
import time
import shutil
import logging

logger = logging.getLogger(__name__)


def move_spotube_downloads(config, log_func, dry_run=False):
    """Move newly downloaded files from Downloads/Spotube to the m4a folder.

    Reads::

        config["spotube_download_path"]  (default: ~/Downloads/Spotube)

    Writes to::

        {library_path}/m4a/

    Files that already exist in the destination (by name) are skipped so
    this is safe to call repeatedly.
    """
    src_base = config.get("spotube_download_path") or os.path.expandvars(r"%USERPROFILE%\Downloads\Spotube")
    library_path = config.get("library_path", "")
    dest = os.path.join(library_path, "m4a")

    if not os.path.isdir(src_base):
        log_func(f"  下載來源不存在: {src_base}")
        return 0

    os.makedirs(dest, exist_ok=True)

    # Scan for audio files (Spotube downloads M4A by default).
    exts = (".m4a", ".mp3", ".flac", ".wav", ".webm")
    files = []
    for ext in exts:
        files.extend(glob.glob(os.path.join(src_base, f"*{ext}")))
        files.extend(glob.glob(os.path.join(src_base, "**", f"*{ext}"), recursive=True))

    if not files:
        log_func("  Downloads/Spotube 中沒有新檔案")
        return 0

    moved = 0
    for src in sorted(files):
        name = os.path.basename(src)
        dst = os.path.join(dest, name)

        if os.path.exists(dst):
            logger.debug("Skipping %s (already exists in m4a)", name)
            continue

        if dry_run:
            log_func(f"  [模擬] 搬移: {name}")
            moved += 1
            continue

        try:
            shutil.move(src, dst)
            log_func(f"  [OK] {name}")
            moved += 1
        except Exception as exc:
            log_func(f"  [FAIL] {name}: {exc}")

    log_func(f"  已搬移 {moved} 個檔案到 {dest}")
    return moved


def wait_for_new_downloads(config, log_func, timeout=300, poll_interval=5):
    """Block until new files appear in the Downloads/Spotube folder.

    Returns the list of new file paths (or empty list on timeout).
    """
    src_base = config.get("spotube_download_path") or os.path.expandvars(r"%USERPROFILE%\Downloads\Spotube")
    if not os.path.isdir(src_base):
        log_func(f"  等待下載資料夾: {src_base}")
        os.makedirs(src_base, exist_ok=True)

    # Count existing files.
    before = set(glob.glob(os.path.join(src_base, "**", "*"), recursive=True))

    elapsed = 0
    while elapsed < timeout:
        time.sleep(poll_interval)
        elapsed += poll_interval

        now = set(glob.glob(os.path.join(src_base, "**", "*"), recursive=True))
        new = now - before

        # Filter to audio files that have finished writing (size stable).
        stable = []
        for p in sorted(new):
            if not os.path.isfile(p):
                continue
            if not p.lower().endswith((".m4a", ".mp3", ".flac")):
                continue
            size1 = os.path.getsize(p)
            time.sleep(0.5)
            size2 = os.path.getsize(p)
            if size1 == size2 and size1 > 0:
                stable.append(p)

        if stable:
            log_func(f"  偵測到 {len(stable)} 個新下載檔案")
            return stable

        if elapsed % 30 == 0:
            log_func(f"  等待下載中… ({elapsed}s / {timeout}s)")

    log_func(f"  等候逾時 ({timeout}s)，未發現新檔案")
    return []
