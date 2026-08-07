import fs from 'node:fs';
import path from 'node:path';
import { walkDir, stemOf } from './util.js';
import { readMetadata } from './metadata.js';
import { toSimplified, isLoaded, loadDict } from './zhcn.js';

// Port of lib/services/library_index.dart
const artistAliases = {
  'claire kuo': '郭靜', 'jolin': '蔡依林', 'jolin tsai': '蔡依林',
  'crowd lu': '盧廣仲', 'pets tseng': '曾沛慈', 'evangeline wong': '王艷薇',
  'sabrina': '胡恂舞', 'sabrina hu': '胡恂舞', 'eric chou': '周興哲',
  'shi shi': '孫盛希', 'boon hui lu': '文慧如', 'vicky chen': '陳忻玥',
  'feng ze': '邱鋒澤', 'ivy': '艾薇', 'genblue': '幻藍小熊',
  'lbi': '利比', 'erin': '連穎', 'eleanor': '李芷婷',
  'ann bai': '白安', 'diana wang': '王詩安', 'ethan': '陳威全',
  'chih siou': '持修', 'show luo': '羅志祥',
};

const noisePatterns = [
  '全新單曲', '單曲', '官方完整版', '官方', '完整版',
  '高清', '動態歌詞版', '歌詞版', '官方版', '全新',
  'music video', 'official video', 'official music video',
  'video', 'loop', 'lyrics',
];

export class LibraryIndex {
  constructor() {
    this._filenameIndex = new Map(); // tokenKey(string) -> [paths]
    this._metadataIndex = new Map();
    this._fileInfoMap = new Map(); // path -> {size, mtimeMs}
    this._mp3Count = 0;
    this._m4aCount = 0;
    this._podcastMp3Count = 0;
    this._podcastOtherCount = 0;
  }

  static _cacheDir() {
    return path.join(
      process.env.LOCALAPPDATA || '',
      'Playlist Administrator', 'data');
  }
  static _fingerprintFile() {
    return path.join(LibraryIndex._cacheDir(), 'index_fingerprint.json');
  }
  static _metaIndexFile() {
    return path.join(LibraryIndex._cacheDir(), 'index_metadata.json');
  }

  static _buildFingerprint(files) {
    const fp = new Set();
    for (const f of files) {
      try {
        const st = fs.statSync(f);
        fp.add(`${f}|${st.mtimeMs}`);
      } catch {
        fp.add(`${f}|0`);
      }
    }
    return fp;
  }

  async build(libraryPath, log, { basePath } = {}) {
    loadDict();
    log('掃描音檔…');
    const allFiles = await this._walkDir(libraryPath);
    if (basePath && basePath !== libraryPath) {
      const baseFiles = await this._walkDir(basePath);
      for (const f of baseFiles) {
        if (!allFiles.includes(f)) allFiles.push(f);
      }
    }
    const mp3s = [];
    const m4as = [];
    for (const f of allFiles) {
      const low = f.toLowerCase();
      if (low.endsWith('.mp3')) mp3s.push(f);
      else if (low.endsWith('.m4a')) m4as.push(f);
    }
    this._mp3Count = mp3s.length;
    this._m4aCount = m4as.length;
    this._fileInfoMap = new Map();
    for (const f of allFiles) {
      try {
        const st = fs.statSync(f);
        this._fileInfoMap.set(f, { size: st.size, mtimeMs: st.mtimeMs });
      } catch {}
    }
    this._filenameIndex = this._buildFilenameIndex(mp3s);

    let cachedFingerprint = null;
    try {
      const f = LibraryIndex._fingerprintFile();
      if (fs.existsSync(f)) {
        cachedFingerprint = new Set(JSON.parse(fs.readFileSync(f, 'utf-8')).fingerprint || []);
      }
    } catch {}

    const currentFp = LibraryIndex._buildFingerprint(allFiles);
    const changedStems = new Set();
    if (cachedFingerprint) {
      for (const entry of currentFp) {
        if (!cachedFingerprint.has(entry)) {
          const pipeIdx = entry.indexOf('|');
          if (pipeIdx > 0) changedStems.add(stemOf(entry.substring(0, pipeIdx)).toLowerCase());
        }
      }
      for (const entry of cachedFingerprint) {
        if (!currentFp.has(entry)) {
          const pipeIdx = entry.indexOf('|');
          if (pipeIdx > 0) changedStems.add(stemOf(entry.substring(0, pipeIdx)).toLowerCase());
        }
      }
    }

    this._metadataIndex = new Map();

    if (changedStems.size === 0 && cachedFingerprint) {
      log(`MP3: ${this._mp3Count}, M4A: ${this._m4aCount} (無變動，載入快取索引)`);
      const cached = this._loadMetaIndex();
      if (cached) {
        for (const [keyJson, paths] of Object.entries(cached)) {
          try {
            const tokens = JSON.parse(keyJson);
            this._metadataIndex.set(tokens.join('\u0000'), paths);
          } catch {}
        }
        log(`  metadata 索引載入完成: ${this._metadataIndex.size} 首`);
        this._saveFingerprint(currentFp);
        return;
      }
    }

    log(`MP3: ${this._mp3Count}, M4A: ${this._m4aCount}`);
    log('建立檔名索引…');
    if (changedStems.size > 0) {
      log(`metadata 新增/變更: ${changedStems.size} 個檔案`);
    }

    // Load cached metadata for unchanged files
    const cached = this._loadMetaIndex();
    const cachedPaths = new Set();
    if (cached) {
      for (const [keyJson, paths] of Object.entries(cached)) {
        let skip = false;
        for (const p of paths) {
          if (changedStems.has(stemOf(p).toLowerCase())) { skip = true; break; }
        }
        if (!skip) {
          this._metadataIndex.set(keyJson, paths);
          for (const p of paths) cachedPaths.add(p);
        }
      }
    }

    const toIndex = mp3s.filter((f) => {
      if (changedStems.size === 0) return true;
      return changedStems.has(stemOf(f).toLowerCase());
    });

    log(`讀取 metadata 索引 (${toIndex.length}/${mp3s.length} 個檔案)…`);
    const newEntries = await this._buildMetadataIndex(toIndex, log);
    for (const [k, v] of newEntries) this._metadataIndex.set(k, v);

    // Remove entries for deleted files
    const onDisk = new Set(mp3s);
    for (const [k, paths] of [...this._metadataIndex]) {
      const kept = paths.filter((p) => onDisk.has(p));
      if (kept.length === 0) this._metadataIndex.delete(k);
      else this._metadataIndex.set(k, kept);
    }

    if (changedStems.size > 0) {
      log(`索引完成 (新增 ${newEntries.length}，快取 ${this._metadataIndex.size - newEntries.length})`);
    } else {
      log('索引完成');
    }

    const serializable = {};
    for (const [k, v] of this._metadataIndex) serializable[k] = v;
    this._saveMetaIndex(serializable);
    this._saveFingerprint(currentFp);
  }

  _saveFingerprint(fp) {
    try {
      const dir = LibraryIndex._cacheDir();
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(LibraryIndex._fingerprintFile(), JSON.stringify({ fingerprint: [...fp] }));
    } catch {}
  }

  _loadMetaIndex() {
    try {
      const f = LibraryIndex._metaIndexFile();
      if (!fs.existsSync(f)) return null;
      return JSON.parse(fs.readFileSync(f, 'utf-8'));
    } catch { return null; }
  }

  _saveMetaIndex(index) {
    try {
      const dir = LibraryIndex._cacheDir();
      fs.mkdirSync(dir, { recursive: true });
      fs.writeFileSync(LibraryIndex._metaIndexFile(), JSON.stringify(index));
    } catch {}
  }

  async _walkDir(dir) {
    const result = [];
    if (!fs.existsSync(dir)) return result;
    const stack = [dir];
    while (stack.length) {
      const cur = stack.pop();
      let entries;
      try { entries = fs.readdirSync(cur, { withFileTypes: true }); } catch { continue; }
      for (const e of entries) {
        const full = path.join(cur, e.name);
        if (e.isDirectory()) stack.push(full);
        else if (e.isFile()) {
          const low = full.toLowerCase();
          if (!low.endsWith('.mp3') && !low.endsWith('.m4a') && !low.endsWith('.flac')) continue;
          if (low.includes('podcast_downloads') || low.includes('podcast_rag')) {
            if (low.endsWith('.mp3')) this._podcastMp3Count++;
            else this._podcastOtherCount++;
            continue;
          }
          result.push(full);
        }
      }
    }
    return result;
  }

  _buildFilenameIndex(files) {
    const index = new Map();
    for (const f of files) {
      const tokens = this._normalize(stemOf(f));
      if (tokens.length) {
        const key = tokens.join('\u0000');
        if (!index.has(key)) index.set(key, []);
        index.get(key).push(f);
      }
    }
    return index;
  }

  async _buildMetadataIndex(files, log) {
    const index = new Map();
    const batchSize = 20;
    for (let i = 0; i < files.length; i += batchSize) {
      const batch = files.slice(i, i + batchSize);
      const metas = await Promise.all(batch.map((f) => readMetadata(f, this._config)));
      for (let j = 0; j < batch.length; j++) {
        const meta = metas[j];
        if (meta.title) {
          const tokens = this._normalize(meta.title);
          if (tokens.length) {
            const key = tokens.join('\u0000');
            if (!index.has(key)) index.set(key, []);
            index.get(key).push(batch[j]);
          }
        }
      }
      if ((i + batch.length) % 500 === 0 || i + batch.length >= files.length) {
        log(`  metadata 索引: ${Math.min(i + batch.length, files.length)}/${files.length}`);
      }
    }
    return index;
  }

  _normalize(text) {
    let t = (text || '').toLowerCase().trim();
    if (!t) return [];

    // Remove spaces between CJK chars
    t = t.replace(/([\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff])\s+(?=[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff])/g, '$1');

    if (isLoaded()) t = toSimplified(t);

    for (const [alias, value] of Object.entries(artistAliases)) {
      const re = new RegExp(`\\b${alias.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'gi');
      t = t.replace(re, isLoaded() ? toSimplified(value) : value.toLowerCase());
    }

    // Remove "E " prefix artifact
    t = t.replace(/(^|(?<=[^a-z0-9]))e(?=[a-z\u4e00-\u9fff\u3040-\u30ff])/g, '');

    for (const p of noisePatterns) {
      t = t.replace(new RegExp(p, 'gi'), ' ');
    }

    t = t.replace(/\s*(feat|ft|vs)\.?\s*|\s*[&,x]\s*/gi, ' ');

    t = t.replace(/[\(\[【（［][^\)\]】）］]*(?:live|remix|mv|official|lyrics?\s*video|music\s*video)[^\)\]】）］]*[\)\]】）］]/gi, ' ');

    t = t.replace(/([a-z])([\u4e00-\u9fff])/g, '$1 $2');
    t = t.replace(/([\u4e00-\u9fff])([a-z])/g, '$1 $2');

    const parts = t.split(/[\s\-_()\[\]【】,./:：，。、！？（）「」""''《》〈〉\u3000]+/);
    return parts.filter((p) => p.length > 0);
  }

  findMp3ForM4a(m4aPath, { useMtime = true, cachedMeta = null } = {}) {
    const stem = stemOf(m4aPath);
    const tokens = this._normalize(stem);
    const m4aInfo = this._fileInfoMap.get(m4aPath);

    const mtimeOk = (mp3Path) => {
      if (!useMtime) return true;
      const mp3Info = this._fileInfoMap.get(mp3Path);
      return mp3Info && m4aInfo && mp3Info.mtimeMs >= m4aInfo.mtimeMs;
    };

    // 1. exact filename match
    const exact = this._findInIndex(tokens, this._filenameIndex);
    if (exact && mtimeOk(exact)) return exact;

    // 2. fuzzy filename match
    for (const [key, paths] of this._filenameIndex) {
      const entryTokens = key.split('\u0000');
      if (this._isSubset(tokens, entryTokens) || this._isSubset(entryTokens, tokens)) {
        for (const f of paths) {
          if (f.toLowerCase().endsWith('.mp3') && this._fileInfoMap.has(f) && mtimeOk(f)) return f;
        }
      }
    }

    // 3. metadata-based matching
    if (cachedMeta && cachedMeta.title) {
      const titleTokens = this._normalize(cachedMeta.title);
      for (const [key, paths] of this._metadataIndex) {
        const entryTokens = key.split('\u0000');
        if (this._isSubset(titleTokens, entryTokens) || this._isSubset(entryTokens, titleTokens)) {
          for (const f of paths) {
            if (f.toLowerCase().endsWith('.mp3') && this._fileInfoMap.has(f)) return f;
          }
        }
      }
      if (cachedMeta.artist) {
        const combined = this._normalize(`${cachedMeta.title} - ${cachedMeta.artist}`);
        for (const [key, paths] of this._filenameIndex) {
          const entryTokens = key.split('\u0000');
          if (this._isSubset(combined, entryTokens) || this._isSubset(entryTokens, combined)) {
            for (const f of paths) {
              if (f.toLowerCase().endsWith('.mp3') && this._fileInfoMap.has(f)) return f;
            }
          }
        }
      }
    }

    return null;
  }

  _findInIndex(tokens, index) {
    const key = tokens.join('\u0000');
    const paths = index.get(key);
    if (paths) {
      for (const f of paths) {
        if (f.toLowerCase().endsWith('.mp3') && this._fileInfoMap.has(f)) return f;
      }
    }
    return null;
  }

  _isSubset(small, big) {
    if (small.length > big.length) return false;
    return small.every((s) => big.some((b) => b.includes(s)));
  }
}
