import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Port of lib/services/chinese_converter.dart — loads assets/zhcdict.json
// and does longest-prefix replacement.
let s2t = null;
let t2s = null;
let sKeys = null;
let tKeys = null;

export function loadDict() {
  if (s2t) return;
  const here = path.dirname(fileURLToPath(import.meta.url));
  // project root is 3 levels up from cli/lib/
  const root = path.resolve(here, '..', '..');
  const candidates = [
    path.join(root, 'assets', 'zhcdict.json'),
    path.join(process.cwd(), 'assets', 'zhcdict.json'),
  ];
  let data = null;
  for (const c of candidates) {
    if (fs.existsSync(c)) {
      try { data = JSON.parse(fs.readFileSync(c, 'utf-8')); break; } catch {}
    }
  }
  if (!data) return;
  s2t = {};
  t2s = {};
  for (const [k, v] of Object.entries(data)) {
    if (typeof v !== 'string') continue;
    s2t[k] = v;
    t2s[v] = k;
  }
  sKeys = Object.keys(s2t).sort((a, b) => b.length - a.length);
  tKeys = Object.keys(t2s).sort((a, b) => b.length - a.length);
}

export const isLoaded = () => s2t !== null;

function convert(text, dict, sortedKeys) {
  if (!text) return text;
  let out = '';
  let i = 0;
  outer:
  while (i < text.length) {
    for (const key of sortedKeys) {
      if (text.startsWith(key, i)) {
        out += dict[key];
        i += key.length;
        continue outer;
      }
    }
    out += text[i];
    i++;
  }
  return out;
}

export function toSimplified(text) {
  loadDict();
  return convert(text, t2s ?? {}, tKeys ?? []);
}

export function toTraditional(text) {
  loadDict();
  return convert(text, s2t ?? {}, sKeys ?? []);
}
