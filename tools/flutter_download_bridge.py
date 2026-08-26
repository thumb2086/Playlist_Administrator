import sys
import os
import json
import tempfile
import traceback
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

# Force UTF-8 output to avoid cp950 encoding errors with Chinese characters
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def emit_json(data):
    try:
        print(json.dumps(data, ensure_ascii=False), flush=True)
    except UnicodeEncodeError:
        print(json.dumps(data, ensure_ascii=True), flush=True)


def cmd_rss_list(args):
    import requests
    url = args[0]
    resp = requests.get(url, timeout=30, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    ns = {'itunes': 'http://www.itunes.com/dtds/podcast-1.0.dtd'}
    channel = root.find('channel')
    if channel is None:
        channel = root
    episodes = []
    for item in channel.findall('.//item'):
        title_el = item.find('title')
        title = title_el.text.strip() if title_el is not None and title_el.text else ''
        pub_date_el = item.find('pubDate')
        pub_date = pub_date_el.text.strip() if pub_date_el is not None and pub_date_el.text else ''
        enclosure = item.find('enclosure')
        audio_url = enclosure.get('url', '') if enclosure is not None else ''
        audio_type = enclosure.get('type', '') if enclosure is not None else ''
        duration_el = item.find('{http://www.itunes.com/dtds/podcast-1.0.dtd}duration')
        duration = ''
        if duration_el is not None and duration_el.text:
            duration = duration_el.text.strip()
        description_el = item.find('description')
        description = ''
        if description_el is not None and description_el.text:
            description = description_el.text.strip()
        episodes.append({
            'title': title,
            'pub_date': pub_date,
            'audio_url': audio_url,
            'audio_type': audio_type,
            'duration': duration,
            'description': description,
        })
    channel_title_el = channel.find('title')
    channel_title = channel_title_el.text.strip() if channel_title_el is not None and channel_title_el.text else ''
    emit_json({'type': 'rss_list', 'title': channel_title, 'episodes': episodes})


def cmd_rss_get_audio(args):
    """Get audio URL from a podcast RSS by episode index"""
    url = args[0]
    index = int(args[1])
    import requests
    resp = requests.get(url, timeout=30, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    items = root.findall('.//item')
    if index >= len(items):
        emit_json({'type': 'error', 'message': f'Episode index {index} out of range'})
        return
    item = items[index]
    enclosure = item.find('enclosure')
    if enclosure is None:
        emit_json({'type': 'error', 'message': 'No enclosure found'})
        return
    audio_url = enclosure.get('url', '')
    title_el = item.find('title')
    title = title_el.text.strip() if title_el is not None and title_el.text else f'episode_{index}'
    emit_json({'type': 'rss_audio', 'title': title, 'audio_url': audio_url})


def cmd_rss_download(args):
    """Download a single podcast episode"""
    url = args[0]
    output_path = args[1]
    import requests
    resp = requests.get(url, stream=True, timeout=60, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    resp.raise_for_status()
    total = int(resp.headers.get('content-length', 0))
    downloaded = 0
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if not chunk:
                break
            f.write(chunk)
            downloaded += len(chunk)
            if total > 0:
                pct = downloaded / total * 100
                emit_json({'type': 'progress', 'downloaded': downloaded, 'total': total, 'percent': round(pct, 1)})
    emit_json({'type': 'complete', 'path': output_path})


def cmd_download_song(args):
    """Download a song using existing core/downloader.py"""
    song_name = args[0]
    library_path = args[1]
    audio_format = args[2] if len(args) > 2 else 'mp3'
    from utils.config import CONFIG_DIR, load_config
    config = load_config()
    from core.downloader import download_song
    result = download_song(song_name, library_path, audio_format, lambda msg: emit_json({
        'type': 'log', 'message': msg
    }), file_list=[], config=config)
    if result:
        emit_json({'type': 'complete', 'path': result})
    else:
        emit_json({'type': 'error', 'message': f'Failed to download: {song_name}'})


def cmd_download_youtube(args):
    """Download audio from a YouTube URL"""
    url = args[0]
    output_path = args[1]
    audio_format = args[2] if len(args) > 2 else 'mp3'

    import yt_dlp
    from utils.helpers import sanitize_filename

    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            speed = d.get('speed', 0)
            pct = round(downloaded / total * 100, 1) if total > 0 else 0
            emit_json({'type': 'progress', 'downloaded': downloaded, 'total': total, 'percent': pct, 'speed': speed})
        elif d['status'] == 'finished':
            emit_json({'type': 'log', 'message': 'Processing audio...'})

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path.replace(f'.{audio_format}', '.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'extract_audio': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': audio_format,
            'preferredquality': '0',
        }],
        'progress_hooks': [progress_hook],
        'keepvideo': False,
        'windowsfilenames': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        final_path = output_path
        if os.path.exists(final_path):
            emit_json({'type': 'complete', 'path': final_path})
        else:
            base = os.path.splitext(os.path.basename(output_path))[0]
            dir_path = os.path.dirname(output_path)
            candidates = [f for f in os.listdir(dir_path) if f.startswith(base) and f.endswith(f'.{audio_format}')]
            if candidates:
                emit_json({'type': 'complete', 'path': os.path.join(dir_path, candidates[0])})
            else:
                emit_json({'type': 'error', 'message': 'Output file not found'})
    except Exception as e:
        emit_json({'type': 'error', 'message': str(e)})


def cmd_stream_resolve(args):
    """Resolve a playable audio URL for a song query via yt-dlp.

    Prints a JSON line with the resolved direct audio URL (bestaudio).
    The Dart side serves it through a local HTTP proxy (or plays directly).
    """
    query = args[0]
    import yt_dlp

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f'ytsearch1:{query}', download=False)
            entry = info['entries'][0] if info.get('entries') else info
            # 1. Direct URL field (works for most formats).
            url = entry.get('url')
            # 2. From formats list — find bestaudio with a usable URL.
            if not url:
                formats = entry.get('formats', [])
                for fmt in reversed(formats):
                    furl = fmt.get('url')
                    if furl and fmt.get('acodec', 'none') != 'none':
                        url = furl
                        break
            # 3. Last resort: try ffmpeg_url (manifest-based formats).
            if not url:
                url = entry.get('manifest_url')
            if not url:
                emit_json({'type': 'error', 'message': f'no stream URL for: {query}'})
                return
            emit_json({
                'type': 'complete',
                'url': url,
                'title': entry.get('title', ''),
                'ext': entry.get('ext', ''),
                'duration': entry.get('duration', 0),
            })
    except Exception as e:
        emit_json({'type': 'error', 'message': str(e)})


def cmd_stream_download(args):
    """Download a song via yt-dlp with ranking (Spotube-style algorithm)."""
    query = args[0]
    output_path = args[1]
    isrc = args[2] if len(args) > 2 else ''

    import yt_dlp
    import re

    # Parse query: "Title - Artist" or just "Title"
    parts = query.split(' - ', 1)
    track_title = parts[0].strip().lower()
    track_artist = parts[1].strip().lower() if len(parts) > 1 else ''

    # Spotube-style ranking regex
    official_re = re.compile(r'official\s*(video|audio|music|lyric|visualizer)', re.I)

    def rank(entries):
        scored = []
        for e in entries:
            score = 0
            title = (e.get('title') or '').lower()
            channel = (e.get('channel') or e.get('uploader') or '').lower()
            duration = e.get('duration') or 0
            # Penalize very short (<30s) or very long (>600s) — likely not the song.
            if duration and (duration < 30 or duration > 600):
                score -= 3
            # Penalize non-music channels (news, clips, talk).
            non_music_re = re.compile(r'新聞|news|clip|shorts|民視|TVBS|中天|東森', re.I)
            if non_music_re.search(channel) or non_music_re.search(title):
                score -= 5
            # +3 if title contains track name (fuzzy: remove spaces/punct for CJK).
            clean_title = re.sub(r'[\s\-_·・]', '', title)
            clean_track = re.sub(r'[\s\-_·・]', '', track_title)
            if clean_track and clean_track in clean_title:
                score += 3
            # +1 if uploader matches artist
            if track_artist and track_artist in channel:
                score += 1
            # +1 per artist name in title
            if track_artist and track_artist in title:
                score += 1
            # +1 official flag
            if official_re.search(title):
                score += 1
            # +2 bonus: official + title match
            if official_re.search(title) and clean_track in clean_title:
                score += 2
            scored.append((e, score))
        scored.sort(key=lambda x: -x[1])
        return [e for e, s in scored if s >= 2]  # minimum score threshold

    # Search strategy: try multiple queries, pick best match.
    search_queries = []
    if isrc:
        search_queries.append(f'ytsearch5:{isrc}')
    # Full query (title - artist)
    search_queries.append(f'ytsearch5:{query}')
    # Title only (YouTube struggles with "title artist" for CJK)
    search_queries.append(f'ytsearch5:{track_title} official audio')
    search_queries.append(f'ytsearch5:{track_title} official')
    # Artist + title order swap
    if track_artist:
        search_queries.append(f'ytsearch5:{track_artist} {track_title}')

    ydl_opts = {
        'format': 'bestaudio',
        'outtmpl': output_path + '.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'extract_audio': False,
        'postprocessors': [],
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
        },
        'socket_timeout': 60,
        'retries': 2,
    }

    best = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for sq in search_queries:
                info = ydl.extract_info(sq, download=False)
                entries = info.get('entries', [])
                if not entries:
                    continue
                ranked = rank(entries)
                # Try each ranked result until one downloads successfully.
                for candidate in ranked:
                    url = candidate.get('webpage_url') or candidate.get('url', '')
                    title = candidate.get('title', '')
                    try:
                        ydl.download([url])
                        best = candidate
                        break
                    except Exception as dl_err:
                        emit_json({'type': 'log', 'message': f'skip: {title[:40]} ({dl_err})'})
                        continue
                if best:
                    break
            if not best:
                emit_json({'type': 'error', 'message': f'no downloadable result for: {query}'})
                return
            title = best.get('title', '')
            emit_json({'type': 'log', 'message': f'downloaded: {title[:50]}'})

        # Find the downloaded raw file.
        raw_path = ''
        for ext in ['.webm', '.m4a', '.opus', '.mp4', '.mp3', '.ogg']:
            if os.path.exists(output_path + ext):
                raw_path = output_path + ext
                break
        if not raw_path:
            emit_json({'type': 'error', 'message': 'downloaded file not found'})
            return

        mp3_path = output_path + '.mp3'
        # If already mp3, done.
        if raw_path == mp3_path:
            emit_json({'type': 'complete', 'path': mp3_path, 'title': title})
            return

        # Convert to mp3 with ffmpeg (-ac 2 for stereo).
        import subprocess
        ffmpeg = 'ffmpeg'
        for p in [r'C:\ffmpeg\bin\ffmpeg.exe', r'C:\tools\ffmpeg.exe']:
            if os.path.exists(p):
                ffmpeg = p
                break
        try:
            result = subprocess.run([
                ffmpeg, '-y', '-i', raw_path,
                '-vn', '-acodec', 'libmp3lame', '-q:a', '0', '-ac', '2',
                mp3_path,
            ], capture_output=True, timeout=120)
            if result.returncode == 0 and os.path.exists(mp3_path):
                os.remove(raw_path)
                emit_json({'type': 'complete', 'path': mp3_path, 'title': title})
                return
        except Exception as e:
            emit_json({'type': 'log', 'message': f'ffmpeg convert failed: {e}'})

        # Fallback: return raw file as-is.
        emit_json({'type': 'complete', 'path': raw_path, 'title': title})
    except Exception as e:
        emit_json({'type': 'error', 'message': str(e)})


def cmd_download_spotdl(args):
    """Download a song via spotDL to a separate spotdl_downloads folder"""
    song_url = args[0]
    output_dir = args[1]
    audio_format = args[2] if len(args) > 2 else 'mp3'
    output_template = os.path.join(output_dir, '{artist} - {title}.{ext}')
    from core.downloader import download_with_spotdl
    config = {'format': audio_format, 'ffmpeg_path': 'bin/ffmpeg.exe', 'overwrite': 'skip'}
    result = download_with_spotdl(song_url, output_template, config)
    if result:
        emit_json({'type': 'complete', 'path': str(result)})
    else:
        emit_json({'type': 'error', 'message': f'spotDL failed: {song_url}'})


def cmd_list_missing(args):
    """List all songs missing a specific format (mp3/flac) across all playlists"""
    target_format = args[0] if args else 'mp3'
    from utils.config import load_config, get_data_file
    import glob
    import hashlib

    config = load_config()
    library_path = config.get('library_path', '')
    if not library_path:
        emit_json({'type': 'error', 'message': 'Library path not configured'})
        return

    search_pattern = os.path.join(library_path, "**", "*")
    all_files = glob.glob(search_pattern, recursive=True)
    audio_files = [f for f in all_files if f.lower().endswith(('.mp3', '.m4a', '.flac', '.wav'))]

    from core.library import build_library_index, find_song_exact_format, parse_playlist, is_internal_playlist_name
    library_index = build_library_index(audio_files)

    playlist_dir = os.path.join(library_path, 'playlists')
    if not os.path.exists(playlist_dir):
        emit_json({'type': 'error', 'message': 'Playlists directory not found'})
        return

    playlist_files = [os.path.join(playlist_dir, f) for f in os.listdir(playlist_dir)
                      if f.endswith('.m3u8') and not is_internal_playlist_name(f)]

    # Load failed FLAC cache (only relevant for flac format)
    failed_cache = {}
    if target_format == 'flac':
        try:
            cache_file = get_data_file('failed_flac.json')
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    failed_cache = json.load(f)
        except:
            pass

    missing_songs = []
    seen = set()

    for pl_file in playlist_files:
        playlist_name = os.path.splitext(os.path.basename(pl_file))[0]
        songs = parse_playlist(pl_file)
        for song_name in songs:
            norm_name = song_name.strip().lower()
            song_key = hashlib.md5(norm_name.encode('utf-8')).hexdigest()

            if target_format == 'flac' and song_key in failed_cache:
                continue

            if find_song_exact_format(song_name, target_format, library_index):
                continue

            if song_key in seen:
                continue
            seen.add(song_key)

            artist_hint = ''
            if ' - ' in song_name:
                parts = song_name.split(' - ', 1)
                artist_hint = parts[1].strip()

            missing_songs.append({
                'name': song_name,
                'playlist': playlist_name,
                'artist_hint': artist_hint,
            })

    emit_json({'type': 'missing_list', 'format': target_format, 'songs': missing_songs, 'total_missing': len(missing_songs)})


def cmd_batch_download(args):
    """Download missing songs in specified format"""
    target_format = args[0] if len(args) > 0 else 'mp3'
    songs_json = args[1] if len(args) > 1 else '[]'
    songs = json.loads(songs_json)

    from utils.config import load_config, get_data_file
    config = load_config()
    library_path = config.get('library_path', '')
    if not library_path:
        emit_json({'type': 'error', 'message': 'Library path not configured'})
        return

    total = len(songs)
    successful = 0
    failed = 0

    emit_json({'type': 'batch_start', 'total': total, 'format': target_format})

    for i, song in enumerate(songs):
        song_name = song['name']
        emit_json({'type': 'batch_progress', 'index': i, 'total': total,
                   'song': song_name, 'format': target_format,
                   'percent': round(i / total * 100, 1) if total > 0 else 0})

        from core.downloader import download_song
        result = download_song(
            song_name, library_path, target_format, lambda msg: emit_json({
                'type': 'log', 'message': msg
            }), file_list=[], config=config
        )

        if result and os.path.exists(result):
            successful += 1
            emit_json({'type': 'log', 'message': f'✅ {song_name} - {target_format.upper()} 下載成功'})
            if target_format == 'flac':
                import hashlib
                norm_name = song_name.strip().lower()
                song_key = hashlib.md5(norm_name.encode('utf-8')).hexdigest()
                try:
                    cache_file = get_data_file('failed_flac.json')
                    if os.path.exists(cache_file):
                        with open(cache_file, 'r', encoding='utf-8') as f:
                            fc = json.load(f)
                        if song_key in fc:
                            del fc[song_key]
                            with open(cache_file, 'w', encoding='utf-8') as f:
                                json.dump(fc, f, ensure_ascii=False, indent=2)
                except:
                    pass
        else:
            failed += 1
            emit_json({'type': 'log', 'message': f'❌ {song_name} - {target_format.upper()} 下載失敗'})

    emit_json({'type': 'batch_complete', 'successful': successful, 'failed': failed, 'format': target_format})


def cmd_normalize_mp3_lufs(args):
    """Normalize MP3s deviating from -14 LUFS. Handles sentinel values (-99) by measuring first."""
    import shutil

    from utils.config import load_config, get_data_file
    config = load_config()
    library_path = config.get('library_path', '')
    if not library_path:
        emit_json({'type': 'error', 'message': 'Library path not configured'})
        return

    cache_file = get_data_file('mp3_lufs_cache.json')
    if not os.path.exists(cache_file):
        emit_json({'type': 'log', 'message': 'MP3 LUFS 快取不存在，跳過 normalize'})
        return

    with open(cache_file, 'r', encoding='utf-8') as f:
        cache = json.load(f)

    target = -14.0
    ffmpeg_path = shutil.which('ffmpeg') or config.get('ffmpeg_path', 'ffmpeg')
    sentinel = -99

    # Phase 1: measure sentinel values and find files that need normalization
    need_measure = {k: v for k, v in cache.items() if abs(float(v) - sentinel) < 0.5}
    need_normalize = {k: float(v) for k, v in cache.items() if abs(float(v) - target) > 2.0 and k not in need_measure}

    if need_measure:
        emit_json({'type': 'log', 'message': f'測量 {len(need_measure)} 個未快取的 MP3...'})
        done = 0
        for rel_path in need_measure:
            abs_path = os.path.join(library_path, rel_path)
            if not os.path.exists(abs_path):
                cache[rel_path] = target
                done += 1
                continue
            # Quick measurement with ffmpeg loudnorm analysis (first 30s)
            cmd = [ffmpeg_path, '-t', '30', '-i', abs_path,
                   '-af', 'loudnorm=print_format=json',
                   '-f', 'null', 'NUL', '-hide_banner', '-y']
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=120,
                                   encoding='utf-8', errors='replace')
                out = r.stderr
                json_start = out.rfind('{')
                if json_start >= 0:
                    try:
                        data, _ = json.JSONDecoder().raw_decode(out[json_start:])
                        input_i = data.get('input_i')
                        if input_i is not None:
                            measured = float(input_i)
                            cache[rel_path] = measured
                            if abs(measured - target) > 2.0:
                                need_normalize[rel_path] = measured
                            done += 1
                            if done % 25 == 0:
                                emit_json({'type': 'progress', 'percent': round(done / len(need_measure) * 100, 1)})
                            continue
                    except:
                        pass
            except:
                pass
            cache[rel_path] = target
            done += 1

    if not need_normalize:
        emit_json({'type': 'log', 'message': '所有 MP3 已在 -14±2 LUFS 範圍內，無需 normalize'})
        # Save updated cache
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        return

    emit_json({'type': 'log', 'message': f'Normalize {len(need_normalize)} 個偏離 -14 的 MP3...'})
    total = len(need_normalize)
    done = 0

    for rel_path, val in need_normalize.items():
        abs_path = os.path.join(library_path, rel_path)
        if not os.path.exists(abs_path):
            continue
        base, ext = os.path.splitext(abs_path)
        tmp = base + '_tmp' + ext
        cmd = [ffmpeg_path, '-y', '-i', abs_path,
               '-af', f'loudnorm=I={target}:TP=-1:LRA=7',
               '-c:a', 'libmp3lame', '-q:a', '2', tmp]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=300)
            if r.returncode == 0 and os.path.exists(tmp):
                os.replace(tmp, abs_path)
                cache[rel_path] = target
                emit_json({'type': 'log', 'message': f'  ✅ {rel_path}  ({val:.1f} → -14)'})
            else:
                emit_json({'type': 'log', 'message': f'  ❌ {rel_path} normalize 失敗'})
        except Exception as e:
            emit_json({'type': 'log', 'message': f'  ⚠️ {rel_path}: {str(e)[:60]}'})
        done += 1
        emit_json({'type': 'progress', 'percent': round(done / total * 100, 1)})

    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    emit_json({'type': 'log', 'message': f'完成: 測量 {len(need_measure)} 個, normalize {done} 個'})


def cmd_groq_transcribe(args):
    """Transcribe audio via curl.exe + ffmpeg chunking"""
    audio_path = args[0]
    api_keys_csv = args[1]
    model = args[2] if len(args) > 2 else 'whisper-large-v3-turbo'
    language = args[3] if len(args) > 3 else 'zh'

    import os, time, subprocess, json, tempfile, io, shutil

    keys = [k.strip() for k in api_keys_csv.split(',') if k.strip()]
    if not keys:
        emit_json({'type': 'error', 'message': 'No API keys provided'})
        return

    curl_path = os.path.join(os.environ.get('SystemRoot', 'C:\\Windows'), 'System32', 'curl.exe')
    if not os.path.exists(curl_path):
        emit_json({'type': 'error', 'message': 'curl.exe not found'})
        return

    temp_file = None
    file_to_send = audio_path
    ffmpeg_path = shutil.which('ffmpeg')

    try:
        # Convert to flac only for small files. For large files (>20MB),
        # skip conversion and chunk the original MP3 directly — FLAC is
        # lossless and actually LARGER than MP3, defeating the purpose.
        if ffmpeg_path and os.path.exists(audio_path):
            file_size = os.path.getsize(audio_path)
            ext = os.path.splitext(audio_path)[1].lower()
            if ext != '.flac' and file_size <= 20 * 1024 * 1024:
                emit_json({'type': 'progress', 'percent': 5, 'message': 'Compressing...'})
                tmp = tempfile.NamedTemporaryFile(suffix='.flac', delete=False)
                tmp.close()
                r = subprocess.run(
                    [ffmpeg_path, '-y', '-i', audio_path, '-ar', '16000', '-ac', '1',
                     '-map', '0:a', '-c:a', 'flac', '-compression_level', '0', tmp.name],
                    capture_output=True, timeout=180
                )
                if r.returncode == 0 and os.path.exists(tmp.name) and os.path.getsize(tmp.name) > 0:
                    file_to_send = tmp.name
                    temp_file = tmp.name
                else:
                    emit_json({'type': 'log', 'message': f'FLAC conversion failed, using original'})
    except Exception as e:
        emit_json({'type': 'log', 'message': f'FLAC conversion error: {e}'})

    # Chunk: split if > 20MB after conversion
    chunk_files = [file_to_send]
    if ffmpeg_path and os.path.exists(file_to_send) and os.path.getsize(file_to_send) > 20 * 1024 * 1024:
        try:
            emit_json({'type': 'progress', 'percent': 8, 'message': 'Splitting audio...'})
            fp = shutil.which('ffprobe') or ffmpeg_path.replace('ffmpeg', 'ffprobe')
            dur = subprocess.run([fp, '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', file_to_send],
                capture_output=True, text=True, timeout=30)
            duration = float(dur.stdout.strip()) if dur.stdout.strip() else 0
            if duration > 0:
                base = os.path.basename(file_to_send).rsplit('.', 1)[0]
                tmpdir = tempfile.gettempdir()
                chunks = []
                chunk_sec = 300  # 5 minutes per chunk for safety
                for s in range(0, int(duration), chunk_sec):
                    cp = os.path.join(tmpdir, f'chunk_{base}_{len(chunks)}.flac')
                    subprocess.run([ffmpeg_path, '-y', '-i', file_to_send, '-ss', str(s), '-t', str(chunk_sec),
                        '-ar', '16000', '-ac', '1', '-c:a', 'flac', cp], capture_output=True, timeout=180)
                    if os.path.exists(cp) and os.path.getsize(cp) > 0:
                        # If chunk still > 20MB, split further into 60s pieces
                        if os.path.getsize(cp) > 20 * 1024 * 1024:
                            sub_dur = subprocess.run([fp, '-v', 'error', '-show_entries', 'format=duration',
                                '-of', 'default=noprint_wrappers=1:nokey=1', cp],
                                capture_output=True, text=True, timeout=30)
                            sub_total = float(sub_dur.stdout.strip()) if sub_dur.stdout.strip() else chunk_sec
                            os.unlink(cp)
                            for ss in range(0, int(sub_total), 60):
                                sp = os.path.join(tmpdir, f'chunk_{base}_{len(chunks)}.flac')
                                subprocess.run([ffmpeg_path, '-y', '-i', file_to_send,
                                    '-ss', str(s + ss), '-t', '60',
                                    '-ar', '16000', '-ac', '1', '-c:a', 'flac', sp],
                                    capture_output=True, timeout=180)
                                if os.path.exists(sp) and os.path.getsize(sp) > 0:
                                    chunks.append(sp)
                        else:
                            chunks.append(cp)
                if chunks: chunk_files = chunks
        except Exception as e:
            emit_json({'type': 'log', 'message': f'Split failed: {e}'})

    def upload_file(fpath, try_key):
        """Upload a single file via curl, return (status, body)"""
        boundary = '----' + str(int(time.time() * 1000000))
        body_buf = io.BytesIO()
        def w(s): body_buf.write(s.encode())
        w('--' + boundary + '\r\n')
        w('Content-Disposition: form-data; name="model"\r\n\r\n')
        w(model + '\r\n')
        w('--' + boundary + '\r\n')
        w('Content-Disposition: form-data; name="response_format"\r\n\r\n')
        w('verbose_json\r\n')
        w('--' + boundary + '\r\n')
        w('Content-Disposition: form-data; name="temperature"\r\n\r\n')
        w('0.0\r\n')
        if language:
            w('--' + boundary + '\r\n')
            w('Content-Disposition: form-data; name="language"\r\n\r\n')
            w(language + '\r\n')
        w('--' + boundary + '\r\n')
        w('Content-Disposition: form-data; name="file"; filename="' + os.path.basename(fpath) + '"\r\n')
        w('Content-Type: ' + _content_type(fpath) + '\r\n\r\n')
        with open(fpath, 'rb') as fh:
            body_buf.write(fh.read())
        w('\r\n--' + boundary + '--\r\n')

        body_file = tempfile.NamedTemporaryFile(suffix='.tmp', delete=False)
        body_file.write(body_buf.getvalue())
        body_file.close()

        cmd = [curl_path, '-s', '-S', '-i', '--ssl', '--max-time', '600',
            '-H', 'Authorization: Bearer ' + try_key,
            '-H', 'Content-Type: multipart/form-data; boundary=' + boundary,
            '-H', 'User-Agent: ' + ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
            '-H', 'Connection: close']
        # Read Windows system proxy from registry
        proxy_url = None
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Internet Settings') as key:
                enabled = winreg.QueryValueEx(key, 'ProxyEnable')[0]
                server = winreg.QueryValueEx(key, 'ProxyServer')[0]
                if enabled and server:
                    proxy_url = 'http://' + server
                    emit_json({'type': 'log', 'message': 'Proxy: ' + proxy_url})
        except: pass
        # Fallback to env vars
        if not proxy_url:
            for e in ['HTTPS_PROXY', 'https_proxy', 'HTTP_PROXY', 'http_proxy']:
                if e in os.environ:
                    proxy_url = os.environ[e]
                    break
        if proxy_url:
            cmd.extend(['--proxy', proxy_url])
        cmd.extend(['--data-binary', '@' + body_file.name,
            'https://api.groq.com/openai/v1/audio/transcriptions'])

        result = subprocess.run(cmd, capture_output=True, timeout=610)
        os.unlink(body_file.name)
        out = result.stdout.decode('utf-8', errors='replace')
        if not out.strip():
            # curl errors (e.g. connection failure) go to stderr; without
            # an HTTP response, sc=0 and the caller must treat this as a
            # transient retryable failure.
            err = result.stderr.decode('utf-8', errors='replace').strip()
            return (0, err or 'curl no response')
        # Find final status line and body (skip 100 Continue + proxy header)
        lines = out.split('\r\n')
        sc = 0
        sc_idx = 0
        for j, line in enumerate(lines):
            if line.startswith('HTTP/'):
                parts = line.split(' ')
                if len(parts) >= 2:
                    try:
                        code = int(parts[1])
                        if code != 100:  # skip 100 Continue
                            sc = code
                            sc_idx = j
                    except: pass
        # Find body: it's after the blank line that follows the final HTTP status
        # The response looks like:
        # HTTP/1.1 200 Connection established  (proxy)
        # (blank line)
        # HTTP/1.1 200 OK  (groq)
        # headers...
        # (blank line)
        # body
        body_start = out.rfind('\r\n\r\n')
        body = out[body_start+4:] if body_start >= 0 else out
        return (sc, body)

    results = []
    for ci, cf in enumerate(chunk_files):
        # Safety: skip chunks that are still too large
        if os.path.exists(cf) and os.path.getsize(cf) > 24 * 1024 * 1024:
            emit_json({'type': 'log', 'message': f'Chunk {ci+1} too large ({os.path.getsize(cf)//1024//1024}MB), skipping'})
            continue
        if len(chunk_files) > 1:
            emit_json({'type': 'progress', 'percent': 10 + ci * 80 // len(chunk_files),
                'message': 'Chunk ' + str(ci+1) + '/' + str(len(chunk_files)) + '...'})

        last_error = None
        last_status = 0
        last_body = ''
        chunk_ok = False

        for attempt in range(len(keys) + 2):
            try_key = keys[attempt % len(keys)]
            try:
                emit_json({'type': 'progress', 'percent': 15, 'message': 'Uploading...'})
                sc, body = upload_file(cf, try_key)
                last_status = sc
                last_body = body[:300]

                if sc == 200:
                    try:
                        j = json.loads(body)
                        text = j.get('text', '')
                    except (json.JSONDecodeError, ValueError):
                        emit_json({'type': 'log', 'message': f'Chunk {ci+1}: HTTP 200 but invalid JSON body ({len(body)} bytes), retrying...'})
                        time.sleep(3)
                        continue
                    results.append(text)
                    chunk_ok = True
                    if len(chunk_files) <= 1:
                        emit_json({'type': 'progress', 'percent': 100})
                        emit_json({'type': 'transcription', 'text': text})
                        if temp_file: os.unlink(temp_file)
                        for c in chunk_files:
                            if c != audio_path and c != temp_file:
                                try: os.unlink(c)
                                except: pass
                        return
                    break

                if sc in (429, 500, 502, 503) or sc == 0:
                    # sc=0: no HTTP response at all (connection reset /
                    # timeout / proxy hiccup) — retry like other transient
                    # failures instead of failing the episode immediately.
                    emit_json({'type': 'log', 'message': 'HTTP ' + str(sc) + ', retry ' + str(attempt+1) + '/' + str(len(keys)+2)})
                    time.sleep(5 + attempt * 3)
                    continue

                # Non-retryable error
                try: j = json.loads(body); msg = j.get('error', {}).get('message', body[:200])
                except: msg = body[:200]
                emit_json({'type': 'error', 'message': '[' + str(sc) + '] ' + msg})
                if temp_file: os.unlink(temp_file)
                for c in chunk_files:
                    if c != audio_path and c != temp_file:
                        try: os.unlink(c)
                        except: pass
                return

            except Exception as e:
                last_error = e
                if attempt < len(keys) + 1:
                    emit_json({'type': 'log', 'message': 'Retry ' + str(attempt+1) + ': ' + str(e)[:60]})
                    time.sleep(3 + attempt * 2)
                    continue
                break

        if not chunk_ok:
            # Build detailed error message
            file_size = os.path.getsize(cf) if os.path.exists(cf) else 0
            err_msg = 'Chunk failed: '
            if last_error:
                err_msg += str(last_error)[:150]
            elif last_status:
                try:
                    j = json.loads(last_body)
                    err_msg += 'HTTP ' + str(last_status) + ' - ' + j.get('error', {}).get('message', last_body[:100])
                except:
                    err_msg += 'HTTP ' + str(last_status) + ' (' + last_body[:100] + ')'
            elif last_body:
                err_msg += 'no HTTP response: ' + last_body[:100]
            else:
                err_msg += 'unknown error (no response)'
            err_msg += ' [' + str(file_size // 1024) + 'KB]'
            emit_json({'type': 'error', 'message': err_msg[:300]})
            # Also write to log file
            try:
                cfg = None
                try:
                    from utils.config import load_config
                    cfg = load_config()
                except Exception:
                    pass
                if cfg and cfg.get('base_path'):
                    log_dir = os.path.join(cfg['base_path'], 'logs')
                else:
                    log_dir = os.path.expanduser(r'~\Music\playlist-admin\logs')
                os.makedirs(log_dir, exist_ok=True)
                with open(os.path.join(log_dir, 'stt_errors.log'), 'a', encoding='utf-8') as lf:
                    lf.write(f'\n--- {time.strftime("%Y-%m-%d %H:%M:%S")} ---\n')
                    lf.write(f'File: {audio_path}\n')
                    lf.write(f'Status: {last_status}\n')
                    lf.write(f'Body: {last_body[:500]}\n')
                    lf.write(f'Error: {str(last_error)[:300] if last_error else "none"}\n')
                    lf.write(f'Keys tried: {len(keys) + 2}\n')
            except: pass
            if temp_file: os.unlink(temp_file)
            for c in chunk_files:
                if c != audio_path and c != temp_file:
                    try: os.unlink(c)
                    except: pass
            return

    if len(results) > 1:
        emit_json({'type': 'transcription', 'text': '\n\n---\n\n'.join(results)})
    if temp_file: os.unlink(temp_file)
    for c in chunk_files:
        if c != audio_path and c != temp_file:
            try: os.unlink(c)
            except: pass

def _content_type(fpath):
    """Map file extension to a MIME type. Must match the actual bytes
    sent, otherwise Groq returns HTTP 502 service_unavailable."""
    ext = os.path.splitext(fpath)[1].lower()
    return {
        '.flac': 'audio/flac',
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        '.ogg': 'audio/ogg',
        '.m4a': 'audio/mp4',
        '.mp4': 'audio/mp4',
    }.get(ext, 'audio/flac')


def _clean_query(text):
    """Clean search query: remove special chars that break YouTube search."""
    text = text.replace('_', ' ').replace('\u3010', '').replace('\u3011', '').replace('\uff5c', ' ')
    text = text.replace('\uff08', ' ').replace('\uff09', ' ').replace('\u300a', '').replace('\u300b', '')
    text = text.replace('[', ' ').replace(']', ' ').replace('"', '').replace('\'', '').replace('?', '')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def cmd_youtube_subs(args):
    """Search YouTube and download Chinese subtitles for a podcast episode"""
    query = _clean_query(args[0])
    output_path = args[1] if len(args) > 1 else ''
    if not output_path:
        emit_json({'type': 'error', 'message': 'No output path'})
        return

    import yt_dlp
    import urllib.parse
    import requests
    import re
    import shutil

    youtube_dl = shutil.which('yt-dlp') or 'yt-dlp'

    # Step 1: Search YouTube
    emit_json({'type': 'log', 'message': f'🔍 搜尋 YouTube: {query}'})
    try:
        search_url = 'https://www.youtube.com/results?' + urllib.parse.urlencode({'search_query': query})
        r = requests.get(search_url, timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        vids = re.findall(r'watch\?v=([a-zA-Z0-9_-]{11})', r.text)
        unique = list(dict.fromkeys(vids))
        if not unique:
            emit_json({'type': 'not_found', 'message': '找不到符合的 YouTube 影片'})
            return
        video_id = unique[0]
        emit_json({'type': 'log', 'message': f'  ✅ 找到影片: https://youtube.com/watch?v={video_id}'})
    except Exception as e:
        emit_json({'type': 'error', 'message': f'搜尋失敗: {e}'})
        return

    # Step 2: Download subtitles
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    # Replace only the final extension. String-wide .replace('.wav', '')
    # would also strip '.wav' from the podcast folder name (e.g.
    # "科技浪 Tech.wav") and save the SRT into a wrong directory.
    srt_path = os.path.splitext(output_path)[0] + '.srt'

    cookie_file = r'C:\Users\CPXru\Desktop\thumb\大拇哥實驗室\cookies.txt'
    if not os.path.exists(cookie_file):
        cookie_file = ''

    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['zh-TW', 'zh-Hant', 'zh', 'zh-Hans', 'en'],
            'subtitlesformat': 'srt',
            'outtmpl': srt_path.replace('.srt', '.%(ext)s'),
            'windowsfilenames': True,
            'sleep_interval_requests': 3,
            'extractor_args': {'youtube': {'sleep_interval': ['3']}},
        }
        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f'https://www.youtube.com/watch?v={video_id}'])

        # Find the actual SRT file (yt-dlp may add language suffix)
        base = srt_path.replace('.srt', '')
        candidates = []
        for f in os.listdir(os.path.dirname(srt_path)):
            if f.startswith(os.path.basename(base)):
                candidates.append(os.path.join(os.path.dirname(srt_path), f))

        srt_found = None
        for c in candidates:
            if c.endswith('.srt'):
                srt_found = c
                break

        if srt_found and os.path.exists(srt_found):
            # Rename to clean name
            if srt_found != srt_path:
                os.replace(srt_found, srt_path)
            emit_json({'type': 'log', 'message': f'  ✅ 字幕已儲存: {srt_path}'})
            emit_json({'type': 'complete', 'path': srt_path})
        else:
            emit_json({'type': 'not_found', 'message': '下載字幕失敗（無可用字幕）'})
    except Exception as e:
        emit_json({'type': 'error', 'message': f'下載字幕異常: {e}'})


def _rag_script(name):
    """Locate a rag script next to this bridge (assets/tools/rag in release,
    repo rag/ in dev / CLI), or relative to cwd."""
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [
        os.path.join(here, 'rag', name),                      # temp extracted / bundle copy
        os.path.join(here, '..', 'rag', name),                # repo: tools/../rag
        os.path.join(os.getcwd(), 'rag', name),               # CLI: cwd = repo root
        os.path.join(os.getcwd(), '..', 'rag', name),
        os.path.join(os.getcwd(), '..', '..', 'rag', name),
        os.environ.get('PA_ROOT', '') and os.path.join(os.environ['PA_ROOT'], 'rag', name),
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return ''


def cmd_rag_query(args):
    """Query the podcast RAG: python rag/query.py "<q>" --answer --json --out <tmp>"""
    script = _rag_script('query.py')
    if not script:
        emit_json({'type': 'error', 'message': '找不到 rag/query.py（release 需打包 assets/tools/rag）'})
        return
    question = args[0]
    topk = args[1] if len(args) > 1 else '8'
    show = args[2] if len(args) > 2 else ''
    out_file = os.path.join(tempfile.gettempdir(), f'pa_rag_{int(time.time() * 1000)}.json')
    cmd = [sys.executable, script, question, '--no-full', '--topk', str(topk), '--answer', '--json', '--out', out_file]
    if show:
        cmd += ['--show', show]
    env = dict(os.environ)
    env['BASE_PATH'] = env.get('BASE_PATH', '')
    try:
        r = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace',
                           env=env, timeout=900, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if not os.path.exists(out_file):
            emit_json({'type': 'error', 'message': (r.stderr or r.stdout or '無輸出').strip()[-500:]})
            return
        with open(out_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        os.unlink(out_file)
    except Exception as e:
        emit_json({'type': 'error', 'message': f'rag-query 執行失敗: {e}'})
        return
    emit_json({'type': 'rag_result', 'data': data})


def cmd_rag_build(args):
    """Incremental RAG build: python rag/build_db.py"""
    script = _rag_script('build_db.py')
    if not script:
        emit_json({'type': 'error', 'message': '找不到 rag/build_db.py（release 需打包 assets/tools/rag）'})
        return
    cmd = [sys.executable, script]
    if '--reset' in args:
        cmd.append('--reset')
    cmd.extend(['--batch', '64', '--workers', '8'])
    env = dict(os.environ)
    env['BASE_PATH'] = env.get('BASE_PATH', '')
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                encoding='utf-8', errors='replace', env=env,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line:
                emit_json({'type': 'log', 'message': line})
        proc.wait(timeout=3600)
        emit_json({'type': 'complete', 'message': 'RAG 索引更新完成'})
    except Exception as e:
        emit_json({'type': 'error', 'message': f'rag-build 執行失敗: {e}'})


def main():
    if len(sys.argv) < 2:
        emit_json({'type': 'error', 'message': 'No command specified'})
        return 1

    command = sys.argv[1]
    args = sys.argv[2:]

    try:
        if command == 'rss-list':
            cmd_rss_list(args)
        elif command == 'rss-get-audio':
            cmd_rss_get_audio(args)
        elif command == 'rss-download':
            cmd_rss_download(args)
        elif command == 'download-song':
            cmd_download_song(args)
        elif command == 'download-youtube':
            cmd_download_youtube(args)
        elif command == 'download-spotdl':
            cmd_download_spotdl(args)
        elif command == 'groq-transcribe':
            cmd_groq_transcribe(args)
        elif command == 'list-missing':
            cmd_list_missing(args)
        elif command == 'batch-download':
            cmd_batch_download(args)
        elif command == 'normalize-mp3-lufs':
            cmd_normalize_mp3_lufs(args)
        elif command == 'youtube-subs':
            cmd_youtube_subs(args)
        elif command == 'stream-resolve':
            cmd_stream_resolve(args)
        elif command == 'stream-download':
            cmd_stream_download(args)
        elif command == 'rag-query':
            cmd_rag_query(args)
        elif command == 'rag-build':
            cmd_rag_build(args)
        else:
            emit_json({'type': 'error', 'message': f'Unknown command: {command}'})
            return 1
    except Exception as e:
        emit_json({'type': 'error', 'message': str(e), 'traceback': traceback.format_exc()})
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
