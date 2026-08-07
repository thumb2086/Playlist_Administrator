import fs from 'node:fs';
import { stemOf } from './util.js';

// Port of lib/services/playlist_parser.dart
export class PlaylistParser {
  static isInternalPlaylist(name) {
    const n = name.toLowerCase();
    if (n.includes('_removed songs')) return true;
    return ['_unsorted', 'single tracks', '_unsorted_songs'].some((m) => n.includes(m));
  }

  static parseTrackNames(filePath) {
    const songs = [];
    if (!fs.existsSync(filePath)) return songs;
    let content;
    try { content = fs.readFileSync(filePath, 'utf-8'); }
    catch { return songs; }

    const lines = content.split('\n').map((l) => l.trim()).filter((l) => l.length > 0);
    if (lines.length === 0) return songs;
    const isM3u = lines.some((l) => l.includes('#EXTM3U'));

    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (isM3u && line.startsWith('#EXTINF:')) {
        let j = i + 1;
        while (j < lines.length && (lines[j].startsWith('#') || lines[j].length === 0)) j++;
        if (j < lines.length) {
          const pathLine = lines[j];
          const name = pathLine.includes('\\') || pathLine.includes('/')
            ? pathLine.replace(/[\\/]/g, '\\').split('\\').pop()
            : pathLine;
          songs.push(name.replace(/\.[^.]+$/, ''));
          i = j + 1;
        } else {
          i++;
        }
      } else {
        if (!line.startsWith('#')) {
          songs.push(line);
        }
        i++;
      }
    }
    return songs;
  }

  static parseTrackEntries(filePath) {
    const entries = [];
    if (!fs.existsSync(filePath)) return entries;
    let content;
    try { content = fs.readFileSync(filePath, 'utf-8'); }
    catch { return entries; }

    const lines = content.split('\n').map((l) => l.trim()).filter((l) => l.length > 0);
    if (lines.length === 0) return entries;
    const isM3u = lines.some((l) => l.includes('#EXTM3U'));

    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (isM3u && line.startsWith('#EXTINF:')) {
        let j = i + 1;
        while (j < lines.length && (lines[j].startsWith('#') || lines[j].length === 0)) j++;
        if (j < lines.length) {
          entries.push(lines[j]);
          i = j + 1;
        } else {
          i++;
        }
      } else {
        if (!line.startsWith('#')) {
          entries.push(line);
        }
        i++;
      }
    }
    return entries;
  }
}
