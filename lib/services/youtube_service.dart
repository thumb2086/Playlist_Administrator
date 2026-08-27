import 'dart:async';
import 'package:youtube_explode_dart/youtube_explode_dart.dart';
import 'package:logger/logger.dart';

final _log = Logger(printer: PrettyPrinter(methodCount: 0));

/// YouTube 串流服務：搜尋 + 取音訊 URL（全原生 Dart，零 Python 依賴）。
///
/// 用 `youtube_explode_dart` 直接與 YouTube 溝通，不需要 yt-dlp CLI。
class YoutubeService {
  YoutubeService._();
  static final instance = YoutubeService._();

  final YoutubeExplode _yt = YoutubeExplode();
  bool _closed = false;

  /// 搜尋 YouTube 並回傳前 N 個結果。
  Future<List<YoutubeSearchResult>> search(String query, {int limit = 5}) async {
    if (_closed) return [];
    try {
      final searchList = await _yt.search.search(query);
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
    }
  }

  /// 根據 videoId 取得最佳音訊串流 URL。
  /// 回傳可直接播放的 HTTP URL。
  Future<String?> getAudioUrl(String videoId) async {
    if (_closed) return null;
    try {
      final manifest = await _yt.videos.streams.getManifest(VideoId(videoId));
      final audioOnly = manifest.audioOnly.sortByBitrate();
      if (audioOnly.isEmpty) return null;
      final best = audioOnly.last;
      _log.i('YouTube 音訊: ${best.bitrate} (${best.container})');
      return best.url.toString();
    } catch (e) {
      _log.e('YouTube 取串流失敗: $e');
      return null;
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

  void close() {
    _closed = true;
    _yt.close();
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
