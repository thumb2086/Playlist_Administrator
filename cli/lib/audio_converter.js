import fs from 'node:fs';
import path from 'node:path';
import { run } from './util.js';
import { readMetadata } from './metadata.js';

// Port of lib/services/audio_converter.dart
export async function convert({ inputPath, outputPath, format = 'mp3', ffmpegPath, meta = null, isCancelled }) {
  let ffmpeg = ffmpegPath || 'ffmpeg';
  if (ffmpeg.includes('\\') || ffmpeg.includes('/')) {
    if (!fs.existsSync(ffmpeg)) ffmpeg = 'ffmpeg';
  }
  if (!fs.existsSync(inputPath)) return { ok: false, lufs: null };
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });

  if (inputPath.toLowerCase().endsWith(`.${format}`)) {
    fs.copyFileSync(inputPath, outputPath);
    return { ok: true, lufs: null };
  }

  if (!meta) meta = await readMetadata(inputPath, { ffmpegPath });

  const args = [
    '-y', '-i', inputPath,
    '-map_metadata', '0',
    '-id3v2_version', '3',
    '-threads', '0',
  ];
  if (format === 'mp3') {
    args.push('-af', 'loudnorm=I=-14:TP=-1:LRA=7', '-filter_threads', '0');
  }
  args.push('-codec:a', format === 'mp3' ? 'libmp3lame' : 'flac', '-q:a', '0', outputPath);

  try {
    const result = await run(ffmpeg, args, { timeout: 600000 });
    if (result.code !== 0) return { ok: false, lufs: null };
    const m = result.stderr.match(/Input Integrated:\s+([-\d.]+)/);
    const lufs = m ? parseFloat(m[1]) : null;
    return { ok: true, lufs };
  } catch {
    return { ok: false, lufs: null };
  }
}
