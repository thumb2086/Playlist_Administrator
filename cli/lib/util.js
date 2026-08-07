import fs from 'node:fs';
import path from 'node:path';
import { spawn, execFile } from 'node:child_process';

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function run(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    execFile(cmd, args, { windowsHide: true, timeout: opts.timeout, encoding: opts.encoding ?? 'utf8' },
      (err, stdout, stderr) => {
        resolve({ code: err ? (err.code ?? 1) : 0, stdout: stdout ?? '', stderr: stderr ?? '' });
      });
  });
}

export function runStream(cmd, args, { onLine, onStderr, timeout } = {}) {
  return new Promise((resolve) => {
    const p = spawn(cmd, args, { windowsHide: true, shell: false });
    let stdout = '';
    let stderr = '';
    if (onLine) {
      let buf = '';
      p.stdout.on('data', (d) => {
        buf += d.toString('utf-8');
        let i;
        while ((i = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, i).replace(/\r$/, '');
          buf = buf.slice(i + 1);
          onLine(line);
        }
      });
      p.stdout.on('end', () => { if (buf.trim()) onLine(buf); });
    } else {
      p.stdout.on('data', (d) => { stdout += d.toString('utf-8'); });
    }
    p.stderr.on('data', (d) => {
      const s = d.toString('utf-8');
      stderr += s;
      onStderr?.(s);
    });
    const t = timeout ? setTimeout(() => { try { p.kill(); } catch {} }, timeout) : null;
    p.on('close', (code) => {
      if (t) clearTimeout(t);
      resolve({ code: code ?? 0, stdout, stderr });
    });
    p.on('error', () => resolve({ code: 1, stdout, stderr }));
  });
}

export function resolveFfmpeg(config) {
  const cfg = config.ffmpegPath || '';
  if (cfg && !cfg.includes('\\') && !cfg.includes('/')) return cfg;
  if (cfg) {
    const abs = path.isAbsolute(cfg) ? cfg : path.resolve(process.cwd(), cfg);
    if (fs.existsSync(abs)) return abs;
  }
  for (const dir of (process.env.PATH || '').split(';')) {
    if (!dir.trim()) continue;
    const cand = path.join(dir.trim(), 'ffmpeg.exe');
    if (fs.existsSync(cand)) return cand;
  }
  return 'ffmpeg';
}

export function resolveFfprobe(ffmpeg) {
  if (ffmpeg !== 'ffmpeg' && !ffmpeg.toLowerCase().endsWith('ffmpeg.exe')) {
    const cand = path.join(path.dirname(ffmpeg), 'ffprobe.exe');
    if (fs.existsSync(cand)) return cand;
  }
  for (const dir of (process.env.PATH || '').split(';')) {
    if (!dir.trim()) continue;
    const cand = path.join(dir.trim(), 'ffprobe.exe');
    if (fs.existsSync(cand)) return cand;
  }
  return 'ffprobe';
}

export async function walkDir(dir, opts = {}) {
  const result = [];
  if (!fs.existsSync(dir)) return result;
  const stack = [dir];
  while (stack.length) {
    const cur = stack.pop();
    let entries;
    try { entries = fs.readdirSync(cur, { withFileTypes: true }); } catch { continue; }
    for (const e of entries) {
      const full = path.join(cur, e.name);
      if (e.isDirectory()) {
        stack.push(full);
      } else if (e.isFile()) {
        if (opts.filter && !opts.filter(full)) continue;
        result.push(full);
      }
    }
  }
  return result;
}

export function relativePath(absPath, relativeTo) {
  const absParts = absPath.replaceAll('\\', '/').split('/');
  const relParts = relativeTo.replaceAll('\\', '/').split('/');
  let common = 0;
  while (common < absParts.length && common < relParts.length &&
      absParts[common].toLowerCase() === relParts[common].toLowerCase()) {
    common++;
  }
  const up = Array(relParts.length - common).fill('..');
  const down = absParts.slice(common);
  return [...up, ...down].join('/');
}

export function stemOf(p) {
  const name = p.replace(/[\\/]/g, '\\').split('\\').pop() ?? '';
  return name.replace(/\.[^.]+$/, '');
}

export function normalizeFileName(name) {
  return name
    .replace(/\s*\[[\w-]{11}\]/g, '')
    .replace(/[<>:"/\\|?*&]/g, '_')
    .trim();
}

export function isInternalPlaylist(name) {
  const n = name.toLowerCase();
  if (n.includes('_removed songs')) return true;
  return ['_unsorted', 'single tracks', '_unsorted_songs'].some((m) => n.includes(m));
}

export function readJson(p, fallback = null) {
  try { return JSON.parse(fs.readFileSync(p, 'utf-8')); } catch { return fallback; }
}

export function writeJson(p, data) {
  try {
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, JSON.stringify(data, null, 2), 'utf-8');
  } catch {}
}
