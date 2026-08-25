import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:xml/xml.dart';
import '../models/podcast_episode.dart';
import '../models/podcast_search_result.dart';
import 'config_service.dart';

enum PodcastSubtitleResult { found, notFound, failed }

class PodcastService {
  static PodcastService? _instance;
  static PodcastService get instance => _instance ??= PodcastService._();
  PodcastService._();

  String _podcastDir(String? podcastName) {
    final cfg = ConfigService.instance.config;
    final base = cfg.podcastsPath;
    if (base.isEmpty) return '';
    final sub = podcastName != null && podcastName.isNotEmpty
        ? podcastName.replaceAll(RegExp(r'[<>:"/\\|?*]'), '_')
        : '';
    final path = sub.isNotEmpty ? '$base\\$sub' : base;
    Directory(path).createSync(recursive: true);
    return path;
  }

  String get _downloadPath => _podcastDir(null);

  static String normalizeFileName(String title) {
    return title
        .replaceAll(RegExp(r'\s*\[[\w-]{11}\]'), '')
        .replaceAll(RegExp(r'[<>:"/\\|?*&]'), '_')
        .trim();
  }

  /// Fetch RSS feed and parse episodes natively (no Python).
  Future<({String title, List<PodcastEpisode> episodes})> fetchEpisodes(
      String rssUrl) async {
    final resp = await http.get(Uri.parse(rssUrl), headers: {
      'User-Agent': 'playlist-admin/2.0',
    });
    if (resp.statusCode != 200) {
      throw Exception('RSS fetch failed (${resp.statusCode})');
    }
    final doc = XmlDocument.parse(resp.body);
    final channel = doc.findAllElements('channel').firstOrNull;
    if (channel == null) throw Exception('No <channel> in RSS');
    final title = channel.findAllElements('title').firstOrNull?.innerText ?? '';
    final episodes = <PodcastEpisode>[];
    for (final item in channel.findAllElements('item')) {
      final epTitle = item.findAllElements('title').firstOrNull?.innerText ?? '';
      final description = item.findAllElements('description').firstOrNull?.innerText ?? '';
      final pubDate = item.findAllElements('pubDate').firstOrNull?.innerText ?? '';
      // Duration from itunes:duration
      final itunesNs = 'http://www.itunes.com/dtds/podcast-1.0.dtd';
      final durationEl = item.findAllElements('duration', namespace: itunesNs).firstOrNull
          ?? item.findAllElements('{http://www.itunes.com/dtds/podcast-1.0.dtd}duration').firstOrNull;
      final durationStr = durationEl?.innerText ?? '';
      // Audio URL from enclosure.
      final enclosure = item.findAllElements('enclosure').firstOrNull;
      final audioUrl = enclosure?.getAttribute('url') ?? '';
      episodes.add(PodcastEpisode(
        title: epTitle,
        audioUrl: audioUrl,
        description: description,
        pubDate: pubDate,
        duration: durationStr,
      ));
    }
    return (title: title, episodes: episodes);
  }

  /// Get audio URL for a specific episode index from RSS.
  Future<String?> getAudioUrl(String rssUrl, int index) async {
    final resp = await http.get(Uri.parse(rssUrl), headers: {
      'User-Agent': 'playlist-admin/2.0',
    });
    if (resp.statusCode != 200) return null;
    final doc = XmlDocument.parse(resp.body);
    final items = doc.findAllElements('item').toList();
    if (index < 0 || index >= items.length) return null;
    final item = items[index];
    // Check enclosure first, then itunes:audio
    final enclosure = item.findAllElements('enclosure').firstOrNull;
    if (enclosure != null) {
      return enclosure.getAttribute('url');
    }
    final audio = item.findAllElements('{http://www.itunes.com/dtds/podcast-1.0.dtd}audio').firstOrNull;
    return audio?.getAttribute('href');
  }

  bool isEpisodeDownloaded(String title, String audioUrl, {String? podcastName}) {
    final ext = _guessExtension(audioUrl);
    final name = normalizeFileName(title);
    final podDir = podcastName != null ? _podcastDir(podcastName) : _downloadPath;
    if (File('$podDir\\$name.$ext').existsSync()) return true;
    final titleEp = RegExp(r'EP(\d+)', caseSensitive: false).firstMatch(title);
    if (titleEp == null) return false;
    final epNumInt = int.tryParse(titleEp.group(1)!);
    if (epNumInt == null) return false;
    final searchDir = Directory(podDir);
    if (!searchDir.existsSync()) return false;
    try {
      return searchDir.listSync().any((f) {
        if (f is! File) return false;
        final fname = f.uri.pathSegments.last;
        if (fname.startsWith('\u3010\u8a66\u807d\u3011') || fname.startsWith('\u3010')) return false;
        final fileEp = RegExp(r'EP(\d+)', caseSensitive: false).firstMatch(fname);
        if (fileEp == null) return false;
        return int.tryParse(fileEp.group(1)!) == epNumInt;
      });
    } catch (_) {}
    return false;
  }

  String episodeOutputPath(String title, String audioUrl) {
    final safeName = title.replaceAll(RegExp(r'[<>:"/\\|?*]'), '_');
    final ext = _guessExtension(audioUrl);
    return '$_downloadPath\\$safeName.$ext';
  }

  /// Download episode audio natively (HTTP streaming, no Python).
  Future<bool> downloadEpisode(
    String rssUrl,
    int index,
    void Function(double progress) onProgress, {
    String? podcastName,
  }) async {
    final audioUrl = await getAudioUrl(rssUrl, index);
    if (audioUrl == null || audioUrl.isEmpty) throw Exception('No audio URL found');

    // Get title from RSS.
    final resp = await http.get(Uri.parse(rssUrl), headers: {
      'User-Agent': 'playlist-admin/2.0',
    });
    final doc = XmlDocument.parse(resp.body);
    final items = doc.findAllElements('item').toList();
    final title = index < items.length
        ? items[index].findAllElements('title').firstOrNull?.innerText ?? 'episode_$index'
        : 'episode_$index';

    final name = normalizeFileName(title);
    final ext = _guessExtension(audioUrl);
    final outDir = _podcastDir(podcastName);
    final outputPath = '$outDir\\$name.$ext';
    if (await File(outputPath).exists()) {
      onProgress(1.0);
      return false;
    }

    // Native HTTP download.
    final client = http.Client();
    final request = http.Request('GET', Uri.parse(audioUrl));
    final response = await client.send(request);
    if (response.statusCode != 200) {
      client.close();
      throw Exception('Download failed (${response.statusCode})');
    }
    final totalBytes = response.contentLength ?? 0;
    int received = 0;
    final sink = File(outputPath).openWrite();
    await for (final chunk in response.stream) {
      sink.add(chunk);
      received += chunk.length;
      if (totalBytes > 0) onProgress(received / totalBytes);
    }
    await sink.close();
    client.close();
    onProgress(1.0);
    return true;
  }

  /// Download subtitles via YoutubeService (native).
  Future<PodcastSubtitleResult> downloadSubtitles(
    String episodeTitle,
    String podcastName, {
    required void Function(String log) onLog,
  }) async {
    final outDir = _podcastDir(podcastName);
    final safeName = normalizeFileName(episodeTitle);
    final outputPath = '$outDir\\$safeName.mp3';

    if (await File(outputPath.replaceAll('.mp3', '.srt')).exists()) {
      onLog('已有字幕，跳過');
      return PodcastSubtitleResult.found;
    }

    // Use yt-dlp CLI for subtitles (youtube_explode doesn't support auto-captions well).
    final query = '$episodeTitle $podcastName';
    try {
      final proc = await Process.start(
        'python',
        ['tools\\flutter_download_bridge.py', 'youtube-subs', query, outputPath],
        runInShell: true,
        workingDirectory: ConfigService.instance.config.basePath,
        environment: {'PYTHONIOENCODING': 'utf-8'},
      );
      var result = PodcastSubtitleResult.failed;
      await proc.stdout.transform(utf8.decoder).transform(const LineSplitter()).forEach((line) {
        if (line.trim().isEmpty) return;
        try {
          final json = jsonDecode(line.trim()) as Map<String, dynamic>;
          final type = json['type'] as String?;
          if (type == 'log') onLog(json['message'] as String? ?? '');
          else if (type == 'error') { onLog('${json['message']}'); result = PodcastSubtitleResult.failed; }
          else if (type == 'not_found') { onLog('${json['message']}'); result = PodcastSubtitleResult.notFound; }
          else if (type == 'complete') { onLog('字幕下載完成'); result = PodcastSubtitleResult.found; }
        } catch (_) { onLog(line); }
      });
      await proc.exitCode;
      return result;
    } catch (e) {
      onLog('字幕下載失敗: $e');
      return PodcastSubtitleResult.failed;
    }
  }

  String _guessExtension(String url) {
    final path = Uri.tryParse(url)?.path ?? '';
    if (path.endsWith('.mp3')) return 'mp3';
    if (path.endsWith('.m4a')) return 'm4a';
    if (path.endsWith('.wav')) return 'wav';
    if (path.endsWith('.ogg')) return 'ogg';
    if (path.endsWith('.flac')) return 'flac';
    if (path.endsWith('.aac')) return 'aac';
    return 'mp3';
  }

  String get downloadPath => _downloadPath;
  String podcastDir(String? podcastName) => _podcastDir(podcastName);
  static String relativePodcastPath = 'podcasts';

  Future<List<PodcastSearchResult>> searchPodcasts(String query) async {
    final url = Uri.parse(
        'https://itunes.apple.com/search?term=${Uri.encodeQueryComponent(query)}&media=podcast&limit=20');
    final resp = await http.get(url, headers: {'User-Agent': 'playlist-admin/2.0'});
    if (resp.statusCode != 200) throw Exception('搜尋失敗 (${resp.statusCode})');
    final data = jsonDecode(resp.body) as Map<String, dynamic>;
    final results = data['results'] as List<dynamic>? ?? [];
    return results
        .map((r) => PodcastSearchResult.fromAppleJson(r as Map<String, dynamic>))
        .where((r) => r.feedUrl.isNotEmpty)
        .toList();
  }
}
