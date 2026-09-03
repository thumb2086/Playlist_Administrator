import 'dart:async';
import 'dart:io';
import 'package:youtube_explode_dart/youtube_explode_dart.dart';
import 'package:logger/logger.dart';
import 'config_service.dart';

final _log = Logger(printer: PrettyPrinter(methodCount: 0));

/// YouTube 串流服務：搜尋 + 取音訊 URL + 下載（全原生 Dart，零 Python 依賴）。
///
/// 用 `youtube_explode_dart` 直接與 YouTube 溝通，不需要 yt-dlp CLI。
class YoutubeService {
  YoutubeService._();
  static final instance = YoutubeService._();

  bool _closed = false;

  /// Create fresh instance per call to avoid stale connections.
  YoutubeExplode _fresh() => YoutubeExplode();

  String get _ffmpeg => ConfigService.instance.config.resolvedFfmpegPath;

  // ── URL 解析 ──────────────────────────────────────────
  /// 從 YouTube URL 解析出 VideoId。
  /// 支援格式: youtube.com/watch?v=xxx, youtu.be/xxx, youtube.com/embed/xxx
  static VideoId? parseVideoId(String input) {
    final trimmed = input.trim();
    // 嘗試直接當作 video ID（11 字元）
    if (RegExp(r'^[a-zA-Z0-9_-]{11}$').hasMatch(trimmed)) {
      return VideoId(trimmed);
    }
    // 嘗試從 URL 解析
    try {
      final uri = Uri.parse(trimmed);
      // youtu.be/xxx
      if (uri.host.contains('youtu.be')) {
        final id = uri.pathSegments.isNotEmpty ? uri.pathSegments.first : '';
        if (id.length == 11) return VideoId(id);
      }
      // youtube.com/watch?v=xxx
      if (uri.queryParameters.containsKey('v')) {
        final id = uri.queryParameters['v']!;
        if (id.length == 11) return VideoId(id);
      }
      // youtube.com/embed/xxx or youtube.com/v/xxx
      final pathSegments = uri.pathSegments;
      if (pathSegments.length >= 2) {
        final prefix = pathSegments[pathSegments.length - 2];
        if (prefix == 'embed' || prefix == 'v') {
          final id = pathSegments.last;
          if (id.length == 11) return VideoId(id);
        }
      }
    } catch (_) {}
    return null;
  }

  // ── 搜尋 ─────────────────────────────────────────────
  /// 搜尋 YouTube 並回傳前 N 個結果。
  Future<List<YoutubeSearchResult>> search(String query, {int limit = 5}) async {
    if (_closed) return [];
    final yt = _fresh();
    try {
      final searchList = await yt.search.search(query);
      final results = searchList.take(limit).map((v) => YoutubeSearchResult(
        videoId: v.id.value,
        title: v.title,
        author: v.author,
        duration: v.duration ?? Duration.zero,
        thumbnailUrl: v.thumbnails.highResUrl,
      )).toList();
      _log.i('YouTube 搜尋 "$query" → ${results.length} 筆結果');
      return results;
    } catch (e) {
      _log.e('YouTube 搜尋失敗: $e');
      return [];
    } finally {
      yt.close();
    }
  }

  /// 根據 videoId 取得最佳音訊串流 URL。
  /// 回傳可直接播放的 HTTP URL。
  Future<String?> getAudioUrl(String videoId) async {
    if (_closed) return null;
    final yt = _fresh();
    try {
      final manifest = await yt.videos.streams.getManifest(VideoId(videoId));
      final audioOnly = manifest.audioOnly.sortByBitrate();
      if (audioOnly.isEmpty) return null;
      final best = audioOnly.last;
      _log.i('YouTube 音訊: ${best.bitrate} (${best.container})');
      return best.url.toString();
    } catch (e) {
      _log.e('YouTube 取串流失敗: $e');
      return null;
    } finally {
      yt.close();
    }
  }

  /// 根據查詢一次搞定：搜尋 → 取最佳音訊 URL。
  /// 回傳 best match 的 URL 和元資料。自動重試 1 次。
  Future<YoutubeStreamResult?> resolveStream(String query) async {
    for (int attempt = 0; attempt < 2; attempt++) {
      try {
        final results = await search(query, limit: 5)
            .timeout(const Duration(seconds: 20), onTimeout: () => []);
        if (results.isEmpty) continue;

        final best = results.first;
        final url = await getAudioUrl(best.videoId)
            .timeout(const Duration(seconds: 15), onTimeout: () => null);
        if (url == null) continue;

        return YoutubeStreamResult(
          videoId: best.videoId,
          title: best.title,
          author: best.author,
          duration: best.duration,
          thumbnailUrl: best.thumbnailUrl,
          audioUrl: url,
        );
      } catch (e) {
        _log.e('YouTube resolve 失敗 (attempt ${attempt + 1}): $e');
        if (attempt == 0) await Future.delayed(const Duration(seconds: 1));
      }
    }
    return null;
  }

  // ── URL 下載（取代 Python bridge download-youtube）──
  /// 從 YouTube URL 下載音訊並轉碼為指定格式。
  /// [url] - YouTube URL 或 video ID
  /// [outputPath] - 輸出檔案完整路徑（含副檔名）
  /// [format] - 目標格式（預設 mp3）
  /// [onProgress] - 進度回調 (0.0~1.0)
  Future<String?> downloadFromUrl(
    String url, {
    required String outputPath,
    String format = 'mp3',
    void Function(double progress)? onProgress,
  }) async {
    final videoId = parseVideoId(url);
    if (videoId == null) {
      _log.e('無法解析 YouTube URL: $url');
      return null;
    }

    // 取得音訊串流 URL
    onProgress?.call(0.1);
    final audioUrl = await getAudioUrl(videoId.value);
    if (audioUrl == null) {
      _log.e('無法取得音訊串流: $url');
      return null;
    }

    // 用 YoutubeExplode 下載 + 本地 ffmpeg 轉碼
    onProgress?.call(0.1);
    final result = await downloadAudio(
      audioUrl,
      outputPath: outputPath,
      format: format,
      onProgress: onProgress,
      videoId: videoId.value,
    );

    return result;
  }

  // ── 搜尋下載（取代 Python bridge download-song）─────
  /// 搜尋 YouTube 並下載最佳匹配的音訊。
  /// [query] - 搜尋字串（如 "周杰倫 晴天"）
  /// [outputPath] - 輸出檔案完整路徑（含副檔名）
  /// [format] - 目標格式（預設 mp3）
  Future<String?> downloadBySearch(
    String query, {
    required String outputPath,
    String format = 'mp3',
    void Function(double progress)? onProgress,
  }) async {
    // 搜尋 + 取得音訊 URL
    onProgress?.call(0.05);
    final result = await resolveStream(query);
    if (result == null) {
      _log.e('搜尋下載失敗: $query');
      return null;
    }

    // 用 YoutubeExplode 下載 + 本地 ffmpeg 轉碼
    onProgress?.call(0.1);
    final savedPath = await downloadAudio(
      result.audioUrl,
      outputPath: outputPath,
      format: format,
      onProgress: onProgress,
      videoId: result.videoId,
    );

    if (savedPath != null) {
      _log.i('搜尋下載完成: ${result.title} → $savedPath');
    }
    return savedPath;
  }

  // ── 底層下載 ─────────────────────────────────────────
  /// 用 yt-dlp CLI 下載並轉碼 YouTube 音訊。
  /// yt-dlp -x --audio-format mp3 一步搞定（下載 + 轉碼）。
  Future<String?> downloadAudio(
    String audioUrl, {
    required String outputPath,
    String format = 'mp3',
    void Function(double progress)? onProgress,
    String? videoId,
  }) async {
    final ytUrl = videoId != null ? 'https://www.youtube.com/watch?v=$videoId' : audioUrl;
    onProgress?.call(0.1);

    try {
      // yt-dlp -x extracts audio, --audio-format converts, -o sets output
      // 使用 mweb client 繞過 PO Token 要求（ios/web 需要 PO Token）
      final proc = await Process.start(
        'yt-dlp',
        [
          '-x',
          '--audio-format', format,
          '--no-playlist',
          '--no-overwrites',
          '--no-check-certificates',
          '--extractor-args', 'youtube:player_client=mweb',
          '-o', outputPath,
          ytUrl,
        ],
        runInShell: true,
      );
      final code = await proc.exitCode.timeout(
        const Duration(seconds: 180),
        onTimeout: () { proc.kill(); return -1; },
      );

      if (code != 0) {
        _log.w('yt-dlp 失敗 (exit $code)');
        onProgress?.call(0.0);
        return null;
      }

      // yt-dlp may append extension — find the actual output file
      final expectedPath = outputPath;
      if (await File(expectedPath).exists()) {
        onProgress?.call(1.0);
        return expectedPath;
      }
      // Try with format extension appended
      final withExt = '$outputPath.$format';
      if (await File(withExt).exists()) {
        if (await File(expectedPath).exists()) await File(expectedPath).delete();
        await File(withExt).rename(expectedPath);
        onProgress?.call(1.0);
        return expectedPath;
      }
      // Search for any file matching the output prefix
      final dir = File(outputPath).parent;
      final prefix = File(outputPath).uri.pathSegments.last;
      await for (final f in dir.list()) {
        if (f is File && f.path.contains(prefix)) {
          if (f.path != expectedPath) {
            await File(expectedPath).delete();
            await f.rename(expectedPath);
          }
          onProgress?.call(1.0);
          return expectedPath;
        }
      }

      _log.w('yt-dlp 找不到輸出檔案');
      onProgress?.call(0.0);
      return null;
    } catch (e) {
      _log.e('yt-dlp 異常: $e');
      return null;
    }
  }

  void close() {
    _closed = true;
  }
}

/// 搜尋結果。
class YoutubeSearchResult {
  final String videoId;
  final String title;
  final String author;
  final Duration duration;
  final String thumbnailUrl;

  const YoutubeSearchResult({
    required this.videoId,
    required this.title,
    required this.author,
    required this.duration,
    required this.thumbnailUrl,
  });
}

/// 解析後的串流結果（含可播放 URL）。
class YoutubeStreamResult extends YoutubeSearchResult {
  final String audioUrl;

  const YoutubeStreamResult({
    required super.videoId,
    required super.title,
    required super.author,
    required super.duration,
    required super.thumbnailUrl,
    required this.audioUrl,
  });
}
