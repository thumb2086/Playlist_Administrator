import 'dart:io';

class AudioConverter {
  static Future<bool> convert({
    required String inputPath,
    required String outputPath,
    String format = 'mp3',
    String? ffmpegPath,
  }) async {
    final ffmpeg = ffmpegPath ?? 'ffmpeg';
    if (!await File(inputPath).exists()) return false;

    if (inputPath.toLowerCase().endsWith('.$format')) {
      await File(inputPath).copy(outputPath);
      return true;
    }

    final result = await Process.run(ffmpeg, [
      '-y',
      '-i', inputPath,
      '-map_metadata', '0',
      '-codec:a', format == 'mp3' ? 'libmp3lame' : 'flac',
      '-q:a', '0',
      outputPath,
    ]);
    return result.exitCode == 0;
  }
}
