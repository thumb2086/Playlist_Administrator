"""Resolve podcast RAG paths from the app config (same as the CLI/GUI)."""
import json
import os
from pathlib import Path


def find_base() -> Path:
    env_bp = os.environ.get("BASE_PATH")
    if env_bp:
        return Path(env_bp)
    local = os.environ.get("LOCALAPPDATA")
    pointer = None
    if local:
        pointer = Path(local) / "playlist-admin" / "data" / "config.json"
        if not pointer.exists():
            pointer = Path(local) / "Playlist Administrator" / "data" / "config.json"
    try:
        if pointer and pointer.exists():
            data = json.loads(pointer.read_text(encoding="utf-8"))
            bp = data.get("base_path") or data.get("basePath")
            if bp:
                return Path(bp)
    except Exception:
        pass
    return Path(r"C:\Users\CPXru\Music\playlist-admin")


def podcast_downloads_dir() -> Path:
    return find_base() / "podcasts"


def rag_data_dir() -> Path:
    return find_base() / "cache" / "podcast"


def chroma_db_dir() -> Path:
    return rag_data_dir() / "chroma_db"