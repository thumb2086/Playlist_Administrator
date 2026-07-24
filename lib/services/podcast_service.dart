import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../models/podcast_episode.dart';
import '../models/podcast_search_result.dart';
import 'config_service.dart';

class PodcastService {
  static PodcastService? _instance;
  static PodcastService get instance => _instance ??= PodcastService._();
  PodcastService._();

  String get _pythonPath => 'python';

  String get _bridgePath {
    // Primary: tools/ next to the exe (installed/release layout)
    final exeDir = File(Platform.resolvedExecutable).parent.path;
    final exeCandidate = '$exeDir\\tools\\flutter_download_bridge.py';
    if (File(exeCandidate).existsSync()) return exeCandidate;
    // Walk-up from exe (development layout: exe deep in build/)
    Directory? d = Directory(exeDir);
    while (d != null) {
      final candidate = '${d.path}\\tools\\flutter_download_bridge.py';
      if (File(candidate).existsSync()) return candidate;
      final parent = d.parent;
      d = parent.path == d.path ? null : parent;
    }
    // Fallback: check current directory
    final cwd = Directory.current.path;
    final cwdCandidate = '$cwd\\tools\\flutter_download_bridge.py';
    if (File(cwdCandidate).existsSync()) return cwdCandidate;
    return '';
  }

  String _podcastDir(String? podcastName) {
    final base = ConfigService.instance.config.basePath;
    if (base.isEmpty) return '';
    final sub = podcastName != null && podcastName.isNotEmpty
        ? podcastName.replaceAll(RegExp(r'[<>:"/\\|?*]'), '_')
        : '';
    final path = sub.isNotEmpty ? '$base\\podcast_downloads\\$sub' : '$base\\podcast_downloads';
    Directory(path).createSync(recursive: true);
    return path;
  }

  String get _downloadPath => _podcastDir(null);

  Future<List<String>> _runPython(List<String> args) async {
    final bridge = _bridgePath;
    if (bridge.isEmpty) throw Exception('Base path not configured');
    final env = Map<String, String>.from(Platform.environment);
    env['PYTHONIOENCODING'] = 'utf-8';
    final proc = await Process.start(
      _pythonPath,
      [bridge, ...args],
      runInShell: true,
      workingDirectory: ConfigService.instance.config.basePath,
      environment: env,
    );
    final lines = <String>[];
    proc.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen(
      (line) {
        if (line.trim().isNotEmpty) lines.add(line.trim());
      },
    );
    final stderrLines = <String>[];
    proc.stderr.transform(utf8.decoder).transform(const LineSplitter()).listen(
      (line) {
        if (line.trim().isNotEmpty) stderrLines.add(line.trim());
      },
    );
    await proc.exitCode;
    if (stderrLines.isNotEmpty) {
      throw Exception(stderrLines.join('\n'));
    }
    return lines;
  }

  Future<Map<String, dynamic>> _runPythonJson(List<String> args) async {
    final lines = await _runPython(args);
    for (final line in lines) {
      try {
        final json = jsonDecode(line) as Map<String, dynamic>;
        if (json['type'] == 'error') {
          throw Exception(json['message'] as String? ?? 'Unknown error');
        }
        if (json['type'] == 'rss_list') return json;
        if (json['type'] == 'rss_audio') return json;
      } catch (e) {
        if (e is Exception) rethrow;
      }
    }
    throw Exception('No valid response from Python bridge');
  }

  Future<({String title, List<PodcastEpisode> episodes})> fetchEpisodes(
      String rssUrl) async {
    final result = await _runPythonJson(['rss-list', rssUrl]);
    final title = result['title'] as String? ?? '';
    final episodes = (result['episodes'] as List<dynamic>?)
            ?.map((e) => PodcastEpisode.fromJson(e as Map<String, dynamic>))
            .toList() ??
        [];
    return (title: title, episodes: episodes);
  }

  Future<String?> getAudioUrl(String rssUrl, int index) async {
    final result = await _runPythonJson(['rss-get-audio', rssUrl, index.toString()]);
    return result['audio_url'] as String?;
  }

  /// Normalize podcast filename: same logic used by downloadEpisode
  static String normalizeFileName(String title) {
    // Remove YouTube IDs [xxxxx], then sanitize illegal file chars
    return title
        .replaceAll(RegExp(r'\s*\[[\w-]{11}\]'), '')
        .replaceAll(RegExp(r'[<>:"/\\|?*]'), '_')
        .trim();
  }

  bool isEpisodeDownloaded(String title, String audioUrl, {String? podcastName}) {
    final ext = _guessExtension(audioUrl);
    final name = normalizeFileName(title);

    // 1. Exact filename match in the correct podcast directory
    final podDir = podcastName != null ? _podcastDir(podcastName) : _downloadPath;
    if (File('$podDir\\$name.$ext').existsSync()) return true;

    // 2. EP-number fallback: extract EP number from both title and existing files
    final titleEp = RegExp(r'EP(\d+)', caseSensitive: false).firstMatch(title);
    if (titleEp == null) return false;
    final epNum = titleEp.group(1)!;
    final epNumInt = int.tryParse(epNum);
    if (epNumInt == null) return false;

    final searchDir = Directory(podDir);
    if (!searchDir.existsSync()) return false;
    try {
      return searchDir.listSync().any((f) {
        if (f is! File) return false;
        final fname = f.uri.pathSegments.last;
        // Skip preview episodes
        if (fname.startsWith('【試聽】') || fname.startsWith('【')) return false;
        // Extract EP number from existing file
        final fileEp = RegExp(r'EP(\d+)', caseSensitive: false).firstMatch(fname);
        if (fileEp == null) return false;
        final fileEpInt = int.tryParse(fileEp.group(1)!);
        // Compare numerically: EP1 == EP001 == EP01
        return fileEpInt == epNumInt;
      });
    } catch (_) {}
    return false;
  }

  String episodeOutputPath(String title, String audioUrl) {
    final safeName = title.replaceAll(RegExp(r'[<>:"/\\|?*]'), '_');
    final ext = _guessExtension(audioUrl);
    return '$_downloadPath\\$safeName.$ext';
  }

  /// Returns true if downloaded, false if skipped (already exists)
  Future<bool> downloadEpisode(
    String rssUrl,
    int index,
    void Function(double progress) onProgress, {
    String? podcastName,
  }) async {
    final result = await _runPythonJson(['rss-get-audio', rssUrl, index.toString()]);
    final audioUrl = result['audio_url'] as String?;
    final title = result['title'] as String? ?? 'episode_$index';
    if (audioUrl == null || audioUrl.isEmpty) {
      throw Exception('No audio URL found');
    }
    final name = normalizeFileName(title);
    final ext = _guessExtension(audioUrl);
    final outDir = _podcastDir(podcastName);
    final outputPath = '$outDir\\$name.$ext';

    if (await File(outputPath).exists()) {
      onProgress(1.0);
      return false;
    }

    final bridge = _bridgePath;
    if (bridge.isEmpty) throw Exception('Base path not configured');
    final env = Map<String, String>.from(Platform.environment);
    env['PYTHONIOENCODING'] = 'utf-8';
    final proc = await Process.start(
      _pythonPath,
      [bridge, 'rss-download', audioUrl, outputPath],
      runInShell: true,
      workingDirectory: ConfigService.instance.config.basePath,
      environment: env,
    );

    proc.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen(
      (line) {
        if (line.trim().isEmpty) return;
        try {
          final json = jsonDecode(line.trim()) as Map<String, dynamic>;
          if (json['type'] == 'progress') {
            final pct = (json['percent'] as num?)?.toDouble() ?? 0;
            onProgress(pct / 100);
          } else if (json['type'] == 'error') {
            throw Exception(json['message'] as String? ?? 'Download failed');
          }
        } catch (e) {
          if (e is Exception) rethrow;
        }
      },
    );
    await proc.exitCode;
    onProgress(1.0);
    return true;
  }

  /// Download YouTube subtitles for a podcast episode instead of RSS audio
  Future<bool> downloadSubtitles(
    String episodeTitle,
    String podcastName, {
    required void Function(String log) onLog,
  }) async {
    final bridge = _bridgePath;
    if (bridge.isEmpty) throw Exception('Base path not configured');

    final query = '$episodeTitle $podcastName';
    final outDir = _podcastDir(podcastName);
    final safeName = normalizeFileName(episodeTitle);
    final outputPath = '$outDir\\$safeName.mp3'; // placeholder ext, bridge outputs .srt

    final env = Map<String, String>.from(Platform.environment);
    env['PYTHONIOENCODING'] = 'utf-8';

    if (await File(outputPath.replaceAll('.mp3', '.srt')).exists()) {
      onLog('⏭️ 已有字幕，跳過');
      return false;
    }

    final proc = await Process.start(
      _pythonPath,
      [bridge, 'youtube-subs', query, outputPath],
      runInShell: true,
      workingDirectory: ConfigService.instance.config.basePath,
      environment: env,
    );

    await proc.stdout.transform(utf8.decoder).transform(const LineSplitter()).forEach((line) {
      if (line.trim().isEmpty) return;
      try {
        final json = jsonDecode(line.trim()) as Map<String, dynamic>;
        final type = json['type'] as String?;
        if (type == 'log') {
          onLog(json['message'] as String? ?? '');
        } else if (type == 'error') {
          onLog('❌ ${json['message']}');
        } else if (type == 'complete') {
          onLog('✅ 字幕下載完成');
        }
      } catch (_) {
        onLog(line);
      }
    });
    await proc.exitCode;
    return true;
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

  /// Get the podcast directory for a specific podcast name.
  String podcastDir(String? podcastName) => _podcastDir(podcastName);

  /// 取得 Podcast 下載目錄路徑（相對於 base_path）
  static String relativePodcastPath = 'podcast_downloads';

  /// 透過 Apple Podcasts Search API 搜尋 podcast（免 API Key）
  Future<List<PodcastSearchResult>> searchPodcasts(String query) async {
    final url = Uri.parse(
        'https://itunes.apple.com/search?term=${Uri.encodeQueryComponent(query)}&media=podcast&limit=20');
    final resp = await http.get(url, headers: {
      'User-Agent': 'PlaylistAdministrator/2.0',
    });
    if (resp.statusCode != 200) {
      throw Exception('搜尋失敗 (${resp.statusCode})');
    }
    final data = jsonDecode(resp.body) as Map<String, dynamic>;
    final results = data['results'] as List<dynamic>? ?? [];
    return results
        .map((r) => PodcastSearchResult.fromAppleJson(r as Map<String, dynamic>))
        .where((r) => r.feedUrl.isNotEmpty)
        .toList();
  }
}
