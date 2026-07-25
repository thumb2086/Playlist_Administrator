import sys
import os
import json
import tempfile
import traceback
import re
import subprocess
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
            'preferredquality': '320',
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

    use_dab_lossless = config.get('dab_use_lossless', False) and target_format == 'flac'
    use_dab_metadata = config.get('dab_use_metadata', False) and target_format == 'flac'
    dab_credentials = None
    if use_dab_lossless:
        dab_email = config.get('dab_email', '')
        dab_password = config.get('dab_password', '')
        if dab_email and dab_password:
            dab_credentials = {'email': dab_email, 'password': dab_password}

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
            }), file_list=[], config=config,
            use_dab_lossless=use_dab_lossless, use_dab_metadata=use_dab_metadata,
            dab_credentials=dab_credentials
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
    model = args[2] if len(args) > 2 else 'whisper-large-v3'
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
        if ffmpeg_path and os.path.exists(audio_path):
            size_mb = os.path.getsize(audio_path) / (1024*1024)
            if size_mb > 5:
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
    except: pass

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
                for s in range(0, int(duration), 600):
                    cp = os.path.join(tmpdir, f'chunk_{base}_{len(chunks)}.flac')
                    subprocess.run([ffmpeg_path, '-y', '-i', file_to_send, '-ss', str(s), '-t', '600',
                        '-ar', '16000', '-ac', '1', '-c:a', 'flac', cp], capture_output=True, timeout=180)
                    chunks.append(cp)
                if chunks: chunk_files = chunks
        except: pass

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
        w('Content-Type: audio/flac\r\n\r\n')
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

                if sc in (429, 500, 502, 503):
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
            else:
                err_msg += 'unknown error (no response)'
            err_msg += ' [' + str(file_size // 1024) + 'KB]'
            emit_json({'type': 'error', 'message': err_msg[:300]})
            # Also write to log file
            try:
                log_dir = os.path.expanduser(r'~\Music\Spotube\logs')
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

def cmd_youtube_subs(args):
    """Search YouTube and download Chinese subtitles for a podcast episode"""
    query = args[0]
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
            emit_json({'type': 'error', 'message': '找不到符合的 YouTube 影片'})
            return
        video_id = unique[0]
        emit_json({'type': 'log', 'message': f'  ✅ 找到影片: https://youtube.com/watch?v={video_id}'})
    except Exception as e:
        emit_json({'type': 'error', 'message': f'搜尋失敗: {e}'})
        return

    # Step 2: Download subtitles
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    srt_path = output_path.replace('.mp3', '').replace('.m4a', '').replace('.wav', '') + '.srt'

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
            emit_json({'type': 'error', 'message': '下載字幕失敗（無可用字幕）'})
    except Exception as e:
        emit_json({'type': 'error', 'message': f'下載字幕異常: {e}'})


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
        else:
            emit_json({'type': 'error', 'message': f'Unknown command: {command}'})
            return 1
    except Exception as e:
        emit_json({'type': 'error', 'message': str(e), 'traceback': traceback.format_exc()})
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
