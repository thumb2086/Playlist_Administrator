import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { spawn } from 'node:child_process';
import { run, runStream, sleep, normalizeFileName, stemOf } from './util.js';

const CACHE_FILE = 'podcast_processed_cache.json';
const SRT_LANGS = ['zh-TW', 'zh-Hant', 'zh', 'zh-Hans', 'en'];

// ---------- RSS ----------
function parseRss(xml) {
  const items = [];
  const itemRe = /<item>([\s\S]*?)<\/item>/g;
  let m;
  while ((m = itemRe.exec(xml)) != null) {
    const block = m[1];
    const title = (block.match(/<title>([\s\S]*?)<\/title>/) || [])[1] || '';
    const pubDate = (block.match(/<pubDate>([\s\S]*?)<\/pubDate>/) || [])[1] || '';
    const enclosure = block.match(/<enclosure[^>]*\/?>/);
    let audioUrl = '';
    let audioType = '';
    if (enclosure) {
      const u = enclosure[0].match(/url="\s*([^"]+)"/);
      const t = enclosure[0].match(/type="([^"]+)"/);
      if (u) audioUrl = decodeXml(u[1]);
      if (t) audioType = t[1];
    }
    const duration = (block.match(/<itunes:duration>([\s\S]*?)<\/itunes:duration>/) || [])[1] || '';
    const description = (block.match(/<description>([\s\S]*?)<\/description>/) || [])[1] || '';
    items.push({
      title: decodeXml(title),
      pub_date: decodeXml(pubDate),
      audio_url: audioUrl,
      audio_type: audioType,
      duration: decodeXml(duration),
      description: decodeXml(description),
    });
  }
  const titleMatch = xml.match(/<channel>[\s\S]*?<title>([\s\S]*?)<\/title>/);
  return {
    title: titleMatch ? decodeXml(titleMatch[1]) : '',
    episodes: items,
  };
}

function decodeXml(s) {
  return s
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&apos;/g, "'")
    .trim();
}

function guessExtension(url) {
  try {
    const p = new URL(url).pathname.toLowerCase();
    for (const ext of ['mp3', 'm4a', 'wav', 'ogg', 'flac', 'aac']) {
      if (p.endsWith(`.${ext}`)) return ext;
    }
  } catch {}
  return 'mp3';
}

export class PodcastService {
  constructor(basePath) {
    this.basePath = basePath;
  }

  podcastDir(podcastName) {
    const sub = podcastName ? podcastName.replace(/[<>:"/\\|?*]/g, '_') : '';
    const dir = sub
      ? path.join(this.basePath, 'podcast_downloads', sub)
      : path.join(this.basePath, 'podcast_downloads');
    fs.mkdirSync(dir, { recursive: true });
    return dir;
  }

  async fetchEpisodes(rssUrl) {
    const resp = await fetch(rssUrl, {
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
      signal: AbortSignal.timeout(30000),
    });
    if (!resp.ok) throw new Error(`RSS HTTP ${resp.status}`);
    const xml = await resp.text();
    return parseRss(xml);
  }

  async downloadEpisode(rssUrl, index, podcastName) {
    const result = await this.fetchEpisodes(rssUrl);
    const ep = result.episodes[index];
    if (!ep || !ep.audio_url) throw new Error('No audio URL found');
    const name = normalizeFileName(ep.title || `episode_${index}`);
    const ext = guessExtension(ep.audio_url);
    const outDir = this.podcastDir(podcastName);
    const outputPath = path.join(outDir, `${name}.${ext}`);
    if (fs.existsSync(outputPath)) return false;

    const resp = await fetch(ep.audio_url, {
      signal: AbortSignal.timeout(600000),
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
    });
    if (!resp.ok) throw new Error(`Download HTTP ${resp.status}`);
    const total = parseInt(resp.headers.get('content-length') || '0', 10);
    let downloaded = 0;
    let lastPct = -1;
    const ws = fs.createWriteStream(outputPath + '.part');
    const reader = resp.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      ws.write(value);
      downloaded += value.length;
      if (total > 0) {
        const pct = Math.trunc(downloaded / total * 100);
        if (pct !== lastPct) {
          lastPct = pct;
          process.stdout.write(`\r  ⬇️ ${pct}%`);
        }
      }
    }
    ws.end();
    if (total > 0 && lastPct !== 100) process.stdout.write('\r  ⬇️ 100%');
    process.stdout.write('\n');
    await new Promise((r) => ws.on('finish', r));
    fs.renameSync(outputPath + '.part', outputPath);
    return true;
  }

  async downloadSubtitles(episodeTitle, podcastName, onLog) {
    const query = `${episodeTitle} ${podcastName}`;
    const outDir = this.podcastDir(podcastName);
    const safeName = normalizeFileName(episodeTitle);
    const outputPath = path.join(outDir, `${safeName}.mp3`);

    if (fs.existsSync(outputPath.replace(/\.mp3$/, '.srt'))) {
      onLog('⏭️ 已有字幕，跳過');
      return 'found';
    }

    onLog(`🔍 搜尋 YouTube: ${query}`);
    let videoId = null;
    try {
      const searchUrl = 'https://www.youtube.com/results?' + new URLSearchParams({ search_query: query });
      const resp = await fetch(searchUrl, {
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
        signal: AbortSignal.timeout(15000),
      });
      const html = await resp.text();
      const vids = [...html.matchAll(/watch\?v=([a-zA-Z0-9_-]{11})/g)].map((m) => m[1]);
      const unique = [...new Set(vids)];
      if (unique.length === 0) {
        onLog('❌ 找不到符合的 YouTube 影片');
        return 'not_found';
      }
      videoId = unique[0];
      onLog(`  ✅ 找到影片: https://youtube.com/watch?v=${videoId}`);
    } catch (e) {
      onLog(`❌ 搜尋失敗: ${e.message}`);
      return 'failed';
    }

    // Download subtitles via yt-dlp
    const srtPath = outputPath.replace(/\.mp3$/, '.srt');
    fs.mkdirSync(path.dirname(srtPath), { recursive: true });
    const outtmpl = srtPath.replace(/\.srt$/, '.%(ext)s');
    const ytdlp = process.env.YTDLP_PATH || 'yt-dlp';
    const args = [
      '--quiet', '--no-warnings',
      '--skip-download',
      '--write-subs', '--write-auto-subs',
      '--sub-langs', SRT_LANGS.join(','),
      '--sub-format', 'srt',
      '--output', outtmpl,
      '--windows-filenames',
      '--sleep-requests', '3',
      `https://www.youtube.com/watch?v=${videoId}`,
    ];
    const cookieFile = path.join(os.homedir(), 'Desktop', 'thumb', '大拇哥實驗室', 'cookies.txt');
    if (fs.existsSync(cookieFile)) args.push('--cookies', cookieFile);

    const result = await run(ytdlp, args, { timeout: 180000 });
    if (result.code !== 0) {
      onLog(`❌ 下載字幕失敗（yt-dlp exit ${result.code}）`);
      return 'failed';
    }

    // Find the SRT (may have language suffix)
    let srtFound = null;
    try {
      const base = srtPath.replace(/\.srt$/, '');
      for (const f of fs.readdirSync(path.dirname(srtPath))) {
        if (f.startsWith(path.basename(base)) && f.toLowerCase().endsWith('.srt')) {
          srtFound = path.join(path.dirname(srtPath), f);
          break;
        }
      }
    } catch {}
    if (srtFound && fs.existsSync(srtFound)) {
      if (srtFound !== srtPath) fs.renameSync(srtFound, srtPath);
      onLog(`  ✅ 字幕已儲存: ${srtPath}`);
      return 'found';
    }
    onLog('❌ 下載字幕失敗（無可用字幕）');
    return 'not_found';
  }

  async searchPodcasts(query) {
    const url = `https://itunes.apple.com/search?term=${encodeURIComponent(query)}&media=podcast&limit=20`;
    const resp = await fetch(url, {
      headers: { 'User-Agent': 'PlaylistAdministrator/2.0' },
      signal: AbortSignal.timeout(30000),
    });
    if (resp.status !== 200) throw new Error(`搜尋失敗 (${resp.status})`);
    const data = await resp.json();
    return (data.results || [])
      .map((r) => ({
        name: r.collectionName || '',
        feedUrl: r.feedUrl || '',
        artist: r.artistName || '',
        artworkUrl: r.artworkUrl100 || '',
        episodeCount: r.trackCount || 0,
      }))
      .filter((r) => r.feedUrl);
  }
}

// ---------- Groq transcription (chunking + fetch) ----------
async function transcribeAudio(audioPath, keys, model, language, onLog) {
  const ffmpeg = process.env.FFMPEG_PATH || 'ffmpeg';
  let fileToSend = audioPath;
  let tempFile = null;
  const size = fs.existsSync(audioPath) ? fs.statSync(audioPath).size : 0;

  // Convert to flac for small files
  if (size > 0 && size <= 20 * 1024 * 1024 && !audioPath.toLowerCase().endsWith('.flac')) {
    const tmp = path.join(os.tmpdir(), `pa_conv_${Date.now()}_${Math.random().toString(36).slice(2)}.flac`);
    const r = await run(ffmpeg, ['-y', '-i', audioPath, '-ar', '16000', '-ac', '1', '-map', '0:a', '-c:a', 'flac', '-compression_level', '0', tmp], { timeout: 180000 });
    if (r.code === 0 && fs.existsSync(tmp) && fs.statSync(tmp).size > 0) {
      fileToSend = tmp;
      tempFile = tmp;
    }
  }

  // Chunk >20MB into 5-min pieces
  let chunkFiles = [fileToSend];
  if (size > 20 * 1024 * 1024) {
    try {
      onLog('Splitting audio...');
      const dur = await run('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', fileToSend], { timeout: 30000 });
      const duration = parseFloat((dur.stdout || '').trim());
      if (duration > 0) {
        const base = path.basename(fileToSend).replace(/\.[^.]+$/, '');
        const chunks = [];
        const chunkSec = 300;
        for (let s = 0; s < Math.floor(duration); s += chunkSec) {
          const cp = path.join(os.tmpdir(), `chunk_${base}_${chunks.length}.flac`);
          const r = await run(ffmpeg, ['-y', '-i', fileToSend, '-ss', String(s), '-t', String(chunkSec), '-ar', '16000', '-ac', '1', '-c:a', 'flac', cp], { timeout: 300000 });
          void r;
          if (fs.existsSync(cp) && fs.statSync(cp).size > 0) chunks.push(cp);
        }
        if (chunks.length > 0) chunkFiles = chunks;
      }
    } catch {}
  }

  const results = [];
  for (let ci = 0; ci < chunkFiles.length; ci++) {
    const cf = chunkFiles[ci];
    if (fs.existsSync(cf) && fs.statSync(cf).size > 24 * 1024 * 1024) {
      onLog(`Chunk ${ci + 1} too large, skipping`);
      continue;
    }
    if (chunkFiles.length > 1) onLog(`Chunk ${ci + 1}/${chunkFiles.length}...`);
    const keyList = keys.split(',').map((k) => k.trim()).filter(Boolean);
    for (let attempt = 0; attempt < keyList.length + 2; attempt++) {
      const tryKey = keyList[attempt % keyList.length];
      try {
        const fd = new FormData();
        fd.append('model', model);
        fd.append('response_format', 'verbose_json');
        fd.append('temperature', '0.0');
        if (language) fd.append('language', language);
        const buf = fs.readFileSync(cf);
        fd.append('file', new Blob([buf], { type: contentType(cf) }), path.basename(cf));
        const resp = await fetch('https://api.groq.com/openai/v1/audio/transcriptions', {
          method: 'POST',
          headers: { Authorization: `Bearer ${tryKey}` },
          body: fd,
          signal: AbortSignal.timeout(600000),
        });
        if (resp.status === 200) {
          const j = await resp.json();
          results.push(j.text || '');
          break;
        }
        if ([429, 500, 502, 503].includes(resp.status)) {
          onLog(`HTTP ${resp.status}, retry ${attempt + 1}/${keyList.length + 2}`);
          await sleep(5000 + attempt * 3000);
          continue;
        }
        const body = await resp.text();
        let msg = body;
        try { msg = JSON.parse(body).error?.message || body; } catch {}
        throw new Error(`[${resp.status}] ${msg}`);
      } catch (e) {
        if (e.message?.startsWith('[')) throw e;
        if (attempt < keyList.length + 1) {
          onLog(`Retry ${attempt + 1}: ${String(e.message || e).slice(0, 60)}`);
          await sleep(3000 + attempt * 2000);
          continue;
        }
        throw e;
      }
    }
  }

  if (tempFile) { try { fs.unlinkSync(tempFile); } catch {} }
  for (const c of chunkFiles) {
    if (c !== audioPath && c !== tempFile) { try { fs.unlinkSync(c); } catch {} }
  }
  return results.join('\n\n---\n\n');
}

function contentType(fpath) {
  const ext = path.extname(fpath).toLowerCase();
  return {
    '.flac': 'audio/flac', '.mp3': 'audio/mpeg', '.wav': 'audio/wav',
    '.ogg': 'audio/ogg', '.m4a': 'audio/mp4', '.mp4': 'audio/mp4',
  }[ext] || 'audio/flac';
}

// ---------- Pipeline ----------
export class PodcastPipeline {
  constructor({ config, onLog, isCancelled = () => false }) {
    this.config = config;
    this.onLog = onLog;
    this.isCancelled = isCancelled;
    this.svc = new PodcastService(config.basePath);
    this.cachePath = path.join(config.basePath, CACHE_FILE);
  }

  _loadCache() {
    try {
      if (!fs.existsSync(this.cachePath)) return {};
      return JSON.parse(fs.readFileSync(this.cachePath, 'utf-8'));
    } catch { return {}; }
  }

  _saveCache(cache) {
    try { fs.writeFileSync(this.cachePath, JSON.stringify(cache), 'utf-8'); } catch {}
  }

  _findSrt(podDir, name) {
    const plain = path.join(podDir, `${name}.srt`);
    if (fs.existsSync(plain)) return plain;
    if (!fs.existsSync(podDir)) return null;
    try {
      for (const f of fs.readdirSync(podDir)) {
        if (f.startsWith(`${name}.`) && f.toLowerCase().endsWith('.srt')) {
          return path.join(podDir, f);
        }
      }
    } catch {}
    return null;
  }

  _srtToTxt(srtPath, txtPath) {
    try {
      if (!fs.existsSync(srtPath)) return;
      const content = fs.readFileSync(srtPath, 'utf-8');
      const textLines = [];
      let last = '';
      for (const line of content.split('\n')) {
        const t = line.trim();
        if (!t) continue;
        if (/^\d+$/.test(t)) continue;
        if (t.includes('-->')) continue;
        const clean = t.replace(/<[^>]+>/g, '');
        if (!clean || clean === last) continue;
        textLines.push(clean);
        last = clean;
      }
      fs.writeFileSync(txtPath, textLines.join('\n'), 'utf-8');
    } catch {}
  }

  async run() {
    const config = this.config;
    const subs = config.podcastSubscriptions || {};
    if (Object.keys(subs).length === 0) {
      this.onLog('沒有訂閱任何 Podcast');
      return;
    }

    const stamp = new Date().toISOString().substring(0, 19).replace('T', ' ');
    this.onLog(`${stamp}  Playlist Administrator (Node CLI)`);
    const hasGroq = !!(config.groqApiKey || '').trim();

    this.onLog(`Podcast 訂閱數: ${Object.keys(subs).length}`);
    const entries = Object.entries(subs);

    for (let si = 0; si < entries.length; si++) {
      if (this.isCancelled()) break;
      const [podcastName, rssUrl] = entries[si];
      const ts = new Date().toISOString().substring(0, 19).replace('T', ' ');
      this.onLog(`\n${ts} --- [${si + 1}/${entries.length}] ${podcastName} ---`);
      try {
        await this._processPodcast(podcastName, rssUrl, hasGroq);
      } catch (e) {
        this.onLog(`  ❌ ${podcastName} 失敗: ${e.message || e}`);
      }
    }
    this.onLog(this.isCancelled() ? 'Podcast Pipeline 已取消' : 'Podcast Pipeline 完成');
  }

  async _processPodcast(podcastName, rssUrl, hasGroq) {
    const cache = this._loadCache();
    const podDir = this.svc.podcastDir(podcastName);
    const ext = 'mp3';

    this.onLog('  讀取 RSS Feed...');
    const result = await this.svc.fetchEpisodes(rssUrl);
    const episodes = result.episodes;
    this.onLog(`  Feed: ${result.title} (${episodes.length} 集)`);

    const tasks = [];
    let alreadyHave = 0;
    for (let i = 0; i < episodes.length; i++) {
      if (this.isCancelled()) break;
      const ep = episodes[i];
      const key = `${podcastName}|${ep.title}`;
      const name = normalizeFileName(ep.title);
      const srtPath = this._findSrt(podDir, name);
      const txtPath = path.join(podDir, `${name}.txt`);
      const hasSrt = srtPath != null;
      const hasTxt = fs.existsSync(txtPath);
      if (hasSrt || hasTxt) {
        if (hasSrt && !hasTxt) this._srtToTxt(srtPath, txtPath);
        cache[key] = {
          srt: hasSrt,
          txt: hasTxt || fs.existsSync(txtPath),
          yt_status: hasSrt ? 'found' : (cache[key]?.yt_status || ''),
          status: 'ok',
        };
        alreadyHave++;
        continue;
      }
      if (!cache[key] || (cache[key].srt !== true && cache[key].txt !== true)) {
        tasks.push({ index: i, episode: ep, key });
      }
    }
    this._saveCache(cache);

    if (tasks.length === 0) {
      this.onLog(`  無新集數 (${alreadyHave} 集已處理過)`);
      return;
    }
    this.onLog(`  需處理: ${tasks.length} 集 (×4 並行)`);
    const total = tasks.length;
    const groqQueue = [];
    let groqActive = 0;
    const groqLimit = Math.max(1, Math.min(8, this.config.groqConcurrency || 3));

    const tryGroq = () => {
      while (groqActive < groqLimit && groqQueue.length > 0 && !this.isCancelled()) {
        const t = groqQueue.shift();
        groqActive++;
        this._runGroq(t, podcastName, podDir, ext, cache).finally(() => {
          groqActive--;
          this._saveCache(cache);
          tryGroq();
        });
      }
    };

    for (let i = 0; i < total; i += 4) {
      if (this.isCancelled()) break;
      const batch = tasks.slice(i, i + 4);
      await Promise.all(batch.map(async (t) => {
        const needGroq = await this._processOne(t, podcastName, rssUrl, podDir, ext, cache);
        this._saveCache(cache);
        if (needGroq && hasGroq) {
          groqQueue.push(t);
          tryGroq();
        }
      }));
      const done = Math.min(i + batch.length, total);
      this.onLog(`  進度: ${done}/${total}`);
    }

    while (groqActive > 0 && !this.isCancelled()) {
      await sleep(1000);
    }

    const values = Object.values(cache);
    const srtCount = values.filter((v) => v.srt === true).length;
    const txtCount = values.filter((v) => v.txt === true).length;
    const errCount = values.filter((v) => v.status === 'error').length;
    this.onLog(`  ${podcastName} 完成: 總處理 ${values.length} 集 (SRT ${srtCount}, 逐字稿 ${txtCount}, 錯誤 ${errCount})`);
  }

  async _processOne(t, podcastName, rssUrl, podDir, ext, cache) {
    const name = normalizeFileName(t.episode.title);
    const audioPath = path.join(podDir, `${name}.${ext}`);
    const txtPath = path.join(podDir, `${name}.txt`);

    if (!fs.existsSync(audioPath)) {
      this.onLog(`  [${t.index}] ⬇️ ${name}`);
      try {
        await this.svc.downloadEpisode(rssUrl, t.index, podcastName);
      } catch {
        this.onLog('    ❌ 下載失敗');
        cache[t.key] = { srt: false, txt: false, yt_status: '', status: 'error' };
        return false;
      }
    }

    const srtPath = this._findSrt(podDir, name);
    if (srtPath != null || fs.existsSync(txtPath)) {
      if (srtPath != null && !fs.existsSync(txtPath)) {
        this._srtToTxt(srtPath, txtPath);
        cache[t.key] = { srt: true, txt: fs.existsSync(txtPath), yt_status: 'found', status: 'ok' };
      }
      return false;
    }

    const prevYt = cache[t.key]?.yt_status;
    if (prevYt === 'not_found') {
      this.onLog(`    ⏭️ ${name} (YT 上次已搜過)`);
      cache[t.key] = { srt: false, txt: false, yt_status: 'not_found', status: 'no_sub' };
      return true;
    }

    this.onLog(`    🔍 ${name}`);
    await sleep((t.index % 4) * 300);
    const subResult = await this.svc.downloadSubtitles(t.episode.title, podcastName, (msg) => this.onLog(`      ${msg}`));
    const srtAfter = this._findSrt(podDir, name);
    if (subResult === 'found' && srtAfter != null) {
      this._srtToTxt(srtAfter, txtPath);
      cache[t.key] = { srt: true, txt: true, yt_status: 'found', status: 'ok' };
      return false;
    }
    if (subResult === 'not_found') {
      cache[t.key] = { srt: false, txt: false, yt_status: 'not_found', status: 'no_sub' };
    } else {
      cache[t.key] = { srt: false, txt: false, yt_status: '', status: 'no_sub' };
    }
    return true;
  }

  async _runGroq(t, podcastName, podDir, ext, cache) {
    if (this.isCancelled()) return;
    const name = normalizeFileName(t.episode.title);
    const audioPath = path.join(podDir, `${name}.${ext}`);
    const txtPath = path.join(podDir, `${name}.txt`);
    if (!fs.existsSync(audioPath)) return;
    if (this._findSrt(podDir, name) != null || fs.existsSync(txtPath)) return;
    this.onLog(`    🎤 ${name}`);
    try {
      const text = await transcribeAudio(
        audioPath, this.config.groqApiKey, 'whisper-large-v3-turbo', 'zh',
        (msg) => this.onLog(`      ${msg}`),
      );
      fs.writeFileSync(txtPath, text, 'utf-8');
      cache[t.key] = { srt: false, txt: true, yt_status: 'not_found', status: 'ok' };
      this.onLog(`      ✅ (${text.length} 字)`);
    } catch (e) {
      this.onLog(`      ❌ ${e.message || e}`);
      cache[t.key] = { srt: false, txt: false, yt_status: '', status: 'error' };
    }
  }
}
