import streamlit as st
import pandas as pd
import time
import shutil
import os
from utils.config import load_config, save_config, derive_paths
from core.library import load_playlists_data, update_library_logic, UpdateStats
from core.sync_manager import sync_folders # Added import for sync_folders
from core.dab_client import DABMusicClient # Added import for real DAB login

# ==========================================
# 1. 基礎設定與函式
# ==========================================
st.set_page_config(
    page_title="Playlist Admin Pro",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 優化樣式
st.markdown("""
<style>
    .stMetric {background-color: #262730; padding: 10px; border-radius: 8px; border: 1px solid #333;}
    .stCode {font-family: 'Consolas', monospace;}
    div[data-testid="stToast"] {background-color: #4CAF50; color: white;}
</style>
""", unsafe_allow_html=True)

# 工具函式：計算目錄大小
def get_dir_size(path):
    total_size = 0
    file_count = 0
    flac_count = 0
    try:
        if not os.path.exists(path):
            return 0, 0, 0
        for dirpath, dirnames, filenames in os.walk(path):
            for f in filenames:
                ext = f.lower()
                if ext.endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm')):
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp)
                    file_count += 1
                    if ext.endswith(('.flac', '.wav')):
                        flac_count += 1
        return total_size, file_count, flac_count
    except Exception:
        return 0, 0, 0

# 介面橋接器：用於串接後端邏輯與 Streamlit UI
class StatusBridge:
    def __init__(self, table_placeholder, log_placeholder=None):
        self.table_placeholder = table_placeholder
        self.log_placeholder = log_placeholder
        self.data = []
        self.df = pd.DataFrame(columns=['序號', '狀態', '歌曲名稱'])

    def update_song_status(self, index, status, name):
        # Update or add row
        found = False
        for i, row in enumerate(self.data):
            if row['歌曲名稱'] == name:
                self.data[i]['狀態'] = status
                found = True
                break
        
        if not found:
            self.data.append({'序號': index + 1, '狀態': status, '歌曲名稱': name})
        
        # Update UI Table - Catch NoSessionContext when called from threads
        try:
            self.df = pd.DataFrame(self.data)
            self.table_placeholder.dataframe(self.df, width='stretch', hide_index=True)
        except Exception:
            # Silently fail widget update if not in script context (e.g. lyrics thread)
            # The status will be updated next time a main-thread call happens
            pass

# 設定的讀取與儲存
def initialize_session_state():
    if 'initialized' in st.session_state:
        return

    config = load_config()

    # Define default settings structure based on config keys
    default_settings = {
        'base_path': os.getcwd(),
        'export_path': os.path.join(os.getcwd(), 'USB_Output'),
        'max_threads': 8,
        'spotdl_path': 'bin/spotdl.exe',
        'ffmpeg_path': 'bin/ffmpeg.exe',
        'spotdl_format': 'mp3',
        'spotdl_force_overwrite': False,
        'spotdl_bitrate': '',
        'spotdl_timeout': 600,
        'spotdl_output_template': '',
        'dab_use_lossless': False,
        'dab_use_metadata': False,
        'dab_email': "",
        'dab_password': "",
        'enable_retroactive_lyrics': False,
        'auto_metadata': False,
        'language': 'zh-TW',
        'spotify_urls': [],
        'url_names': {}
    }

    # Merge: values from file override defaults
    st.session_state['settings'] = {**default_settings, **config}
    
    # Ensure derived paths (library_path, playlists_path) are present
    derive_paths(st.session_state['settings'])
    
    # Ensure folders exist
    from utils.config import ensure_dirs
    ensure_dirs(st.session_state['settings'])
    
    # Map backend keys to UI keys if they differ
    if 'base_folder' not in st.session_state['settings']:
        st.session_state['settings']['base_folder'] = os.path.normpath(st.session_state['settings']['base_path'])
    if 'threads' not in st.session_state['settings']:
        st.session_state['settings']['threads'] = st.session_state['settings']['max_threads']
    if 'auto_lyrics' not in st.session_state['settings']:
        st.session_state['settings']['auto_lyrics'] = st.session_state['settings']['enable_retroactive_lyrics']
    
    # Normalize other paths
    st.session_state['settings']['export_path'] = os.path.normpath(st.session_state['settings']['export_path'])

    # Initialize playlist data
    if 'playlist_data' not in st.session_state:
        raw_data = load_playlists_data(st.session_state['settings'])
        if not raw_data:
            # Provide a dummy row or empty DF with columns to avoid crash/empty view
            st.session_state.playlist_data = pd.DataFrame(columns=['啟用', '類型', '名稱', '連結', '狀態'])
        else:
            st.session_state.playlist_data = pd.DataFrame(raw_data)

    st.session_state['initialized'] = True

def save_settings():
    """Saves Streamlit UI state back to config.json"""
    s = st.session_state['settings']
    
    # Prepare config for saving (mapping UI keys back to backend keys if needed)
    config_to_save = {
        'base_path': os.path.normpath(s.get('base_folder')),
        'export_path': os.path.normpath(s.get('export_path')),
        'max_threads': s.get('threads'),
        'dab_use_lossless': s.get('dab_use_lossless'),
        'dab_use_metadata': s.get('dab_use_metadata'),
        'dab_email': s.get('dab_email'),
        'dab_password': s.get('dab_password'),
        'enable_retroactive_lyrics': s.get('auto_lyrics'),
        'auto_metadata': s.get('auto_metadata'),
        'spotdl_path': s.get('spotdl_path', 'bin/spotdl.exe'),
        'ffmpeg_path': s.get('ffmpeg_path', 'bin/ffmpeg.exe'),
        'spotdl_format': s.get('spotdl_format', 'mp3'),
        'spotdl_force_overwrite': s.get('spotdl_force_overwrite', False),
        'spotdl_bitrate': s.get('spotdl_bitrate', ''),
        'spotdl_timeout': int(s.get('spotdl_timeout', 600)),
        'spotdl_output_template': s.get('spotdl_output_template', ''),
        'language': s.get('language', 'zh-TW'),
        'spotify_urls': s.get('spotify_urls', []),
        'url_names': s.get('url_names', {})
    }

    # Derive dependent paths and save
    derive_paths(config_to_save)
    save_config(config_to_save)
    
    # Update local state to reflect potentially derived paths
    st.session_state['settings'].update(config_to_save)
    
    st.toast("✅ 設定已成功儲存！")

# ==========================================
# 2. 程式主體
# ==========================================
initialize_session_state()

# ==========================================
# 3. 側邊欄 (導航 & 狀態)
# ==========================================
with st.sidebar:
    st.title("🎵 Playlist Admin")
    st.caption("v3.0 Sync Edition")
    
    page = st.radio("功能導航", ["🏠 儀表板 (Dashboard)", "📝 連結管理", "📤 匯出同步", "⚙️ 系統設定"])
    
    st.divider()
    
    # st.subheader(f"💾 硬碟狀態 ({drive_letter})")
    # st.progress(disk['percent'], text=f"已使用 {disk['used_gb']} GB")
    
    # c1, c2 = st.columns(2)
    # c1.metric("剩餘 (Free)", f"{disk['free_gb']} GB")
    # c2.metric("總量 (Total)", f"{disk['total_gb']} GB")

# ==========================================
# 🏠 頁面 1: 儀表板 (Dashboard)
# ==========================================
if page == "🏠 儀表板 (Dashboard)":
    st.header("系統概況")

    lib_path = os.path.join(st.session_state['settings']['base_folder'], "Music")
    total_size, total_files, flac_count = get_dir_size(lib_path)
    lossy_count = total_files - flac_count
    size_gb = total_size / (1024**3)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("📚 歌曲總數", f"{total_files:,}")
    col2.metric("💎 無損 (FLAC/WAV)", f"{flac_count:,}")
    col3.metric("🎧 壓縮 (MP3/M4A)", f"{lossy_count:,}")
    col4.metric("💾 資料庫大小", f"{size_gb:.2f} GB")
    
    # Safely handle empty dataframe or missing columns
    if not st.session_state.playlist_data.empty and '啟用' in st.session_state.playlist_data.columns:
        active_count = len(st.session_state.playlist_data[st.session_state.playlist_data['啟用']])
    else:
        active_count = 0
    col5.metric("⚡ 啟用任務", f"{active_count} 個排程")

    st.write("") 

    st.subheader("📂 目前下載路徑")
    st.code(st.session_state['settings']['base_folder'], language="text")
    st.caption("如需修改路徑，請前往 [系統設定] 頁面。")

    st.divider()

    # --- 執行區 ---
    st.subheader("🚀 執行操作")
    
    status_table_placeholder = st.empty()
    status_table_placeholder.info("等待任務開始... (點擊下方按鈕開始)")
    
    col_btn, col_log = st.columns([1, 1])
    with col_btn:
        if st.button("開始下載 / 更新 (Start)", type="primary", width='stretch'):
            progress_bar = st.progress(0, text="準備開始下載...")
            with st.status("正在執行同步更新...", expanded=True) as status_indicator:
                stats = UpdateStats()
                bridge = StatusBridge(status_table_placeholder)
                stats.app = bridge # Provide bridge to backend
                
                log_history = []
                def log_func(msg, immediate=False):
                    log_history.append(f"{time.strftime('%H:%M:%S')} {msg}")
                    # Update status indicator text
                    status_indicator.write(msg)
                    # We could also use another placeholder for log history if needed
                
                def progress_func(current, total, eta=None):
                    if not total or total <= 0:
                        progress_bar.progress(0, text="正在分析缺歌...")
                        return
                    pct = int((float(current) / float(total)) * 100)
                    pct = max(0, min(100, pct))
                    if eta is None:
                        eta_text = "ETA 計算中"
                    else:
                        eta_text = str(eta)
                    progress_bar.progress(pct, text=f"下載進度 {current}/{total} | {eta_text}")
                
                update_library_logic(
                    st.session_state['settings'], 
                    stats, 
                    log_func,
                    progress_func=progress_func
                )
                progress_bar.progress(100, text="下載流程完成")
                
                st.success(f"✅ 同步完成！下載了 {len(stats.songs_downloaded)} 首歌。")
                # Refresh data after download
                st.session_state.playlist_data = pd.DataFrame(load_playlists_data(st.session_state['settings']))
        
        st.button("暫停任務 (Pause)", width='stretch')

    with col_log:
        st.caption("📋 系統日誌 (System Logs)")
        # This will be updated by log_func if we add a placeholder, 
        # but for now let's use a simpler approach or just show completion stats.
        st.info("任務執行時，詳細日誌會顯示在同步狀態欄位中。")

# ==========================================
# 📝 頁面 2: 連結管理
# ==========================================
elif page == "📝 連結管理":
    col_h, col_r = st.columns([4, 1])
    with col_h:
        st.header("管理 Spotify 連結")
        st.caption("勾選「啟用」以納入下載排程。")
    with col_r:
        st.write("") # Padding
        if st.button("🔄 重新整理", width='stretch', help="重新掃描硬碟與設定檔中的歌單"):
            st.session_state.playlist_data = pd.DataFrame(load_playlists_data(st.session_state['settings']))
            st.rerun()

    edited_df = st.data_editor(
        st.session_state.playlist_data,
        column_config={
            "啟用": st.column_config.CheckboxColumn("下載?", width="small"),
            "類型": st.column_config.TextColumn("類型", disabled=True, width="medium"),
            "名稱": st.column_config.TextColumn("歌單名稱", width="medium"),
            "連結": st.column_config.LinkColumn("Spotify URL", width="large"),
            "狀態": st.column_config.TextColumn("同步狀態", disabled=True, width="medium")
        },
        num_rows="dynamic",
        width='stretch',
        height=500
    )
    
    if not edited_df.equals(st.session_state.playlist_data):
        st.session_state.playlist_data = edited_df
        # Update spotify_urls and url_names based on edited_df
        active_playlists = edited_df[edited_df['啟用'] & (edited_df['連結'] != "")]
        st.session_state['settings']['spotify_urls'] = active_playlists['連結'].tolist()
        st.session_state['settings']['url_names'] = {row['連結']: row['名稱'] for _, row in active_playlists.iterrows()}
        # Suggest saving
        st.info("💡 連結清單已變動，請記得點擊「儲存設定」。")

# ==========================================
# 📤 頁面 3: 匯出同步
# ==========================================
elif page == "📤 匯出同步":
    st.header("匯出至外部裝置 (USB/SD)")
    
    col_src, col_dst = st.columns(2)
    with col_src:
        st.info("📂 來源 (電腦):")
        st.code(st.session_state['settings']['base_folder'], language="text")
    with col_dst:
        st.warning("💾 目標 (USB):")
        new_export = st.text_input("輸入目標路徑", value=st.session_state['settings']['export_path'])
        st.session_state['settings']['export_path'] = new_export

    st.divider()

    st.subheader("1. 選擇同步模式")
    
    sync_mode = st.radio(
        "模式選擇",
        ["標準複製 (Copy Only)", "鏡像同步 (Mirror Sync)"],
        captions=[
            "安全模式：僅複製新檔案，USB 上既有的檔案**不會**被刪除。",
            "進階模式：讓 USB 與電腦完全一致。**注意：會刪除 USB 上多餘的舊歌！**"
        ]
    )

    st.subheader("2. 選擇要匯出的歌單")
    if not st.session_state.playlist_data.empty and '名稱' in st.session_state.playlist_data.columns:
        all_playlists = st.session_state.playlist_data["名稱"].tolist()
    else:
        all_playlists = []
    
    selected_playlists = st.multiselect(
        "勾選項目:", 
        options=all_playlists, 
        default=all_playlists
    )

    st.divider()

    btn_type = "primary" if sync_mode == "標準複製 (Copy Only)" else "secondary"
    btn_label = f"🚀 開始執行: {sync_mode.split(' ')[0]}"
    
    if st.button(btn_label, type=btn_type, width='stretch'):
        if not os.path.exists(new_export):
            st.error(f"❌ 目標路徑不存在: {new_export}")
        elif len(selected_playlists) == 0:
            st.error("❌ 未選擇任何歌單")
        else:
            st.toast(f"正在分析 {len(selected_playlists)} 個歌單...")
            with st.status(f"正在進行 [{sync_mode}]...", expanded=True) as status_container:
                # Custom log function for Streamlit
                def log_to_streamlit(message):
                    status_container.write(message)
                
                actual_sync_mode = "Copy" if sync_mode == "標準複製 (Copy Only)" else "Mirror"
                
                sync_folders(
                    source_base_dir=st.session_state['settings']['base_folder'],
                    target_base_dir=new_export,
                    playlist_names=[name for name in selected_playlists if name in st.session_state.playlist_data['名稱'].tolist()], # Ensure only selected and valid playlists are passed
                    mode=actual_sync_mode,
                    log_func=log_to_streamlit
                )
                
                st.success("匯出完成！")

# ==========================================
# ⚙️ 頁面 4: 系統設定
# ==========================================
elif page == "⚙️ 系統設定":
    st.header("系統設定")

    tab1, tab2, tab3 = st.tabs(["一般 & 路徑", "DAB Music (無損核心)", "進階效能"])

    # 更新 session_state 當 UI 變動
    settings = st.session_state['settings']

    with tab1:
        st.subheader("儲存位置")
        settings['base_folder'] = st.text_input("下載資料夾 (Base Folder)", value=settings.get('base_folder'))
        
        st.subheader("介面")
        settings['language'] = st.selectbox("語言 (Language)", ["繁體中文 (zh-TW)", "English (en-US)"], index=0 if settings.get('language') == 'zh-TW' else 1)
        
        st.subheader("spotDL 下載引擎")
        settings['spotdl_path'] = st.text_input("spotdl 路徑", value=settings.get('spotdl_path', 'bin/spotdl.exe'))
        settings['ffmpeg_path'] = st.text_input("ffmpeg 路徑", value=settings.get('ffmpeg_path', 'bin/ffmpeg.exe'))
        settings['spotdl_format'] = st.selectbox(
            "格式",
            ["mp3", "m4a", "opus"],
            index=["mp3", "m4a", "opus"].index(settings.get('spotdl_format', 'mp3')) if settings.get('spotdl_format', 'mp3') in ["mp3", "m4a", "opus"] else 0
        )
        settings['spotdl_force_overwrite'] = st.checkbox("強制覆蓋", value=settings.get('spotdl_force_overwrite', False))
        settings['spotdl_bitrate'] = st.text_input("Bitrate (選填，例如 320k)", value=settings.get('spotdl_bitrate', ''))
        settings['spotdl_timeout'] = st.number_input("spotDL Timeout (秒)", min_value=60, max_value=3600, value=int(settings.get('spotdl_timeout', 600)), step=30)
        settings['spotdl_output_template'] = st.text_input(
            "輸出模板 (選填)",
            value=settings.get('spotdl_output_template', ''),
            help="留空時使用預設 Music/{artist}/{album}/{title}.{output-ext}"
        )

    with tab2:
        st.subheader("DAB Music 核心服務")
        st.info("DAB Music 帳號可用於獲取 FLAC 無損音質或高品質 Metadata (如專輯封面)。")
        
        c1, c2 = st.columns(2)
        with c1:
            settings['dab_use_lossless'] = st.checkbox("啟用項目：無損音質 (FLAC)", value=settings.get('dab_use_lossless', False))
        with c2:
            settings['dab_use_metadata'] = st.checkbox("啟用項目：高品質 Metadata", value=settings.get('dab_use_metadata', False))
            
        if settings['dab_use_lossless'] or settings['dab_use_metadata']:
            c1_cred, c2_cred = st.columns(2)
            with c1_cred:
                settings['dab_email'] = st.text_input("DAB Email", value=settings.get('dab_email'))
            with c2_cred:
                settings['dab_password'] = st.text_input("DAB Password", type="password", value=settings.get('dab_password'))
            
            if st.button("驗證帳號 (Test Login)"):
                if not settings.get('dab_email') or not settings.get('dab_password'):
                    st.warning("⚠️ 請先輸入 Email 與密碼")
                else:
                    client = DABMusicClient()
                    with st.spinner("正在驗證帳號..."):
                        if client.login(settings['dab_email'], settings['dab_password']):
                            user_name = client.user_info.get('username', '使用者')
                            st.success(f"✅ 驗證成功！歡迎回來，{user_name}。")
                        else:
                            st.error("❌ 驗證失敗，請檢查 Email 或密碼是否正確，或確認伺服器狀態。")
        else:
            st.caption("目前狀態：使用公開來源 (僅 MP3 128/320kbps)")

    with tab3:
        st.subheader("下載行為")
        settings['threads'] = st.slider("同時下載數 (Threads)", 1, 32, value=settings.get('max_threads', 8))
        settings['auto_lyrics'] = st.checkbox("自動搜尋歌詞 (Auto Lyrics)", value=settings.get('enable_retroactive_lyrics', False))
        
        # Meta toggle now decoupled from lossless, but still needs credentials
        md_disabled = not (settings.get('dab_use_lossless') or settings.get('dab_use_metadata'))
        md_help = "需要啟用任一 DAB Music 核心服務才能使用此功能" if md_disabled else "將封面與詳細專輯資訊寫入檔案"
        
        settings['auto_metadata'] = st.checkbox("自動寫入 Metadata (DAB 精確版)", 
                    value=settings.get('auto_metadata'),
                    disabled=md_disabled,
                    help=md_help)
        
        if md_disabled:
            st.warning("⚠️ 「自動寫入 Metadata」功能已停用，請先至 [DAB Music] 分頁啟用服務並登入。")
    
    st.divider()
    if st.button("💾 儲存設定 (Save Settings)", type="primary", width='stretch'):
        save_settings()
