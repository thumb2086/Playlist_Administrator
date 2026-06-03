import 'dart:convert';
import 'dart:io';

class TrackMetadata {
  final String? title;
  final String? artist;
  final String? album;

  TrackMetadata({this.title, this.artist, this.album});

  bool get hasData => title != null || artist != null;
}

class MetadataReader {
  static Future<TrackMetadata> read(String filePath) async {
    try {
      final result = await Process.run('ffprobe', [
        '-v', 'quiet',
        '-print_format', 'json',
        '-show_format',
        filePath,
      ]);
      if (result.exitCode != 0) return TrackMetadata();

      final json = jsonDecode(result.stdout as String) as Map<String, dynamic>;
      final format = json['format'] as Map<String, dynamic>?;
      final tags = format?['tags'] as Map<String, dynamic>?;
      if (tags == null) return TrackMetadata();

      return TrackMetadata(
        title: _first(tags, ['title', 'Title', 'TIT2']),
        artist: _first(tags, ['artist', 'Artist', 'TPE1']),
        album: _first(tags, ['album', 'Album', 'TALB']),
      );
    } catch (_) {
      return TrackMetadata();
    }
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
