import { run, resolveFfmpeg, resolveFfprobe } from './util.js';

// Port of lib/services/metadata_reader.dart (title/artist/album only;
// artwork extraction is not needed by the CLI).
export async function readMetadata(filePath, config) {
  try {
    const ffprobe = resolveFfprobe(resolveFfmpeg(config));
    const r = await run(ffprobe, [
      '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', filePath,
    ]);
    if (r.code !== 0) return { title: null, artist: null, album: null };
    const json = JSON.parse(r.stdout || '{}');
    const format = json.format;
    const tags = format?.tags || {};
    return {
      title: first(tags, ['title', 'Title', 'TIT2']),
      artist: first(tags, ['artist', 'Artist', 'TPE1']),
      album: first(tags, ['album', 'Album', 'TALB']),
    };
  } catch {
    return { title: null, artist: null, album: null };
  }
}

function first(map, keys) {
  for (const k of keys) {
    const v = map[k];
    if (v != null && String(v).length > 0) return String(v);
  }
  return null;
}
