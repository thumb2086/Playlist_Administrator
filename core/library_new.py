def move_unsorted_songs(config, log_func):
    """ Creates playlist for songs not in any playlist (without moving files) """
    from utils.i18n import _
    log_func(_('moving_unsorted'))
    
    # Normalize paths to standard Windows backslashes for reliable string comparison
    library_path = os.path.normpath(os.path.abspath(config['library_path']))
    playlists_path = os.path.normpath(os.path.abspath(config['playlists_path']))
    
    # 1. Gather all songs from all playlists
    all_playlist_files = glob.glob(os.path.join(playlists_path, "*.m3u8")) + \
                         glob.glob(os.path.join(playlists_path, "*.m3u"))
    
    songs_in_playlists = set()
    for pl_file in all_playlist_files:
        base = os.path.basename(pl_file)
        # Skip the unsorted/single tracks playlists themselves
        if any(x in base for x in ["_未分類", "_Unsorted", "Single Tracks", "單曲"]): continue
        songs_in_playlists.update(parse_playlist(pl_file))
    
    # Build tokens for comparison
    playlist_tokens = set()
    for s in songs_in_playlists:
        t = tuple(get_normalized_tokens(s))
        if t: playlist_tokens.add(t)
        
    # 2. Identify orphan files in Music root and subdirectories
    search_pattern = os.path.join(library_path, "**", "*")
    all_library_files = [os.path.normpath(f) for f in glob.glob(search_pattern, recursive=True) if os.path.isfile(f)]
    
    orphans = []
    for f in all_library_files:
        if os.path.basename(f).startswith('.'): continue
        if not f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm')): continue
        
        filename_no_ext = os.path.splitext(os.path.basename(f))[0]
        file_tokens = tuple(get_normalized_tokens(filename_no_ext))
        
        if file_tokens not in playlist_tokens:
            orphans.append(f)
    
    # 3. Create playlist for unsorted songs (without moving files)
    pl_name = "_" + _('removed_songs_pl')
    m3u_path = os.path.join(playlists_path, f"{pl_name}.m3u8")
    
    # Check if we should also handle manual single tracks (songs in Music/Single Tracks)
    single_tracks_dir = os.path.join(library_path, "Single Tracks")
    single_tracks_pl = os.path.join(playlists_path, "Single Tracks.m3u8")
    
    if os.path.exists(single_tracks_dir):
        st_files = [f for f in os.listdir(single_tracks_dir) if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav', '.webm'))]
        if st_files:
            with open(single_tracks_pl, 'w', encoding='utf-8-sig', newline='') as f:
                f.write("#EXTM3U\r\n")
                for base in sorted(st_files):
                    name_no_ext = os.path.splitext(base)[0]
                    rel_path = f"../Music/Single Tracks/{base}"
                    f.write(f"#EXTINF:-1,{name_no_ext}\r\n")
                    f.write(f"{rel_path}\r\n")
    
    # Cleanup old legacy name if it exists
    old_m3u_path = os.path.join(playlists_path, "_Unsorted_Songs.m3u8")
    if old_m3u_path != m3u_path and os.path.exists(old_m3u_path):
        try: os.remove(old_m3u_path)
        except: pass
    
    # Create playlist for unsorted songs (keep files in original location)
    if orphans:
        try:
            os.makedirs(playlists_path, exist_ok=True)
            with open(m3u_path, 'w', encoding='utf-8-sig', newline='') as f:
                f.write("#EXTM3U\r\n")
                for file_path in sorted(orphans):
                    # Get relative path from playlists folder to the audio file
                    abs_file_path = os.path.normpath(os.path.abspath(file_path))
                    abs_playlists_path = os.path.normpath(os.path.abspath(playlists_path))
                    
                    # Calculate relative path
                    try:
                        rel_path = os.path.relpath(abs_file_path, abs_playlists_path)
                        # Convert to forward slashes for M3U compatibility
                        rel_path = rel_path.replace('\\', '/')
                    except ValueError:
                        # Cross-drive issue: use absolute path or fallback
                        # Use forward slashes and remove drive letter for compatibility
                        rel_path = abs_file_path.replace('\\', '/')
                        if ':' in rel_path:
                            # Remove drive letter for cross-drive compatibility
                            rel_path = rel_path.split(':', 1)[1].lstrip('/\\')
                        # Fallback to absolute path if relative path fails
                        rel_path = abs_file_path
                    
                    name_no_ext = os.path.splitext(os.path.basename(file_path))[0]
                    f.write(f"#EXTINF:-1,{name_no_ext}\r\n")
                    f.write(f"{rel_path}\r\n")
            
            log_func(f" -> 已為 {len(orphans)} 首未分類歌曲創建播放清單")
        except Exception as e:
            log_func(f"  ⚠️ 創建未分類播放清單失敗: {e}")
    else:
        # Remove empty playlist if no unsorted songs
        if os.path.exists(m3u_path):
            try: os.remove(m3u_path)
            except: pass
        log_func(" -> 沒有未分類歌曲")
    
    return len(orphans)
