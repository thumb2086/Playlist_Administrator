import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { LibraryIndex } from './library_index.js';
import { convert as convertAudio } from './audio_converter.js';
import { SpotifyScraper } from './scraper.js';
import { SnapshotManager } from './snapshot.js';
import { LufsService } from './lufs.js';
import { readMetadata } from './metadata.js';
import { PlaylistParser } from './playlist_parser.js';
import { saveConfig } from './config.js';
import { walkDir, stemOf, relativePath, isInternalPlaylist } from './util.js';

// Port of lib/pipeline/pipeline_orchestrator.dart
export class PipelineOrchestrator {
  constructor({ config, onLog, onProgress, isCancelled = () => false }) {
    this.config = config;
    this.onLog = onLog;
    this.onProgress = onProgress;
    this.isCancelled = isCancelled;
    this.totalRemoved = 0;
  }

  async run({ fromStep = 0, toStep } = {}) {
    const steps = [
      ['Convert M4A → MP3', 30.0],
      ['Scrape Spotify playlists', 25.0],
      ['Prune missing tracks', 15.0],
      ['Organize unsorted songs', 10.0],
      ['Enrich metadata', 10.0],
      ['Measure LUFS', 10.0],
    ];
    const end = toStep ?? steps.length;
    let doneWeight = 0;

    for (let i = fromStep; i < end; i++) {
      if (this.isCancelled()) break;
      this.onLog(`--- Step ${i + 1}/${steps.length}: ${steps[i][0]} ---`);
      this.onProgress(0, 100, i);
      try {
        await this._runStep(i, (pct) => {
          const global = Math.round(doneWeight + (pct / 100.0) * steps[i][1]);
          this.onProgress(global, 100, i);
        });
      } catch (e) {
        this.onLog(`  ❌ ${steps[i][0]} 失敗: ${e.message || e}`);
      }
      doneWeight += Math.trunc(steps[i][1]);
    }
    this.onLog(this.isCancelled() ? 'Pipeline 已取消' : 'Pipeline 完成');
  }

  async _runStep(index, progress) {
    switch (index) {
      case 0: await this._stepConvert(progress); break;
      case 1: await this._stepScrape(progress); break;
      case 2: await this._stepPrune(progress); break;
      case 3: await this._stepUnsorted(progress); break;
      case 4: await this._stepMetadata(progress); break;
      case 5: await this._stepMeasureLufs(progress); break;
    }
  }

  async _stepConvert(progress) {
    const config = this.config;
    const m4aDir = config.m4aPath;
    const mp3Dir = config.mp3Path;
    if (!fs.existsSync(m4aDir)) {
      this.onLog(`M4A 資料夾不存在: ${m4aDir}`);
      progress(100);
      return;
    }
    fs.mkdirSync(mp3Dir, { recursive: true });

    let m4aFiles = (await walkDir(m4aDir, { filter: (f) => f.toLowerCase().endsWith('.m4a') }));
    if (m4aFiles.length === 0) {
      const libM4a = await walkDir(config.libraryPath, { filter: (f) => f.toLowerCase().endsWith('.m4a') });
      if (libM4a.length === 0) {
        this.onLog('找不到任何 M4A 檔案');
        progress(100);
        return;
      }
      this.onLog(`在音樂庫根目錄找到 ${libM4a.length} 個 M4A 檔案`);
      m4aFiles = libM4a;
    } else {
      this.onLog(`找到 ${m4aFiles.length} 個 M4A 檔案`);
    }

    const index = new LibraryIndex();
    await index.build(config.libraryPath, this.onLog, { basePath: config.basePath });

    const tasks = [];
    let skipped = 0;
    const totalM4a = m4aFiles.length;
    let scanned = 0;

    for (const m4a of m4aFiles) {
      if (this.isCancelled()) return;

      let existing = index.findMp3ForM4a(m4a, { useMtime: true });
      if (existing) { skipped++; scanned++; this._scanLog(scanned, totalM4a, tasks, skipped); continue; }

      const meta = await readMetadata(m4a, config);
      existing = index.findMp3ForM4a(m4a, { useMtime: true, cachedMeta: meta });
      if (existing) { skipped++; scanned++; this._scanLog(scanned, totalM4a, tasks, skipped); continue; }

      const mp3Name = `${stemOf(m4a)}.mp3`;
      const dest = path.join(config.mp3Path, mp3Name);
      if (fs.existsSync(dest) && fs.statSync(dest).mtimeMs >= fs.statSync(m4a).mtimeMs) {
        skipped++;
        scanned++;
        this._scanLog(scanned, totalM4a, tasks, skipped);
        continue;
      }

      tasks.push({ src: m4a, dest, meta });
      scanned++;
      this._scanLog(scanned, totalM4a, tasks, skipped);
    }

    this.onLog(`待轉檔: ${tasks.length}, 跳過: ${skipped}`);
    if (tasks.length === 0) { progress(100); return; }

    const physicalCores = Math.max(2, Math.min(16, Math.trunc(os.cpus().length / 2)));
    const concurrency = physicalCores;
    let converted = 0;
    let done = 0;
    const lufs = new LufsService(this.config);

    const worker = async () => {
      while (true) {
        if (this.isCancelled()) return;
        const idx = next++;
        if (idx >= tasks.length) return;
        const t = tasks[idx];
        const fname = path.basename(t.src);
        const r = await convertAudio({
          inputPath: t.src, outputPath: t.dest,
          ffmpegPath: config.ffmpegPath || 'ffmpeg',
          meta: t.meta, isCancelled: this.isCancelled,
        });
        if (this.isCancelled()) return;
        done++;
        if (r.ok) {
          converted++;
          lufs.cacheConversionLufsFast(t.src, r.lufs);
        }
        this.onLog(`  [${done}/${tasks.length}] ${r.ok ? '✅' : '❌'} ${fname}`);
        progress((done / tasks.length) * 100);
      }
    };
    let next = 0;
    await Promise.all(Array.from({ length: concurrency }, () => worker()));
    this.onLog(`轉檔完成: ${converted} 個`);
  }

  _scanLog(scanned, total, tasks, skipped) {
    if (scanned % 200 === 0 || scanned === total) {
      this.onLog(`  比對: ${scanned}/${total} (待轉檔 ${tasks.length}，跳過 ${skipped})`);
    }
  }

  async _stepScrape(progress) {
    const config = this.config;
    const urls = Object.keys(config.urlNames);
    if (urls.length === 0) {
      this.onLog('沒有 Spotify URL');
      progress(100);
      return;
    }
    fs.mkdirSync(config.playlistsPath, { recursive: true });

    const scraper = new SpotifyScraper({ log: this.onLog, playlistsPath: config.playlistsPath, libraryPath: config.libraryPath });
    const plNames = await scraper.scrapeAll(urls, config);
    saveConfig(config);

    let totalRemoved = 0;
    for (const plName of plNames) {
      const plFile = path.join(config.playlistsPath, `${plName}.m3u8`);
      if (!fs.existsSync(plFile)) continue;
      try {
        const tracks = PlaylistParser.parseTrackNames(plFile);
        if (tracks.length === 0) continue;
        const removed = SnapshotManager.processPlaylist(config, plName, tracks);
        if (removed > 0) {
          this.onLog(`  📋 ${plName}: 偵測到 ${removed} 首已移除歌曲`);
          totalRemoved += removed;
        }
      } catch (e) {
        this.onLog(`  ⚠️ 無法處理 ${plName} 快照: ${e.message || e}`);
      }
    }
    if (totalRemoved > 0) {
      this.onLog(`  📋 共 ${totalRemoved} 首已移除歌曲被記錄`);
    }
    progress(100);
  }

  async _stepPrune(progress) {
    const plDir = this.config.playlistsPath;
    if (!fs.existsSync(plDir)) {
      this.onLog('播放清單資料夾不存在');
      progress(100);
      return;
    }
    const files = fs.readdirSync(plDir)
      .filter((f) => f.toLowerCase().endsWith('.m3u8') || f.toLowerCase().endsWith('.m3u'))
      .map((f) => path.join(plDir, f));

    this.totalRemoved = 0;
    const totalFiles = files.length;

    for (let i = 0; i < files.length; i++) {
      if (this.isCancelled()) return;
      const f = files[i];
      const baseName = path.basename(f);
      if (isInternalPlaylist(baseName)) {
        this.onLog(`  跳過內部歌單: ${baseName}`);
        progress(((i + 1) / totalFiles) * 100);
        continue;
      }
      try {
        const content = fs.readFileSync(f, 'utf-8').split('\n').map((l) => l.replace(/\r$/, ''));
        const newLines = [];
        let removed = 0;
        const isM3u = content.some((l) => l.includes('#EXTM3U'));

        let j = 0;
        while (j < content.length) {
          const line = content[j];
          if (!line) { j++; continue; }
          if (isM3u && line.startsWith('#EXTINF:')) {
            let k = j + 1;
            while (k < content.length && (!content[k].trim() || content[k].startsWith('#'))) k++;
            if (k < content.length) {
              const pathLine = content[k].trim();
              if (this._trackFileExists(pathLine)) {
                newLines.push(line, content[k]);
              } else {
                removed++;
              }
              j = k + 1;
            } else {
              newLines.push(line);
              j++;
            }
            continue;
          }
          if (line.startsWith('#') || !line.trim()) {
            newLines.push(line);
          } else {
            if (this._trackFileExists(line.trim())) newLines.push(line);
            else removed++;
          }
          j++;
        }

        if (removed > 0) {
          fs.writeFileSync(f, `${newLines.join('\n')}\n`, 'utf-8');
          this.totalRemoved += removed;
          this.onLog(`  ${baseName}: 移除 ${removed} 首`);
        }
      } catch (e) {
        this.onLog(`  ⚠️ 無法處理 ${baseName}: ${e.message || e}`);
      }
      progress(((i + 1) / totalFiles) * 100);
    }
    this.onLog(`Prune 完成，共移除 ${this.totalRemoved} 首`);
  }

  _trackFileExists(entry) {
    if (!entry.includes('.') && !entry.includes('\\')) return true;
    const relToPl = path.join(this.config.playlistsPath, entry);
    if (fs.existsSync(relToPl)) return true;
    if (fs.existsSync(entry)) return true;
    const fname = entry.replace(/[\\/]/g, '\\').split('\\').pop();
    for (const base of [this.config.basePath, this.config.libraryPath, this.config.playlistsPath]) {
      if (fs.existsSync(path.join(base, fname))) return true;
    }
    return false;
  }

  async _stepUnsorted(progress) {
    const plDir = this.config.playlistsPath;
    if (!fs.existsSync(plDir)) { progress(100); return; }

    const allPlaylistSongs = new Set();
    for (const e of fs.readdirSync(plDir, { withFileTypes: true })) {
      if (!e.isFile()) continue;
      const low = e.name.toLowerCase();
      if (!low.endsWith('.m3u8') && !low.endsWith('.m3u')) continue;
      if (isInternalPlaylist(e.name)) continue;
      try {
        const names = PlaylistParser.parseTrackNames(path.join(plDir, e.name));
        for (const n of names) {
          allPlaylistSongs.add(n.replace(/\.[^.]+$/, '').toLowerCase());
        }
      } catch {}
    }

    const unsortedFiles = [];
    const libDir = this.config.libraryPath;
    if (fs.existsSync(libDir)) {
      const files = await walkDir(libDir, { filter: (f) => /\.(mp3|m4a|flac)$/i.test(f) });
      for (const f of files) {
        const low = f.toLowerCase();
        if (low.includes('podcast_downloads') || low.includes('podcast_rag')) continue;
        const stem = stemOf(f).toLowerCase();
        if (!allPlaylistSongs.has(stem)) unsortedFiles.push(f);
      }
    }

    const unsortedPath = path.join(this.config.playlistsPath, '_Unsorted.m3u8');
    const existingStems = new Set();
    if (fs.existsSync(unsortedPath)) {
      try {
        const existing = PlaylistParser.parseTrackEntries(unsortedPath);
        for (const e of existing) {
          existingStems.add(stemOf(e).toLowerCase());
        }
      } catch {}
    }

    const newUnsorted = unsortedFiles.filter((f) => !existingStems.has(stemOf(f).toLowerCase()));
    if (newUnsorted.length === 0) {
      this.onLog(`未分類歌曲共 ${unsortedFiles.length} 首，無新增`);
      progress(100);
      return;
    }

    let sb = '';
    if (existingStems.size === 0) sb += '#EXTM3U\n';
    const absPlPath = path.dirname(unsortedPath);
    for (const filePath of newUnsorted) {
      const absFilePath = path.resolve(filePath);
      sb += `#EXTINF:-1,${stemOf(filePath)}\n`;
      sb += `${relativePath(absFilePath, absPlPath)}\n`;
    }

    fs.writeFileSync(unsortedPath, sb, { flag: existingStems.size === 0 ? 'w' : 'a', encoding: 'utf-8' });
    this.onLog(`已為 ${newUnsorted.length} 首新未分類歌曲更新清單 (共 ${unsortedFiles.length} 首)`);
    progress(100);
  }

  async _stepMetadata(progress) {
    const config = this.config;
    if (!config.enableMetadataEnrichment) {
      this.onLog('Metadata enrichment 未啟用，跳過');
      progress(100);
      return;
    }
    this.onLog('Metadata enrichment 已啟用，開始掃描…');
    // Scan files missing metadata, fill from spotify_cache / filename, apply via ffmpeg
    const files = [];
    for (const f of await walkDir(config.libraryPath, { filter: (x) => /\.(mp3|m4a|flac)$/i.test(x) })) {
      const meta = await readMetadata(f, config);
      if (!meta.title || !meta.artist) files.push(f);
    }
    if (files.length === 0) {
      this.onLog('✅ 所有檔案都有完整 metadata');
    } else {
      this.onLog(`🎵 找到 ${files.length} 個檔案缺少 metadata，開始補充…`);
      let success = 0;
      const total = files.length;
      for (let i = 0; i < files.length; i++) {
        if (this.isCancelled()) return;
        try {
          const ok = await this._enrichFile(files[i], config);
          if (ok) success++;
        } catch (e) {
          this.onLog(`  ❌ ${path.basename(files[i])}: ${e.message || e}`);
        }
        if (onProgress) progress(((i + 1) / total) * 100);
        if (i % 10 === 9 || i === files.length - 1) {
          this.onLog(`  進度: ${i + 1}/${total} (成功: ${success})`);
        }
      }
      this.onLog(`🎉 Metadata 補充完成: ${success}/${total}`);
    }
    progress(100);
  }

  async _enrichFile(filePath, config) {
    const stem = stemOf(filePath);
    const meta = await readMetadata(filePath, config);
    let title = meta.title;
    let artist = meta.artist;
    let album;
    let year;
    let coverUrl;

    const cacheDir = path.join(config.basePath, 'spotify_cache');
    if (fs.existsSync(cacheDir)) {
      const exact = path.join(cacheDir, `${stem}.json`);
      let cached = null;
      if (fs.existsSync(exact)) {
        try { cached = JSON.parse(fs.readFileSync(exact, 'utf-8')); } catch {}
      }
      if (!cached) {
        try {
          for (const f of fs.readdirSync(cacheDir)) {
            if (!f.endsWith('.json')) continue;
            const data = JSON.parse(fs.readFileSync(path.join(cacheDir, f), 'utf-8'));
            const cacheTitle = String(data.title || '').toLowerCase().replaceAll(' ', '');
            const stemLower = stem.toLowerCase().replaceAll(' ', '');
            if (cacheTitle.includes(stemLower) || stemLower.includes(cacheTitle)) { cached = data; break; }
          }
        } catch {}
      }
      if (cached) {
        title = title || cached.title;
        artist = artist || cached.artist;
        album = album || cached.album;
        const rd = cached.release_date;
        if (rd && rd.length >= 4) year = rd.substring(0, 4);
        coverUrl = coverUrl || cached.cover_url;
      }
    }

    if ((!title || !title.length) && stem.includes(' - ')) {
      const parts = stem.split(' - ');
      if (parts.length >= 2) {
        artist = parts[0].trim();
        title = parts.slice(1).join(' - ').trim();
      }
    }
    if (!title || !title.length) title = stem;

    const ext = filePath.toLowerCase().split('.').pop();
    const tmpPath = `${filePath}_tmp.${ext}`;
    const cmd = ['ffmpeg', '-y', '-i', filePath, '-c', 'copy'];
    if (title && title.length) cmd.push('-metadata', `title=${title}`);
    if (artist && artist.length) cmd.push('-metadata', `artist=${artist}`);
    if (album && album.length) cmd.push('-metadata', `album=${album}`);
    if (year && year.length) cmd.push('-metadata', `date=${year}`);
    if (coverUrl) {
      // Best effort: fetch cover and embed as APIC when mpeg audio
      try {
        const resp = await fetch(coverUrl);
        if (resp.ok && /^(mp3|m4a)$/i.test(ext)) {
          const buf = Buffer.from(await resp.arrayBuffer());
          const tmpCover = path.join(process.env.TEMP || '.', `pa_cover_${Date.now()}.jpg`);
          fs.writeFileSync(tmpCover, buf);
          cmd.push('-i', tmpCover, '-map', '0:a', '-map', '1:v', '-c:v', 'mjpeg', '-disposition:v', 'attached_pic');
          const { execFile } = await import('node:child_process');
          const { promisify } = await import('node:util');
          await promisify(execFile)(cmd[0], cmd.slice(1), { windowsHide: true });
          try { fs.unlinkSync(tmpCover); } catch {}
          try {
            fs.unlinkSync(filePath);
            fs.renameSync(tmpPath, filePath);
          } catch {}
          this.onLog(`  ✅ 已更新 metadata+封面: ${path.basename(filePath)}`);
          return true;
        }
      } catch {}
    }
    cmd.push(tmpPath);
    const { execFile } = await import('node:child_process');
    const { promisify } = await import('node:util');
    try {
      const { stdout } = await promisify(execFile)(cmd[0], cmd.slice(1), { windowsHide: true, timeout: 120000 });
      void stdout;
      fs.unlinkSync(filePath);
      fs.renameSync(tmpPath, filePath);
      this.onLog(`  ✅ 已更新 metadata: ${path.basename(filePath)}`);
      return true;
    } catch {
      try { if (fs.existsSync(tmpPath)) fs.unlinkSync(tmpPath); } catch {}
      this.onLog(`  ⚠️ 寫入 metadata 失敗: ${path.basename(filePath)}`);
      return false;
    }
  }

  async _stepMeasureLufs(progress) {
    try {
      const svc = new LufsService(this.config);
      await svc.measureAndNormalizePlaylistMp3s({
        onLog: this.onLog,
        onProgress: (done, total) => progress(total > 0 ? (done / total) * 100 : 0),
        concurrency: 8,
        tolerance: 2.0,
        isCancelled: this.isCancelled,
      });
    } catch (e) {
      this.onLog(`LUFS 異常: ${e.message || e}`);
    }
    progress(100);
  }
}
