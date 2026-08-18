import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../models/playlist_item.dart';
import '../services/config_service.dart';
import '../services/stream_server.dart';
import '../services/smtc_service.dart';
import '../services/playback_history.dart';
import '../services/metadata_reader.dart';

/// Central playback controller: owns the AudioPlayer, queue, and all state.
/// Used by both PlayerBar (bottom bar) and the queue drawer / PlayerPage.
class PlayerController {
  static PlayerController? _instance;
  static PlayerController get instance => _instance ??= PlayerController._();
  PlayerController._();

  final AudioPlayer _player = AudioPlayer();
  final List<String> _queue = [];           // local file paths
  final List<String> _queueTitles = [];     // display names
  int _index = -1;
  bool _isPlaying = false;
  bool _shuffle = false;
  bool _loop = true;
  double _volume = 0.7;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  String _title = '';
  String _artist = '';
  String? _coverPath;
  String _statusText = '';
  Timer? _smtcTimer;
  Timer? _sleepTimer;
  DateTime? _sleepEndsAt;
  bool _prefetching = false;
  // PlaylistItem data for prefetch (query + isrc per queue slot).
  final List<PlaylistItem> _queueItems = [];
  // Playback history scrobble state.
  String _recordedSongKey = '';
  // Cover art memory cache (path → bytes).
  final Map<String, Uint8List?> _artworkCache = {};

  // Getters
  AudioPlayer get player => _player;
  bool get isPlaying => _isPlaying;
  bool get shuffle => _shuffle;
  bool get loop => _loop;
  double get volume => _volume;
  Duration get position => _position;
  Duration get duration => _duration;
  String get title => _title;
  String get artist => _artist;
  String? get coverPath => _coverPath;
  int get index => _index;
  List<String> get queue => List.unmodifiable(_queue);
  List<String> get queueTitles => List.unmodifiable(_queueTitles);
  bool get hasTrack => _index >= 0 && _index < _queue.length;
  String get statusText => _statusText;
  DateTime? get sleepEndsAt => _sleepEndsAt;
  String get sleepRemainingText {
    final end = _sleepEndsAt;
    if (end == null) return '';
    final left = end.difference(DateTime.now());
    if (left.isNegative) return '';
    final m = left.inMinutes.remainder(60);
    final h = left.inHours;
    return h > 0 ? '$h時$m分' : '$m分';
  }

  void setSleepTimer(Duration? duration) {
    _sleepTimer?.cancel();
    _sleepTimer = null;
    _sleepEndsAt = null;
    if (duration == null) { _notify(); return; }
    _sleepTimer = Timer(duration, () {
      if (_isPlaying) { _player.pause(); _isPlaying = false; }
      _sleepEndsAt = null;
      _notify();
    });
    _sleepEndsAt = DateTime.now().add(duration);
    _notify();
  }

  final _listeners = <VoidCallback>[];
  void addListener(VoidCallback fn) => _listeners.add(fn);
  void removeListener(VoidCallback fn) => _listeners.remove(fn);
  void _notify() {
    for (final fn in _listeners) {
      try { fn(); } catch (_) {}
    }
  }

  void init() {
    _volume = ConfigService.instance.config.volume.clamp(0.0, 1.0);
    _player.setVolume(_volume);
    _player.onPlayerComplete.listen((_) {
      if (_loop || _shuffle) {
        next();
      } else {
        _isPlaying = false;
        _notify();
      }
    });
    _player.onPositionChanged.listen((p) {
      _position = p;
      _checkPlaybackRecord(p);
      _notify();
    });
    _player.onDurationChanged.listen((d) {
      _duration = d;
      _notify();
    });
    // Attach SMTC: media buttons → PlayerController.
    SmtcService.instance.attach(
      onPlayPause: togglePlay,
      onNext: next,
      onPrevious: previous,
      onStop: () { if (_isPlaying) { _player.pause(); _isPlaying = false; _notify(); } },
      onSeek: (pos) { seek(pos); },
    );
    // Periodic SMTC push.
    _smtcTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!_isPlaying) return;
      _pushSmtc();
    });
  }

  /// Play a local file.
  Future<void> playFile(String path, {String? title, String? artist, String? coverUrl}) async {
    StreamServer.instance.stopActive();
    await _player.stop();
    _title = title ?? _titleFromPath(path);
    _artist = artist ?? _artistFromPath(path);
    _coverPath = coverUrl;
    _recordedSongKey = '';
    _isPlaying = true;
    _notify();
    // Load embedded artwork if no cover URL provided.
    if (_coverPath == null) {
      _loadEmbeddedArtwork(path);
    }
    await _player.play(DeviceFileSource(path));
    _pushSmtc();
  }

  /// Play via true streaming: HTTP proxy pipes ffmpeg output → audioplayers plays URL.
  Future<void> playStream(String query, {String? title, String? artist, String? isrc, String? coverUrl}) async {
    StreamServer.instance.stopActive();
    await _player.stop();
    _title = title ?? query;
    _artist = artist ?? '';
    _coverPath = coverUrl;
    _recordedSongKey = '';
    _statusText = '串流中: ${_title}';
    _isPlaying = false;
    _notify();
    try {
      await StreamServer.instance.start();
      // Build HTTP stream URL — StreamServer._serveTranscoded handles resolve + ffmpeg pipe.
      final streamUrl = '${StreamServer.instance.baseUrl}/stream/${Uri.encodeComponent(query)}';
      _statusText = '連線: ${_title}';
      _notify();
      _isPlaying = true;
      await _player.play(UrlSource(streamUrl));
      _statusText = '';
      _pushSmtc();
    } catch (e) {
      // Fallback: download-then-play if streaming fails.
      _statusText = '降級下載: ${_title}';
      _notify();
      try {
        final localPath = await StreamServer.instance.resolveToFile(query, isrc: isrc);
        if (localPath.isEmpty || !File(localPath).existsSync()) {
          _statusText = '找不到: $query';
          _notify();
          return;
        }
        _statusText = '';
        _isPlaying = true;
        await _player.play(DeviceFileSource(localPath));
        _pushSmtc();
      } catch (e2) {
        _statusText = '錯誤: $e2';
        _notify();
      }
    }
    _notify();
  }

  /// Smart play: local file if path exists, otherwise stream.
  Future<void> play(String pathOrQuery, {String? title, String? artist, String? isrc, String? coverUrl}) async {
    if (File(pathOrQuery).existsSync()) {
      await playFile(pathOrQuery, title: title, artist: artist, coverUrl: coverUrl);
    } else {
      await playStream(pathOrQuery, title: title, artist: artist, isrc: isrc, coverUrl: coverUrl);
    }
  }

  /// Play podcast show: look up RSS feed, get episodes, play latest.
  Future<void> playPodcastShow(String showName) async {
    StreamServer.instance.stopActive();
    await _player.stop();
    _title = showName;
    _statusText = '載入 Podcast: $showName';
    _isPlaying = false;
    _notify();
    try {
      final cfg = ConfigService.instance.config;
      final rssUrl = cfg.podcastSubscriptions[showName];
      if (rssUrl == null || rssUrl.isEmpty) {
        _statusText = '找不到 RSS: $showName';
        _notify();
        return;
      }
      // Fetch RSS feed.
      final resp = await http.get(Uri.parse(rssUrl),
          headers: {'User-Agent': 'Mozilla/5.0'}).timeout(const Duration(seconds: 15));
      if (resp.statusCode != 200) {
        _statusText = 'RSS 載入失敗: ${resp.statusCode}';
        _notify();
        return;
      }
      // Parse XML for episodes with audio URLs.
      final episodes = _parseRssEpisodes(resp.body);
      if (episodes.isEmpty) {
        _statusText = '找不到集數: $showName';
        _notify();
        return;
      }
      // Play first episode (latest).
      final ep = episodes.first;
      _title = ep['title'] ?? showName;
      _artist = showName;
      _statusText = '播放: ${_title}';
      _notify();
      await _player.play(UrlSource(ep['url']!));
      _isPlaying = true;
      _pushSmtc();
    } catch (e) {
      _statusText = '錯誤: $e';
    }
    _notify();
  }

  /// Parse RSS XML to extract episodes with title + audio URL.
  List<Map<String, String>> _parseRssEpisodes(String xml) {
    final episodes = <Map<String, String>>[];
    final itemPattern = RegExp(r'<item>(.*?)</item>', dotAll: true);
    final titlePattern = RegExp(r'<title><!\[CDATA\[(.*?)\]\]></title>|<title>(.*?)</title>');
    final urlPattern = RegExp(r'<enclosure[^>]+url="([^"]+)"');
    for (final match in itemPattern.allMatches(xml)) {
      final item = match.group(1)!;
      final titleMatch = titlePattern.firstMatch(item);
      final title = (titleMatch?.group(1) ?? titleMatch?.group(2) ?? '').trim();
      final urlMatch = urlPattern.firstMatch(item);
      final url = urlMatch?.group(1) ?? '';
      if (url.isNotEmpty && (url.endsWith('.mp3') || url.endsWith('.m4a') || url.contains('audio'))) {
        episodes.add({'title': title, 'url': url});
      }
    }
    return episodes;
  }

  /// Play a PlaylistItem: direct RSS URL if available, else cache-first, else stream.
  Future<void> playItem(PlaylistItem item) async {
    StreamServer.instance.stopActive();
    await _player.stop();
    _title = item.name;
    _artist = item.artist;
    _coverPath = item.coverUrl;
    _recordedSongKey = '';
    _notify();

    // 1. Direct RSS URL (podcast).
    if (item.audioUrl != null && item.audioUrl!.isNotEmpty) {
      _statusText = '播放: ${item.name}';
      _isPlaying = true;
      _notify();
      // Cache RSS audio: play URL, cache in background.
      _cacheRssAudio(item);
      await _player.play(UrlSource(item.audioUrl!));
      _pushSmtc();
      _notify();
      return;
    }

    // 2. Check cache\stream\ first.
    final cached = StreamServer.instance.findCached(item.audioQuery);
    if (cached != null && File(cached).existsSync()) {
      await playFile(cached, title: item.name, artist: item.artist, coverUrl: item.coverUrl);
      return;
    }

    // 3. Check local music library.
    final local = _findLocalTrack(item.audioQuery);
    if (local != null) {
      await playFile(local, title: item.name, artist: item.artist, coverUrl: item.coverUrl);
      return;
    }

    // 4. Stream via YouTube.
    await playStream(item.audioQuery, title: item.name, artist: item.artist, isrc: item.isrc, coverUrl: item.coverUrl);
  }

  String? _findLocalTrack(String query) {
    final cfg = ConfigService.instance.config;
    final musicDir = Directory(cfg.musicPath);
    if (!musicDir.existsSync()) return null;
    final lower = query.toLowerCase();
    for (final f in musicDir.listSync().whereType<File>()) {
      if (f.path.endsWith('.mp3')) {
        final stem = f.uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '').toLowerCase();
        if (stem == lower || stem.contains(lower) || lower.contains(stem)) {
          return f.path;
        }
      }
    }
    return null;
  }

  void _cacheRssAudio(PlaylistItem item) async {
    try {
      final cacheDir = Directory('${ConfigService.instance.config.streamCachePath}');
      await cacheDir.create(recursive: true);
      final safeName = item.name.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_').trim();
      final outPath = '${cacheDir.path}\\$safeName.mp3';
      if (File(outPath).existsSync()) return;
      final resp = await http.get(Uri.parse(item.audioUrl!)).timeout(const Duration(seconds: 60));
      if (resp.statusCode == 200) {
        await File(outPath).writeAsBytes(resp.bodyBytes);
      }
    } catch (_) {}
  }


  /// Prefetch next track in background (called at 80% or after play starts).
  void _prefetchNext() {
    if (_prefetching || _queue.isEmpty || _index < 0) return;
    final nextIdx = _index + 1;
    if (nextIdx >= _queue.length) return;
    final nextPath = _queue[nextIdx];
    // Only prefetch if it's NOT a local file (needs download).
    if (File(nextPath).existsSync()) return;
    _prefetching = true;
    StreamServer.instance.start().then((_) {
      StreamServer.instance.resolveToFile(nextPath).then((_) {
        _prefetching = false;
      }).catchError((_) { _prefetching = false; });
    });
  }

  void setQueue(List<String> paths, {List<String>? titles, int startIndex = 0, List<PlaylistItem>? items}) {
    _queue
      ..clear()
      ..addAll(paths);
    _queueTitles
      ..clear()
      ..addAll(titles ?? paths.map(_titleFromPath));
    _queueItems
      ..clear()
      ..addAll(items ?? []);
    _index = startIndex;
    _notify();
  }

  void addToQueue(String path, {String? title, PlaylistItem? item}) {
    _queue.add(path);
    _queueTitles.add(title ?? _titleFromPath(path));
    if (item != null) _queueItems.add(item);
    _notify();
  }

  void removeFromQueue(int index) {
    if (index < 0 || index >= _queue.length) return;
    _queue.removeAt(index);
    _queueTitles.removeAt(index);
    if (index < _queueItems.length) _queueItems.removeAt(index);
    if (_index >= _queue.length) _index = _queue.length - 1;
    if (index < _index) _index--;
    _notify();
  }

  void clearQueue() {
    _queue.clear();
    _queueTitles.clear();
    _queueItems.clear();
    _index = -1;
    if (_isPlaying) { _player.stop(); _isPlaying = false; }
    _title = '';
    _artist = '';
    _position = Duration.zero;
    _duration = Duration.zero;
    _statusText = '';
    _notify();
  }

  void moveInQueue(int oldIndex, int newIndex) {
    if (oldIndex < 0 || oldIndex >= _queue.length) return;
    if (newIndex < 0 || newIndex >= _queue.length) return;
    final path = _queue.removeAt(oldIndex);
    final title = _queueTitles.removeAt(oldIndex);
    _queue.insert(newIndex, path);
    _queueTitles.insert(newIndex, title);
    if (oldIndex < _queueItems.length) {
      final item = _queueItems.removeAt(oldIndex);
      _queueItems.insert(newIndex, item);
    }
    if (_index == oldIndex) {
      _index = newIndex;
    } else if (oldIndex < _index && newIndex >= _index) {
      _index--;
    } else if (oldIndex > _index && newIndex <= _index) {
      _index++;
    }
    _notify();
  }

  void jumpTo(int index) {
    if (index < 0 || index >= _queue.length) return;
    _index = index;
    if (index < _queueItems.length && _queueItems[index] != null) {
      playItem(_queueItems[index]);
    } else {
      play(_queue[index], title: _queueTitles[index]);
    }
  }

  void next() {
    if (_queue.isEmpty) return;
    if (_shuffle) {
      _index = DateTime.now().millisecondsSinceEpoch % _queue.length;
    } else {
      _index = (_index + 1) % _queue.length;
    }
    if (_index < _queueItems.length && _queueItems[_index] != null) {
      playItem(_queueItems[_index]);
    } else {
      play(_queue[_index], title: _queueTitles[_index]);
    }
  }

  void previous() {
    if (_queue.isEmpty) return;
    _index = (_index - 1 + _queue.length) % _queue.length;
    if (_index < _queueItems.length && _queueItems[_index] != null) {
      playItem(_queueItems[_index]);
    } else {
      play(_queue[_index], title: _queueTitles[_index]);
    }
  }

  void togglePlay() {
    if (_isPlaying) {
      _player.pause();
      _isPlaying = false;
    } else {
      _player.resume();
      _isPlaying = true;
    }
    _notify();
    _pushSmtc();
  }

  void toggleShuffle() { _shuffle = !_shuffle; _notify(); }
  void toggleLoop() { _loop = !_loop; _notify(); }

  Future<void> setVolume(double v) async {
    _volume = v.clamp(0.0, 1.0);
    await _player.setVolume(_volume);
    ConfigService.instance.config.volume = _volume;
    ConfigService.instance.save();
    _notify();
  }

  Future<void> seek(Duration pos) async {
    await _player.seek(pos);
    _position = pos;
    _notify();
    _pushSmtc();
  }

  void _pushSmtc() {
    SmtcService.instance.update(
      title: _title, artist: _artist, artworkUrl: _coverPath,
      playing: _isPlaying, position: _position, duration: _duration,
    );
  }

  /// Scrobble: record track when listened to >=50% (capped at 4 min).
  void _checkPlaybackRecord(Duration position) {
    if (_title.isEmpty || _duration.inMilliseconds == 0) return;
    final stem = _title.toLowerCase();
    if (stem == _recordedSongKey) return;
    final thresholdMs = (_duration.inMilliseconds ~/ 2)
        .clamp(0, const Duration(minutes: 4).inMilliseconds);
    if (position.inMilliseconds < thresholdMs) return;
    _recordedSongKey = stem;
    PlaybackHistory.instance.record(_title, _artist, _duration);
  }

  /// Load embedded artwork from a local audio file in background.
  void _loadEmbeddedArtwork(String path) async {
    if (_artworkCache.containsKey(path)) {
      final cached = _artworkCache[path];
      if (cached != null) {
        _coverPath = 'mem:${path.hashCode}';
        _notify();
      }
      return;
    }
    try {
      final meta = await MetadataReader.read(path);
      _artworkCache[path] = meta.artwork;
      if (meta.artwork != null && meta.artwork!.isNotEmpty) {
        _coverPath = 'mem:${path.hashCode}';
        _notify();
        _pushSmtc();
      }
    } catch (_) {}
  }

  /// Get cached artwork bytes (for PlayerBar to display).
  Uint8List? getArtworkBytes() {
    final cp = _coverPath;
    if (cp == null || !cp.startsWith('mem:')) return null;
    // Search all cached entries for matching hash.
    for (final entry in _artworkCache.entries) {
      if ('mem:${entry.key.hashCode}' == cp) return entry.value;
    }
    return null;
  }

  String _titleFromPath(String path) {
    final stem = File(path).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
    if (stem.contains(' - ')) return stem.split(' - ').first.trim();
    return stem;
  }

  String _artistFromPath(String path) {
    final stem = File(path).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
    if (stem.contains(' - ')) return stem.split(' - ').sublist(1).join(' - ').trim();
    return '';
  }

  void dispose() {
    _smtcTimer?.cancel();
    _player.dispose();
  }
}
