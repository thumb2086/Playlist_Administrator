import os
import glob
import time
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.pipeline import PipelineStep, PipelineState
from core.library import (
    _resolve_spotube_paths,
    _get_m4a_cache_key,
    build_library_index,
    build_metadata_index,
    _build_playlist_song_index,
    _find_existing_mp3_for_source,
    _metadata_based_mp3_path,
    _move_matching_legacy_mp3,
)
from core.audio_converter import convert_audio_file
from core.ffmpeg_installer import ensure_ffmpeg_available, get_ffmpeg_path


class StepConvert(PipelineStep):
    """Convert Spotube M4A files to MP3 with real progress and killable workers."""

    @property
    def name(self):
        return "Convert M4A → MP3"

    @property
    def weight(self):
        return 35.0

    def run(self, state: PipelineState):
        config = state.config
        log_func = state.log_func

        m4a_path, mp3_path = _resolve_spotube_paths(config)
        os.makedirs(m4a_path, exist_ok=True)
        os.makedirs(mp3_path, exist_ok=True)

        if not ensure_ffmpeg_available(config, log_func):
            log_func("FFmpeg unavailable. Skip conversion.")
            return True

        if not state.wait_if_paused() or state.is_cancelled():
            return False

        # --- 1. Scan M4A files ---
        log_func("正在掃描 M4A 檔案…")
        _cache_key, m4a_files = _get_m4a_cache_key(m4a_path, mp3_path)
        if not m4a_files:
            log_func("沒有 M4A 檔案需要轉換。")
            return True
        log_func(f"找到 {len(m4a_files)} 個 M4A 檔案")

        if not state.wait_if_paused() or state.is_cancelled():
            return False

        # --- 2. Build index with progress ---
        existing_mp3 = len(glob.glob(os.path.join(mp3_path, "**", "*.mp3"), recursive=True))
        total_mp3 = len(glob.glob(os.path.join(config.get("library_path", ""), "**", "*.mp3"), recursive=True))
        log_func(f"M4A: {len(m4a_files)} 個, 已有 MP3: {existing_mp3} 個 (共 {total_mp3} 個)")
        if existing_mp3 >= len(m4a_files):
            log_func("所有 M4A 似乎都已轉檔完畢，檢查是否有新檔案需要轉換…")
        log_func(f"掃描 MP3 索引…")

        search_pattern = os.path.join(config.get("library_path", ""), "**", "*")
        all_files = [f for f in glob.glob(search_pattern, recursive=True) if os.path.isfile(f)]
        mp3_files = [f for f in all_files if f.lower().endswith('.mp3')]
        log_func(f"建立檔名索引 ({len(mp3_files)} 個 MP3)…")
        mp3_index = build_library_index(mp3_files)

        log_func("讀取 MP3 元資料索引（可能需數秒）…")
        metadata_index = build_metadata_index(mp3_files)
        log_func(f"元資料索引完成 ({len(metadata_index)} 個條目)")

        playlist_index = None
        if config.get("spotube_convert_matched_only", False):
            pl_path = config.get("playlists_path", "")
            log_func("建立播放清單索引…")
            playlist_index = _build_playlist_song_index(pl_path)
            log_func(f"播放清單索引完成 ({len(playlist_index) if playlist_index else 0} 個條目)")

        if state.is_cancelled():
            return False

        # --- 3. Build task list with status tracking ---
        tasks = []
        skipped = 0
        scb = state.status_cb
        for idx, src in enumerate(m4a_files):
            if os.path.normpath(src).lower().startswith(os.path.normpath(mp3_path).lower()):
                continue

            base = os.path.splitext(os.path.basename(src))[0]
            legacy_dest = os.path.join(mp3_path, f"{base}.mp3")
            dest, name = _metadata_based_mp3_path(src, mp3_path)
            _move_matching_legacy_mp3(src, legacy_dest, dest, log_func)

            existing = _find_existing_mp3_for_source(src, mp3_index, metadata_index)
            if existing:
                if scb:
                    scb(idx, "[skip]", name)
                skipped += 1
                continue
            # Fallback: check if MP3 exists AND is newer than M4A (confirmed converted)
            if os.path.exists(dest) and os.path.getmtime(dest) >= os.path.getmtime(src):
                if scb:
                    scb(idx, "[skip]", name)
                skipped += 1
                continue
            if playlist_index:
                bn = os.path.splitext(os.path.basename(src))[0]
                bn_lower = bn.lower()
                found = any(bn_lower in pl_name.lower()
                            for pl_name in playlist_index.values())
                if not found:
                    if scb:
                        scb(idx, "[skip]", name)
                    skipped += 1
                    continue

            if scb:
                scb(idx, "[wait]", name)
            tasks.append((idx, src, dest, name))

        total_tasks = len(tasks)
        if total_tasks == 0:
            log_func("所有 M4A 已有對應 MP3，無需轉換。")
            return True

        log_func(f"待轉檔: {total_tasks}, 跳過 (已存在): {skipped}")

        # --- 4. Convert with ThreadPoolExecutor (batched, killable) ---
        worker_count = max(1, int(config.get("spotube_convert_workers", 4)))
        log_func(f"使用 {worker_count} 個執行緒轉檔…")

        batch_size = 50
        converted = 0

        with ThreadPoolExecutor(max_workers=worker_count) as ex:
            for batch_start in range(0, len(tasks), batch_size):
                batch = tasks[batch_start:batch_start + batch_size]
                future_map = {}
                for item in batch:
                    if state.is_cancelled():
                        break
                    if not state.wait_if_paused():
                        break
                    idx, src, dest, song_name = item
                    if scb:
                        scb(idx, "[conv]", song_name)
                    fut = ex.submit(self._convert_one, src, dest, song_name,
                                    config, log_func, state)
                    future_map[fut] = (idx, src, dest, song_name)

                for fut in as_completed(future_map):
                    if state.is_cancelled():
                        break
                    idx, src, dest, song_name = future_map[fut]
                    ok = fut.result()
                    if ok:
                        converted += 1
                        if scb:
                            scb(idx, "[done]", song_name)
                    else:
                        if scb:
                            scb(idx, "[FAIL]", song_name)
                    state.progress_cb(self.name, converted, total_tasks,
                                      f"{converted}/{total_tasks}")
                    if converted % 50 == 0 or converted == total_tasks:
                        log_func(f"  進度: {converted}/{total_tasks}")

        log_func(f"轉檔完成: {converted} 個新 MP3")
        return True

    def _convert_one(self, src, dest, name, config, log_func, state):
        if state.is_cancelled():
            return False
        if not state.wait_if_paused():
            return False
        try:
            convert_audio_file(src, dest, 'mp3', log_func, get_ffmpeg_path(config))
            return True
        except Exception as e:
            log_func(f"  [FAIL] {name}: {e}")
            return False
