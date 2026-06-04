import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:html/parser.dart' show parse;
import 'config_service.dart';

class SpotifyTrackMeta {
  final String title;
  final String artist;
  final String? album;
  final String? releaseDate;
  final String? coverUrl;
  SpotifyTrackMeta({
    required this.title,
    required this.artist,
    this.album,
    this.releaseDate,
    this.coverUrl,
  });

  Map<String, dynamic> toJson() => {
    'title': title,
    'artist': artist,
    if (album != null) 'album': album,
    if (releaseDate != null) 'release_date': releaseDate,
    if (coverUrl != null) 'cover_url': coverUrl,
  };
}

class SpotifyScraper {
  final void Function(String) log;
  final String playlistsPath;

  SpotifyScraper({required this.log, required this.playlistsPath});

  Future<List<String>> scrapeAll(List<String> urls) async {
    final plNames = <String>[];
    int processed = 0;
    for (final url in urls) {
      processed++;
      log('[$processed/${urls.length}] 處理: $url');
      try {
        final name = await _scrapeOne(url);
        if (name != null) plNames.add(name);
      } catch (e) {
        log('  錯誤: $e');
      }
    }
    return plNames;
  }

  Map<String, dynamic>? _getPath(Map<String, dynamic> obj, List<String> keys) {
    var current = obj;
    for (final k in keys) {
      if (current.containsKey(k) && current[k] is Map<String, dynamic>) {
        current = current[k] as Map<String, dynamic>;
      } else {
        return null;
      }
    }
    return current;
  }

  Future<String?> _scrapeOne(String url) async {
    final spId = url.split('playlist/').last.split('?').first;
    final embedUrl = 'https://open.spotify.com/embed/playlist/$spId';

    log('  連線到 Spotify Embed…');
    final resp = await http.get(Uri.parse(embedUrl), headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
      'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
    });

    if (resp.statusCode != 200) {
      log('  HTTP ${resp.statusCode}');
      return null;
    }

    final doc = parse(resp.body);
    String? plName;
    final tracks = <String>[];

    // Try __NEXT_DATA__ first (newer Spotify embed format)
    final nextData = doc.querySelector('script#__NEXT_DATA__');
    if (nextData != null) {
      try {
        final data = jsonDecode(nextData.text) as Map<String, dynamic>;
        final entity = _getPath(data, ['props', 'pageProps', 'state', 'data', 'entity']);
        if (entity != null) {
          plName = entity['name'] as String?;
          final trackList = (entity['trackList'] ?? entity['tracks']) as List<dynamic>?;
          if (trackList != null) {
            _ensureCacheDir();
            for (final item in trackList) {
              final track = (item is Map<String, dynamic>) ? (item['track'] as Map<String, dynamic>? ?? item) : null;
              if (track == null) continue;
              final name = track['name'] as String? ?? track['title'] as String?;
              if (name == null) continue;
              final artists = (track['artists'] as List<dynamic>?)
                      ?.map((a) => (a as Map<String, dynamic>)['name'] as String?)
                      .where((a) => a != null)
                      .join(', ') ??
                  (track['subtitle'] as String?);
              final displayName = (artists != null && artists.isNotEmpty) ? '$name - $artists' : name;
              tracks.add(displayName);
              _saveTrackCache(displayName, name, artists ?? '', track);
            }
          }
        }
      } catch (_) {}
    }

    // Fallback: try old script[type="application/json"] format
    if (plName == null || tracks.isEmpty) {
      final scripts = doc.querySelectorAll('script[type="application/json"]');
      for (final script in scripts) {
        try {
          final json = jsonDecode(script.text) as Map<String, dynamic>;
          final state = json['state'] as Map<String, dynamic>?;
          if (state == null) continue;
          final playlist = state['playlist'] as Map<String, dynamic>?;
          if (playlist == null) continue;
          plName = playlist['name'] as String?;
          final items = playlist['items'] as List<dynamic>?;
          if (items == null) continue;

          _ensureCacheDir();
          for (final item in items) {
            final track = item['track'] as Map<String, dynamic>?;
            if (track == null) continue;
            final artists = (track['artists'] as List<dynamic>?)
                    ?.map((a) => (a as Map<String, dynamic>)['name'] as String?)
                    .where((a) => a != null)
                    .join(', ') ?? '';
            final title = track['name'] as String? ?? '';
            final displayName = artists.isNotEmpty ? '$title - $artists' : title;
            tracks.add(displayName);
            _saveTrackCache(displayName, title, artists, track);
          }
          break;
        } catch (_) {}
      }
    }

    if (plName == null || tracks.isEmpty) {
      log('  無法解析歌單');
      return null;
    }

    log('  歌單: $plName, ${tracks.length} 首');

    final m3uPath = '$playlistsPath\\$plName.m3u8';
    await Directory(playlistsPath).create(recursive: true);

    final buffer = StringBuffer('#EXTM3U\n');
    for (final t in tracks) {
      buffer.writeln('#EXTINF:-1,$t');
      buffer.writeln(t);
    }
    await File(m3uPath).writeAsString(buffer.toString(), flush: true);
    log('  已儲存: $plName.m3u8');
    // Update config with the real playlist name
    ConfigService.instance.config.urlNames[url] = plName;
    ConfigService.instance.save();
    return plName;
  }

  void _ensureCacheDir() {
    final base = ConfigService.instance.config.basePath;
    if (base.isEmpty) return;
    final dir = Directory('$base\\spotify_cache');
    if (!dir.existsSync()) dir.createSync(recursive: true);
  }

  String _cacheDir() =>
      '${ConfigService.instance.config.basePath}\\spotify_cache';

  void _saveTrackCache(String displayName, String title, String artists, Map<String, dynamic> track) {
    try {
      final album = track['album'] as Map<String, dynamic>?;
      String? albumName;
      String? releaseDate;
      String? coverUrl;

      if (album != null) {
        albumName = album['name'] as String?;
        releaseDate = (album['release_date'] ?? album['date']) as String?;
        final images = album['images'] as List<dynamic>?;
        if (images != null && images.isNotEmpty) {
          final img = images[0] as Map<String, dynamic>?;
          coverUrl = img?['url'] as String?;
        }
      }

      final meta = SpotifyTrackMeta(
        title: title,
        artist: artists,
        album: albumName,
        releaseDate: releaseDate,
        coverUrl: coverUrl,
      );

      final cleanName = _sanitize(displayName);
      final file = File('${_cacheDir()}\\$cleanName.json');
      file.writeAsStringSync(jsonEncode(meta.toJson()), flush: true);
    } catch (_) {}
  }

  String _sanitize(String name) {
    return name.replaceAll(RegExp(r'[<>:"/\\|?*]'), '_')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }
}
