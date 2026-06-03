import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:html/parser.dart' show parse;

class SpotifyScraper {
  final void Function(String) log;
  final String playlistsPath;

  SpotifyScraper({required this.log, required this.playlistsPath});

  Future<void> scrapeAll(List<String> urls) async {
    int processed = 0;
    for (final url in urls) {
      processed++;
      log('[$processed/${urls.length}] 處理: $url');
      try {
        await _scrapeOne(url);
      } catch (e) {
        log('  錯誤: $e');
      }
    }
  }

  Future<void> _scrapeOne(String url) async {
    final spId = url.split('playlist/').last.split('?').first;
    final embedUrl = 'https://open.spotify.com/embed/playlist/$spId';

    log('  連線到 Spotify Embed…');
    final resp = await http.get(Uri.parse(embedUrl), headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    });

    if (resp.statusCode != 200) {
      log('  HTTP ${resp.statusCode}');
      return;
    }

    final doc = parse(resp.body);
    final scripts = doc.querySelectorAll('script[type="application/json"]');
    String? plName;
    final tracks = <String>[];

    for (final script in scripts) {
      final json = jsonDecode(script.text) as Map<String, dynamic>?;
      if (json == null) continue;

      try {
        final state = json['state'] as Map<String, dynamic>?;
        if (state == null) continue;
        final playlist = state['playlist'] as Map<String, dynamic>?;
        if (playlist == null) continue;
        plName = playlist['name'] as String?;
        final items = playlist['items'] as List<dynamic>?;
        if (items == null) continue;
        for (final item in items) {
          final track = item['track'] as Map<String, dynamic>?;
          if (track == null) continue;
          final artists = (track['artists'] as List<dynamic>?)
                  ?.map((a) => (a as Map<String, dynamic>)['name'] as String?)
                  .where((a) => a != null)
                  .join(', ') ??
              '';
          final title = track['name'] as String? ?? '';
          tracks.add(artists.isNotEmpty ? '$title - $artists' : title);
        }
      } catch (_) {}
    }

    if (plName == null || tracks.isEmpty) {
      log('  無法解析歌單');
      return;
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
  }
}
