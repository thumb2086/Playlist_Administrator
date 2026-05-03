import os
import time

import pandas as pd
import streamlit as st

from core.library import UpdateStats, load_playlists_data, update_library_logic
from core.sync_manager import sync_folders
from utils.config import derive_paths, ensure_dirs, load_config, save_config
from utils.version import get_version

DEPRECATION_NOTICE = (
    "Streamlit UI is deprecated. Please use Tkinter with `python main.py`."
)

st.set_page_config(
    page_title="Playlist Administrator",
    page_icon="PA",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.warning(DEPRECATION_NOTICE, icon="WARNING")

st.markdown(
    """
<style>
:root {
  --pa-ink: #20231f;
  --pa-muted: #667064;
  --pa-line: #d9ded5;
  --pa-paper: #f8faf3;
  --pa-panel: #ffffff;
  --pa-sage: #6f8f72;
  --pa-coral: #c8654b;
  --pa-gold: #c69a3d;
}
.stApp {
  color: var(--pa-ink);
  background:
    linear-gradient(135deg, rgba(111,143,114,.16), transparent 34%),
    linear-gradient(315deg, rgba(198,154,61,.14), transparent 36%),
    var(--pa-paper);
}
[data-testid="stSidebar"] {
  background: #edf2e8;
  border-right: 1px solid var(--pa-line);
}
[data-testid="stMetric"] {
  background: var(--pa-panel);
  border: 1px solid var(--pa-line);
  border-radius: 8px;
  padding: 14px 16px;
  box-shadow: 0 10px 26px rgba(32,35,31,.06);
}
.pa-band {
  border: 1px solid var(--pa-line);
  background: rgba(255,255,255,.76);
  border-radius: 8px;
  padding: 18px 20px;
  margin: 8px 0 18px;
}
.pa-title {
  font-size: 30px;
  line-height: 1.15;
  font-weight: 800;
  margin: 0 0 6px;
}
.pa-subtle {
  color: var(--pa-muted);
}
.stButton > button {
  border-radius: 8px;
  border: 1px solid var(--pa-line);
  font-weight: 700;
}
.stButton > button[kind="primary"] {
  background: var(--pa-sage);
  border-color: var(--pa-sage);
}
div[data-testid="stStatusWidget"] {
  border-radius: 8px;
}
</style>
""",
    unsafe_allow_html=True,
)


AUDIO_EXTENSIONS = (".mp3", ".flac", ".wav", ".m4a", ".webm")
LOSSLESS_EXTENSIONS = (".flac", ".wav")
PLAYLIST_COLUMNS = ["啟用", "類型", "名稱", "連結", "狀態"]


def scan_library(path):
    total_size = 0
    total_files = 0
    lossless_count = 0
    if not path or not os.path.exists(path):
        return total_size, total_files, lossless_count

    for dirpath, _, filenames in os.walk(path):
        for filename in filenames:
            if not filename.lower().endswith(AUDIO_EXTENSIONS):
                continue
            file_path = os.path.join(dirpath, filename)
            try:
                total_size += os.path.getsize(file_path)
            except OSError:
                pass
            total_files += 1
            if filename.lower().endswith(LOSSLESS_EXTENSIONS):
                lossless_count += 1
    return total_size, total_files, lossless_count


def normalize_playlist_frame(rows):
    frame = pd.DataFrame(rows or [], columns=PLAYLIST_COLUMNS)
    for column in PLAYLIST_COLUMNS:
        if column not in frame.columns:
            frame[column] = "" if column != "啟用" else False
    frame = frame[PLAYLIST_COLUMNS]
    frame["啟用"] = frame["啟用"].fillna(False).astype(bool)
    return frame.fillna("")


def refresh_playlist_data():
    st.session_state.playlist_data = normalize_playlist_frame(
        load_playlists_data(st.session_state.settings)
    )


def initialize_state():
    if st.session_state.get("initialized"):
        return

    config = load_config()
    defaults = {
        "base_path": os.getcwd(),
        "export_path": os.path.join(os.getcwd(), "USB_Output"),
        "ffmpeg_path": "bin/ffmpeg.exe",
        "spotube_folder_name": "spotube",
        "spotube_exact_match": True,
        "language": "zh-TW",
        "spotify_urls": [],
        "url_names": {},
    }
    settings = {**defaults, **config}
    derive_paths(settings)
    ensure_dirs(settings)

    st.session_state.settings = settings
    st.session_state.initialized = True
    refresh_playlist_data()


def persist_settings():
    settings = st.session_state.settings.copy()
    derive_paths(settings)
    save_config(settings)
    st.session_state.settings = settings


def update_playlist_settings(frame):
    active = frame[(frame["啟用"]) & (frame["連結"].astype(str).str.strip() != "")]
    st.session_state.settings["spotify_urls"] = active["連結"].astype(str).tolist()
    st.session_state.settings["url_names"] = {
        str(row["連結"]): str(row["名稱"]).strip() or str(row["連結"])
        for _, row in active.iterrows()
    }


class StreamlitStatusBridge:
    def __init__(self, placeholder):
        self.placeholder = placeholder
        self.rows = []

    def update_song_status(self, index, status, name):
        item = {"序號": index + 1, "狀態": status, "歌曲": name}
        for row in self.rows:
            if row["序號"] == item["序號"]:
                row.update(item)
                break
        else:
            self.rows.append(item)
        self.placeholder.dataframe(pd.DataFrame(self.rows), hide_index=True, width="stretch")


def render_header():
    st.markdown(
        f"""
<div class="pa-band">
  <div class="pa-title">Playlist Administrator</div>
  <div class="pa-subtle">v{get_version()} · Spotify embed · MP3 playlist workflow</div>
</div>
""",
        unsafe_allow_html=True,
    )


initialize_state()
render_header()

settings = st.session_state.settings
library_path = settings.get("library_path")
playlists_path = settings.get("playlists_path")
export_path = settings.get("export_path")

with st.sidebar:
    st.subheader("工作區")
    st.caption(settings.get("base_path", ""))
    page = st.radio(
        "導覽",
        ["總覽", "更新", "連結", "匯出", "設定"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption(f"Music: {library_path}")
    st.caption(f"Playlists: {playlists_path}")


if page == "總覽":
    total_size, total_files, lossless_count = scan_library(library_path)
    lossy_count = max(total_files - lossless_count, 0)
    active_count = int(st.session_state.playlist_data["啟用"].sum()) if not st.session_state.playlist_data.empty else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("歌曲總數", f"{total_files:,}")
    col2.metric("無損檔案", f"{lossless_count:,}")
    col3.metric("MP3/壓縮", f"{lossy_count:,}")
    col4.metric("啟用歌單", f"{active_count:,}")

    st.markdown('<div class="pa-band">', unsafe_allow_html=True)
    st.subheader("最近的歌單狀態")
    preview = st.session_state.playlist_data[["啟用", "類型", "名稱", "狀態"]].head(12)
    st.dataframe(preview, hide_index=True, width="stretch")
    st.markdown("</div>", unsafe_allow_html=True)


elif page == "更新":
    st.subheader("更新音樂庫與 Spotify 歌單")
    st.caption("會先抓取 Spotify embed 曲目、重建 m3u8，接著清掉指向不存在檔案的歌單項目。")

    status_table = st.empty()
    progress = st.progress(0, text="等待開始")
    logs = st.empty()

    if st.button("開始更新", type="primary", width="stretch"):
        stats = UpdateStats()
        stats.app = StreamlitStatusBridge(status_table)
        log_lines = []

        def log_func(message, immediate=False):
            log_lines.append(f"{time.strftime('%H:%M:%S')} {message}")
            logs.code("\n".join(log_lines[-80:]), language="text")

        def progress_func(current, total, eta=None):
            total = total or 100
            pct = int(max(0, min(100, (float(current) / float(total)) * 100)))
            progress.progress(pct, text=f"進度 {current}/{total}")

        with st.status("正在更新", expanded=True) as status:
            update_library_logic(settings, stats, log_func, progress_func=progress_func)
            progress.progress(100, text="完成")
            status.update(label="更新完成", state="complete")

        refresh_playlist_data()
        st.success("更新完成，歌單資料已重新載入。")


elif page == "連結":
    st.subheader("Spotify 連結")
    st.caption("新增或停用歌單後，請儲存設定。")

    edited = st.data_editor(
        st.session_state.playlist_data,
        column_config={
            "啟用": st.column_config.CheckboxColumn("啟用", width="small"),
            "類型": st.column_config.TextColumn("類型", disabled=True),
            "名稱": st.column_config.TextColumn("名稱"),
            "連結": st.column_config.LinkColumn("Spotify URL"),
            "狀態": st.column_config.TextColumn("狀態", disabled=True),
        },
        num_rows="dynamic",
        hide_index=True,
        width="stretch",
        height=520,
    )

    col1, col2 = st.columns([1, 1])
    if col1.button("儲存連結", type="primary", width="stretch"):
        st.session_state.playlist_data = normalize_playlist_frame(edited)
        update_playlist_settings(st.session_state.playlist_data)
        persist_settings()
        st.success("連結設定已儲存。")
    if col2.button("重新載入", width="stretch"):
        refresh_playlist_data()
        st.rerun()


elif page == "匯出":
    st.subheader("匯出到 USB/SD")
    source_col, target_col = st.columns(2)
    source_col.text_input("來源", value=settings.get("base_path", ""), disabled=True)
    target = target_col.text_input("目標路徑", value=export_path or "")
    settings["export_path"] = target

    mode_label = st.radio(
        "同步模式",
        ["Copy", "Mirror"],
        default="Copy",
        help="Mirror 會讓目標資料夾和選取歌單一致。",
        horizontal=True,
    )

    playlist_names = st.session_state.playlist_data["名稱"].dropna().astype(str).tolist()
    selected = st.multiselect("歌單", playlist_names, default=playlist_names)

    if st.button("開始匯出", type="primary", width="stretch"):
        if not target or not os.path.exists(target):
            st.error(f"目標路徑不存在: {target}")
        elif not selected:
            st.error("請至少選擇一個歌單。")
        else:
            persist_settings()
            with st.status("正在匯出", expanded=True) as status:
                def log_export(message):
                    status.write(message)

                sync_folders(
                    source_base_dir=settings.get("base_path"),
                    target_base_dir=target,
                    playlist_names=selected,
                    mode=mode_label,
                    log_func=log_export,
                )
                status.update(label="匯出完成", state="complete")


elif page == "設定":
    st.subheader("系統設定")
    col1, col2 = st.columns(2)

    with col1:
        settings["base_path"] = st.text_input("Base Folder", value=settings.get("base_path", ""))
        settings["language"] = st.selectbox(
            "語言",
            ["zh-TW", "en"],
            index=0 if settings.get("language", "zh-TW") == "zh-TW" else 1,
        )
        settings["ffmpeg_path"] = st.text_input("ffmpeg 路徑", value=settings.get("ffmpeg_path", "bin/ffmpeg.exe"))

    with col2:
        settings["spotube_folder_name"] = st.text_input("Spotube 資料夾", value=settings.get("spotube_folder_name", "spotube"))
        settings["spotube_exact_match"] = st.checkbox(
            "Spotube 檔名精準匹配",
            value=bool(settings.get("spotube_exact_match", True)),
        )
        settings["spotube_convert_matched_only"] = st.checkbox(
            "只轉換有匹配歌單的歌曲",
            value=bool(settings.get("spotube_convert_matched_only", False)),
        )
        st.text_input("Playlists", value=playlists_path or "", disabled=True)

    if st.button("儲存設定", type="primary", width="stretch"):
        derive_paths(settings)
        ensure_dirs(settings)
        persist_settings()
        refresh_playlist_data()
        st.success("設定已儲存。")
