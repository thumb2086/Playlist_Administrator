import fs from 'node:fs';
import path from 'node:path';
import { walkDir, stemOf, relativePath } from './util.js';

// Port of lib/services/spotify_scraper.dart
const cn2en = {
  '郭靜': 'Claire Kuo', '蔡依林': 'Jolin Tsai', '盧廣仲': 'Crowd Lu',
  '曾沛慈': 'Pets Tseng', '王艷薇': 'Evangeline Wong', '胡恂舞': 'Sabrina Hu',
  '周興哲': 'Eric Chou', '孫盛希': 'Shi Shi', '文慧如': 'Boon Hui Lu',
  '陳忻玥': 'Vicky Chen', '邱鋒澤': 'Feng Ze', '艾薇': 'Ivy',
  '幻藍小熊': 'GENBLUE', '利比': 'LBI', '連穎': 'Erin',
  '李芷婷': 'Eleanor', '白安': 'Ann Bai', '王詩安': 'Diana Wang',
  '陳威全': 'Ethan', '持修': 'Chih Siou', '羅志祥': 'Show Luo',
  '陳零九': 'Nine Chen', '九澤CP': 'Nine Ze CP',
  '告五人': 'Accusefive', '理想混蛋': 'Bestards',
  '魏如萱': 'Waa Wei', '魏如昀': 'Queen Wei',
};

const toEnglish = (name) => cn2en[name] || name;

function englishDisplayName(raw) {
  if (!raw.includes(' - ')) return raw;
  const idx = raw.lastIndexOf(' - ');
  return `${raw.substring(0, idx)} - ${toEnglish(raw.substring(idx + 3).trim())}`;
}

function getPath(obj, keys) {
  let current = obj;
  for (const k of keys) {
    if (current && typeof current === 'object' && current[k] && typeof current[k] === 'object') {
      current = current[k];
    } else {
      return null;
    }
  }
  return current;
}

function sanitize(name) {
  return name.replace(/[<>:"/\\|?*]/g, '_').replace(/\s+/g, ' ').trim();
}

function stripControlChars(s) {
  return s.replace(/[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufeff]/g, '').trim();
}

export class SpotifyScraper {
  constructor({ log, playlistsPath, libraryPath = '' }) {
    this.log = log;
    this.playlistsPath = playlistsPath;
    this.libraryPath = libraryPath;
    this._mp3Index = null;
  }

  async _buildIndex() {
    if (this._mp3Index || !this.libraryPath) return;
    this.log('  掃描音樂庫建立檔案索引…');
    const mp3 = new Map();
    const dirs = [this.libraryPath, path.join(this.libraryPath, 'mp3'), path.join(this.libraryPath, 'flac')];
    for (const dir of dirs) {
      if (!fs.existsSync(dir)) continue;
      const files = await walkDir(dir, { filter: (f) => f.toLowerCase().endsWith('.mp3') });
      for (const f of files) {
        const low = f.toLowerCase();
        if (low.includes('podcast_downloads') || low.includes('podcast_rag')) continue;
        const stem = stemOf(f).toLowerCase();
        if (!mp3.has(stem)) mp3.set(stem, f);
      }
    }
    this._mp3Index = mp3;
    this.log(`  音檔索引完成: MP3 ${mp3.size}`);
  }

  _findAudioFile(trackName) {
    const ix = this._mp3Index;
    if (!ix) return null;
    const stem = trackName.toLowerCase().trim();
    if (ix.has(stem)) return ix.get(stem);
    if (stem.includes(' - ')) {
      const parts = stem.split(' - ');
      if (parts.length >= 2) {
        const reversed = `${parts[1]} - ${parts[0]}`;
        if (ix.has(reversed)) return ix.get(reversed);
        const titlePart = parts[0].trim();
        if (titlePart.length >= 2) {
          for (const k of ix.keys()) {
            if (k.startsWith(titlePart) || k.includes(` ${titlePart} `)) {
              return ix.get(k);
            }
          }
        }
      }
    }
    return null;
  }

  async scrapeAll(urls, config) {
    const plNames = [];
    let processed = 0;
    for (const url of urls) {
      processed++;
      this.log(`[${processed}/${urls.length}] 處理: ${url}`);
      try {
        const name = await this._scrapeOne(url, config);
        if (name != null) plNames.push(name);
      } catch (e) {
        this.log(`  錯誤: ${e.message || e}`);
      }
    }
    return plNames;
  }

  async _scrapeOne(url, config) {
    const spId = url.split('playlist/').pop().split('?')[0];
    const embedUrl = `https://open.spotify.com/embed/playlist/${spId}`;
    this.log('  連線到 Spotify Embed…');
    const resp = await fetch(embedUrl, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.5',
      },
    });
    if (resp.status !== 200) {
      this.log(`  HTTP ${resp.status}`);
      return null;
    }
    const html = await resp.text();

    let plName = null;
    const tracks = [];

    // Try __NEXT_DATA__ first
    const nextMatch = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
    if (nextMatch) {
      try {
        const data = JSON.parse(nextMatch[1]);
        const entity = getPath(data, ['props', 'pageProps', 'state', 'data', 'entity']);
        if (entity) {
          plName = entity.name ? stripControlChars(String(entity.name)) : null;
          const trackList = entity.trackList || entity.tracks;
          if (Array.isArray(trackList)) {
            for (const item of trackList) {
              const track = (item && typeof item === 'object' && item.track) || item;
              if (!track) continue;
              const name = track.name || track.title;
              if (!name) continue;
              const artists = Array.isArray(track.artists)
                ? track.artists.map((a) => a?.name).filter(Boolean).join(', ')
                : track.subtitle;
              const displayName = artists ? `${name} - ${artists}` : name;
              tracks.push(englishDisplayName(displayName));
              this._saveTrackCache(englishDisplayName(displayName), String(name), toEnglish((artists || '').trim()), track, config);
            }
          }
        }
      } catch {}
    }

    // Fallback: old script[type="application/json"]
    if (!plName || tracks.length === 0) {
      const scriptRe = /<script type="application\/json"[^>]*>([\s\S]*?)<\/script>/g;
      let m;
      while ((m = scriptRe.exec(html)) != null) {
        try {
          const json = JSON.parse(m[1]);
          const state = json.state;
          if (!state || !state.playlist) continue;
          const playlist = state.playlist;
          plName = playlist.name ? stripControlChars(String(playlist.name)) : null;
          const items = playlist.items;
          if (!Array.isArray(items)) continue;
          for (const item of items) {
            const track = item.track;
            if (!track) continue;
            const artists = Array.isArray(track.artists)
              ? track.artists.map((a) => a?.name).filter(Boolean).join(', ')
              : '';
            const title = track.name || '';
            const displayName = artists ? `${title} - ${artists}` : title;
            tracks.push(englishDisplayName(displayName));
            this._saveTrackCache(englishDisplayName(displayName), String(title), toEnglish(artists.trim()), track, config);
          }
          break;
        } catch {}
      }
    }

    if (!plName || tracks.length === 0) {
      this.log('  無法解析歌單');
      const emptyFile = path.join(this.playlistsPath, `${plName || 'unknown'}.m3u8`);
      if (fs.existsSync(emptyFile)) {
        fs.unlinkSync(emptyFile);
        this.log('  已刪除空的播放清單檔案');
      }
      return null;
    }

    this.log(`  歌單: ${plName}, ${tracks.length} 首`);
    await this._buildIndex();

    const m3uPath = path.join(this.playlistsPath, `${plName}.m3u8`);
    fs.mkdirSync(this.playlistsPath, { recursive: true });

    // Clean up old M3U8 if playlist renamed
    const oldName = config.urlNames[url];
    if (oldName && oldName !== plName) {
      const oldFile = path.join(this.playlistsPath, `${oldName}.m3u8`);
      if (fs.existsSync(oldFile)) {
        fs.unlinkSync(oldFile);
        this.log(`  已清理舊歌單檔: ${oldName}.m3u8`);
      }
    }

    let sb = '#EXTM3U\n';
    let resolved = 0;
    for (const t of tracks) {
      const matched = this._findAudioFile(t);
      if (matched != null) {
        const localName = stemOf(matched);
        sb += `#EXTINF:-1,${localName}\n`;
        const absPath = path.resolve(matched);
        const absPl = path.resolve(path.dirname(m3uPath));
        sb += `${relativePath(absPath, absPl)}\n`;
        resolved++;
      }
    }
    fs.writeFileSync(m3uPath, sb, 'utf-8');
    this.log(`  已儲存: ${plName}.m3u8 (已解析路徑: ${resolved}/${tracks.length})`);

    // Update config with the real playlist name
    config.urlNames[url] = plName;
    return plName;
  }

  _ensureCacheDir(config) {
    if (!config.basePath) return;
    const dir = path.join(config.basePath, 'spotify_cache');
    if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
  }

  _saveTrackCache(displayName, title, artists, track, config) {
    try {
      const album = track.album;
      let albumName, releaseDate, coverUrl;
      if (album) {
        albumName = album.name;
        releaseDate = album.release_date ?? album.date;
        const images = album.images;
        if (Array.isArray(images) && images.length) {
          coverUrl = images[0]?.url;
        }
      }
      const cleanName = sanitize(displayName);
      this._ensureCacheDir(config);
      const file = path.join(config.basePath, 'spotify_cache', `${cleanName}.json`);
      fs.writeFileSync(file, JSON.stringify({
        title, artist: artists,
        ...(albumName ? { album: albumName } : {}),
        ...(releaseDate ? { release_date: releaseDate } : {}),
        ...(coverUrl ? { cover_url: coverUrl } : {}),
      }), 'utf-8');
    } catch {}
  }
}
