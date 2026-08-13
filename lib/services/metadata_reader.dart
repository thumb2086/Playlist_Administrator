import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

class TrackMetadata {
  final String? title;
  final String? artist;
  final String? album;
  final Uint8List? artwork;

  TrackMetadata({this.title, this.artist, this.album, this.artwork});

  bool get hasData => title != null || artist != null;
}

class MetadataReader {
  static Future<TrackMetadata> read(String filePath) async {
    try {
      final result = await Process.run('ffprobe', [
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        '-show_streams',
        filePath,
      ], stdoutEncoding: null);
      if (result.exitCode != 0) return TrackMetadata();

      final json =
          jsonDecode(utf8.decode(result.stdout as List<int>)) as Map<String, dynamic>;
      final format = json['format'] as Map<String, dynamic>?;
      final tags = format?['tags'] as Map<String, dynamic>?;
      final streams = json['streams'] as List<dynamic>?;

      Uint8List? artwork;
      if (streams != null) {
        for (final s in streams) {
          if (s is Map<String, dynamic> &&
              (s['codec_type'] == 'image' || s['codec_type'] == 'video')) {
            artwork = await _extractArtwork(filePath);
            break;
          }
        }
      }

      return TrackMetadata(
        title: tags != null ? _first(tags, ['title', 'Title', 'TIT2']) : null,
        artist: tags != null ? _first(tags, ['artist', 'Artist', 'TPE1']) : null,
        album: tags != null ? _first(tags, ['album', 'Album', 'TALB']) : null,
        artwork: artwork,
      );
    } catch (_) {
      return TrackMetadata();
    }
  }

  static Future<Uint8List?> _extractArtwork(String filePath) async {
    try {
      final result = await Process.run('ffmpeg', [
        '-v', 'quiet',
        '-i', filePath,
        '-map', '0:v:0',
        '-f', 'image2',
        '-c', 'copy',
        'pipe:1',
      ], stdoutEncoding: null);
      if (result.exitCode == 0 && result.stdout is List<int>) {
        final bytes = result.stdout as List<int>;
        if (bytes.isNotEmpty) return Uint8List.fromList(bytes);
      }
    } catch (_) {}
    return null;
  }

  static String? _first(Map<String, dynamic> map, List<String> keys) {
    for (final k in keys) {
      if (map.containsKey(k) && map[k] != null && (map[k] as String).isNotEmpty) {
        return map[k] as String;
      }
    }
    return null;
  }
}
