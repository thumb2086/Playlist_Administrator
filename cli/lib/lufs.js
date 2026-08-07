import fs from 'node:fs';
import path from 'node:path';
import { run, resolveFfmpeg, isInternalPlaylist, readJson, writeJson, sleep } from './util.js';

// Port of lib/services/lufs_service.dart (measure + normalize playlist MP3s)
export class LufsService {
  constructor(config) {
    this.config = config;
  }

  _cacheFile(fmt) {
    return path.join(this.config.basePath, `${fmt}_lufs_cache.json`);
  }

  _load(fmt) {
    const data = readJson(this._cacheFile(fmt), {});
    const out = {};
    for (const [k, v] of Object.entries(data)) out[k] = typeof v === 'number' ? v : parseFloat(v);
    return out;
  }

  _save(fmt, cache) {
    writeJson(this._cacheFile(fmt), cache);
  }

  _resolvePlaylistPath(entry, playlistsPath, basePath, libraryPath) {
    if (!entry) return null;
    if (!entry.includes('.') && !entry.includes('\\') && !entry.includes('/')) return null;
    const resolved = path.join(playlistsPath, entry);
    if (fs.existsSync(resolved)) return resolved;
    if (fs.existsSync(entry)) return entry;
    const fname = entry.replace(/[\\/]/g, '\\').split('\\').pop();
    for (const base of [basePath, libraryPath, playlistsPath]) {
      const cand = path.join(base, fname);
      if (fs.existsSync(cand)) return cand;
    }
    return null;
  }

  getPlaylistMp3Files() {
    const { playlistsPath, basePath, libraryPath } = this.config;
    if (!fs.existsSync(playlistsPath)) return new Set();
    const mp3Files = new Set();
    for (const e of fs.readdirSync(playlistsPath, { withFileTypes: true })) {
      if (!e.isFile()) continue;
      const low = e.name.toLowerCase();
      if (!low.endsWith('.m3u8') && !low.endsWith('.m3u')) continue;
      if (isInternalPlaylist(e.name)) continue;
      try {
        const content = fs.readFileSync(path.join(playlistsPath, e.name), 'utf-8');
        for (const line of content.split('\n')) {
          const trimmed = line.trim();
          if (!trimmed || trimmed.startsWith('#')) continue;
          if (!trimmed.includes('.mp3') && !trimmed.includes('.m4a') && !trimmed.includes('.flac')) continue;
          const resolved = this._resolvePlaylistPath(trimmed, playlistsPath, basePath, libraryPath);
          if (resolved && resolved.toLowerCase().endsWith('.mp3')) {
            mp3Files.add(resolved);
          }
        }
      } catch {}
    }
    return mp3Files;
  }

  async measureAndNormalizePlaylistMp3s({ onLog, onProgress, concurrency = 8, tolerance = 2.0, isCancelled }) {
    const { libraryPath, playlistsPath, basePath } = this.config;
    if (!libraryPath || !playlistsPath) {
      onLog('Library or Playlists path not configured');
      return;
    }
    onLog('掃描歌單中的 MP3 檔案…');
    const playlistFiles = this.getPlaylistMp3Files();
    if (playlistFiles.size === 0) {
      onLog('歌單中沒有 MP3 檔案');
      return;
    }
    onLog(`歌單內共 ${playlistFiles.size} 個 MP3`);

    const cache = this._load('mp3');
    const target = -14.0;
    const needsNormalize = [];
    let skipCount = 0;
    for (const p of playlistFiles) {
      const cached = cache[p];
      if (cached != null && Math.abs(cached - target) <= tolerance) skipCount++;
      else needsNormalize.push(p);
    }
    if (needsNormalize.length === 0) {
      onLog(`所有歌單 MP3 已在 ${target}±${tolerance}LUFS 範圍內 (已快取 ${skipCount} 檔)`);
      return;
    }
    onLog(`需 Normalize/測量: ${needsNormalize.length} 檔 (${skipCount} 檔已合格)`);
    const ffmpeg = resolveFfmpeg(this.config);
    const total = needsNormalize.length;
    let done = 0;
    let lastSave = 0;

    for (let i = 0; i < total; i += concurrency) {
      if (isCancelled && isCancelled()) break;
      const batch = needsNormalize.slice(i, i + concurrency);
      await Promise.all(batch.map((p) => this._normalizeOne(p, ffmpeg, target, cache, onLog, isCancelled)));
      if (isCancelled && isCancelled()) break;
      done += batch.length;
      if (onProgress) onProgress(done, total);
      if (done - lastSave >= 10) {
        this._save('mp3', cache);
        lastSave = done;
        onLog(`  進度: ${done}/${total}`);
      }
    }
    this._save('mp3', cache);
    if (isCancelled && isCancelled()) {
      onLog(`LUFS 已取消（已處理 ${done} 檔）`);
    } else {
      onLog(`完成: ${done} 個檔案已統一至 ${target} LUFS`);
    }
  }

  async _normalizeOne(absPath, ffmpeg, target, cache, onLog, isCancelled) {
    if (!fs.existsSync(absPath)) return;
    const base = absPath.substring(0, absPath.lastIndexOf('.'));
    const tmp = `${base}_tmp.mp3`;
    const name = absPath.split('\\').pop();
    try {
      const result = await run(ffmpeg, [
        '-y', '-i', absPath,
        '-af', `loudnorm=I=${target}:TP=-1:LRA=7`,
        '-c:a', 'libmp3lame', '-q:a', '2', tmp,
      ], { timeout: 600000 });
      if (result.code !== 0 || !fs.existsSync(tmp)) {
        onLog(`  ❌ ${name} normalize 失敗`);
        return;
      }
      let inputLufs = target;
      const m = result.stderr.match(/Input Integrated:\s+([-\d.]+)/);
      if (m) inputLufs = parseFloat(m[1]);
      fs.renameSync(tmp, absPath);
      cache[absPath] = target;
      if (Math.abs(inputLufs - target) > 0.1) {
        onLog(`  ✅ ${name}  (${inputLufs.toFixed(1)} → ${target})`);
      }
    } catch (ex) {
      onLog(`  ⚠️ ${name}: ${ex.message || ex}`);
    }
  }

  cacheConversionLufsFast(m4aPath, lufs) {
    const m4aCache = this._load('m4a');
    if (!(m4aPath in m4aCache) && lufs != null) {
      m4aCache[m4aPath] = lufs;
      this._save('m4a', m4aCache);
    }
  }

  measureOne(path_, onResult, isCancelled) {
    const ffmpeg = resolveFfmpeg(this.config);
    return run(ffmpeg, ['-i', path_, '-af', 'loudnorm=print_format=json', '-f', 'null', '-', '-hide_banner', '-y'], { timeout: 300000 })
      .then((result) => {
        if (result.code !== 0) { onResult(-14.0); return; }
        const stderr = result.stderr;
        const jsonStart = stderr.lastIndexOf('{');
        if (jsonStart >= 0) {
          try {
            const data = JSON.parse(stderr.substring(jsonStart));
            if (data.input_i != null) { onResult(parseFloat(data.input_i)); return; }
          } catch {}
        }
        onResult(-14.0);
      })
      .catch(() => onResult(-14.0));
  }
}
