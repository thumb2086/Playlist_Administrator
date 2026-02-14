import os
import glob
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.library import parse_playlist, get_normalized_tokens
from utils.config import load_config
from utils.helpers import sanitize_filename

import argparse
import difflib
import re
from mutagen.flac import FLAC

def get_file_metadata(flac_path):
    """Get metadata dictionary from FLAC file"""
    try:
        audio = FLAC(flac_path)
        return {
            'artist': audio.get('ARTIST', [''])[0],
            'title': audio.get('TITLE', [''])[0],
            'album': audio.get('ALBUM', [''])[0]
        }
    except:
        return None

def normalize_internal(text):
    """Simple normalization for substring checks"""
    if not text: return ""
    text = text.lower()
    # Keep characters and numbers
    text = re.sub(r'[^a-z0-9\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+', '', text)
    return text

def main():
    parser = argparse.ArgumentParser(description='Fix existing FLAC filenames to match playlist entries')
    parser.add_argument('--dry-run', action='store_true', help='Simulation mode: show changes without renaming')
    parser.add_argument('--verbose', action='store_true', help='Show more details about matching process')
    args = parser.parse_args()
    
    config = load_config()
    library_path = config.get('library_path', 'data/Music')
    playlists_path = config.get('playlists_path', 'data/Playlists')
    
    if args.dry_run:
        print("🧪 [模擬模式] 僅顯示預計變更，不會實際更名檔案")
    
    print(f"🔍 正在尋找播放清單中的正確歌曲名稱...")
    
    all_playlist_songs = set()
    playlist_files = glob.glob(os.path.join(playlists_path, "*.m3u8")) + glob.glob(os.path.join(playlists_path, "*.m3u"))
    
    for pl_file in playlist_files:
        songs = parse_playlist(pl_file)
        all_playlist_songs.update(songs)
    
    # Pre-process playlist entries
    playlist_meta = []
    for song_name in all_playlist_songs:
        playlist_meta.append({
            'original': song_name,
            'normalized': normalize_internal(song_name),
            'tokens': set(get_normalized_tokens(song_name))
        })
            
    print(f"✅ 已載入 {len(all_playlist_songs)} 首播放清單歌曲名稱")
    
    flac_pattern = os.path.join(library_path, "**", "*.flac")
    flac_files = glob.glob(flac_pattern, recursive=True)
    
    print(f"🔍 發現 {len(flac_files)} 個 FLAC 檔案，開始對比命名...")
    
    renamed_count = 0
    skipped_count = 0
    
    # Critical Stopwords to avoid weak matches (e.g. "On", "You", "4")
    STOPWORDS = {'you', 'me', 'the', 'a', 'an', 'i', 'to', 'and', 'my', 'in', 'it', 'is', 'on', '4', 'u', 'now', 'your'}
    
    for flac_path in flac_files:
        old_filename = os.path.basename(flac_path)
        name_no_ext = os.path.splitext(old_filename)[0]
        
        # 1. Skip if current filename already matches something well
        old_tokens = set(get_normalized_tokens(name_no_ext))
        current_match_found = False
        if old_tokens:
            for pl in playlist_meta:
                if old_tokens.issubset(pl['tokens']):
                    if len(old_tokens) / len(pl['tokens']) >= 0.3:
                        current_match_found = True
                        break
        if current_match_found: continue

        # 2. Extract Metadata for safe matching
        metadata = get_file_metadata(flac_path)
        m_title = metadata['title'] if metadata else ""
        norm_m_title = normalize_internal(m_title)
        
        best_pl = None
        best_score = 0
        best_confidence = 0
        
        for pl in playlist_meta:
            # SAFETY LAYER 1: If we have a metadata title, it MUST be a substring of the playlist entry
            if norm_m_title and len(norm_m_title) > 1:
                if norm_m_title not in pl['normalized']:
                    continue
            
            # Match tokens
            m_combined = f"{metadata['artist']} {metadata['title']}" if metadata and metadata['title'] else name_no_ext
            search_tokens = set(get_normalized_tokens(m_combined))
            common = search_tokens & pl['tokens']
            
            # SAFETY LAYER 2: Exclude stopwords from min-match-count
            solid_common = [t for t in common if t not in STOPWORDS and len(t) > 1]
            if not solid_common and search_tokens != pl['tokens']:
                continue
                
            # Scoring
            score = len(common) + len(solid_common) * 2
            similarity = difflib.SequenceMatcher(None, pl['normalized'], normalize_internal(m_title or name_no_ext)).ratio()
            score += similarity * 10 
            
            if score > best_score:
                best_score = score
                best_pl = pl
                best_confidence = similarity
        
        # FINAL SAFETY: High score and high similarity required
        if best_pl and best_score >= 10.0 and best_confidence > 0.6:
            new_base = sanitize_filename(best_pl['original'])
            new_filename = new_base + ".flac"
            
            # 額外安全檢查：如果原本的檔名已經包含「歌手 - 歌名」，而新檔名只有「歌名」
            # 則維持原樣不改 (除非原本的歌手名稱完全錯誤)
            if " - " in old_filename and " - " not in new_filename:
                if metadata and metadata['artist'] and metadata['title']:
                    # 檢查舊檔名是否已經包含正確的歌手與歌名 tokens
                    m_tokens = set(get_normalized_tokens(f"{metadata['artist']} {metadata['title']}"))
                    if m_tokens.issubset(old_tokens):
                        # 舊檔名已經很完整且正確了，不要改成沒歌手的簡短名
                        continue

            if old_filename != new_filename:
                new_path = os.path.join(os.path.dirname(flac_path), new_filename)
                if os.path.exists(new_path) and old_filename.lower() != new_filename.lower():
                    skipped_count += 1
                else:
                    try:
                        if not args.dry_run:
                            os.rename(flac_path, new_path)
                            lrc_old = flac_path.replace(".flac", ".lrc")
                            lrc_new = new_path.replace(".flac", ".lrc")
                            if os.path.exists(lrc_old): 
                                try: os.rename(lrc_old, lrc_new)
                                except: pass
                        else:
                            print(f"  🧪 預計更名: {old_filename} -> {new_filename} (相似度: {best_confidence:.1%})")
                        renamed_count += 1
                    except Exception as e:
                        print(f"  ❌ 失敗: {old_filename} -> {str(e)}")
        elif args.verbose and best_pl:
            print(f"  🔍 略過弱匹配: {old_filename} -> {best_pl['original']} (相似: {best_confidence:.1%}, 分數: {best_score:.1f})")
            
    print(f"\n🎉 處理完成! (模式: {'模擬' if args.dry_run else '實際執行'})")
    print(f"   - {'預計' if args.dry_run else '成功'}更名: {renamed_count} 首")
    print(f"   - 跳過/失敗: {skipped_count} 首")
    print(f"   - 檔名已經正確: {len(flac_files) - renamed_count - skipped_count} 首")

if __name__ == "__main__":
    main()
