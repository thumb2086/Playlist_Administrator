import 'dart:io';
import 'metadata_reader.dart';

class AudioConverter {
  static Future<bool> convert({
    required String inputPath,
    required String outputPath,
    String format = 'mp3',
    String? ffmpegPath,
    TrackMetadata? meta,
  }) async {
    String ffmpeg = ffmpegPath ?? 'ffmpeg';
    if (!ffmpeg.contains('\\') && !ffmpeg.contains('/')) {
      // Already a simple name like 'ffmpeg' — keep as-is
    } else if (!await File(ffmpeg).exists()) {
      ffmpeg = 'ffmpeg'; // Fallback to PATH if configured path doesn't exist
    }
    if (!await File(inputPath).exists()) return false;

    // Ensure output directory exists
    await File(outputPath).parent.create(recursive: true);

    if (inputPath.toLowerCase().endsWith('.$format')) {
      await File(inputPath).copy(outputPath);
      return true;
    }

    meta ??= await MetadataReader.read(inputPath);

    final args = <String>[
      '-y', '-i', inputPath,
      '-map_metadata', '0',
      '-id3v2_version', '3',
    ];

    // Apply EBU R128 loudnorm to MP3 output (YouTube/Spotify standard -14 LUFS)
    if (format == 'mp3') {
      args.addAll(['-af', 'loudnorm=I=-14:TP=-1:LRA=7']);
    }

    args.addAll([
      '-codec:a', format == 'mp3' ? 'libmp3lame' : 'flac',
      '-q:a', '0',
      outputPath,
    ]);

    try {
      final result = await Process.run(ffmpeg, args);
      return result.exitCode == 0;
    } catch (_) {
      return false;
    }
  }
}
