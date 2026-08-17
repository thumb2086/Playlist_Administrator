import 'dart:async';
import 'dart:io';
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/foundation.dart';
import '../services/config_service.dart';
import '../services/stream_server.dart';
import '../services/smtc_service.dart';

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
      _notify();
    });
    _player.onDurationChanged.listen((d) {
      _duration = d;
      _notify();
    });
    // Periodic SMTC push.
    _smtcTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!_isPlaying) return;
      SmtcService.instance.update(
        title: _title, artist: _artist,
        playing: true, position: _position, duration: _duration,
      );
    });
  }

  /// Play a local file.
  Future<void> playFile(String path, {String? title, String? artist}) async {
    _title = title ?? _titleFromPath(path);
    _artist = artist ?? _artistFromPath(path);
    _isPlaying = true;
    _notify();
    await _player.play(DeviceFileSource(path));
    _pushSmtc();
  }

  /// Play via streaming: resolve → transcode → local mp3.
  Future<void> playStream(String query, {String? title, String? artist}) async {
    _title = title ?? query;
    _artist = artist ?? '';
    _statusText = '串流中: ${_title}';
    _isPlaying = false;
    _notify();
    try {
      await StreamServer.instance.start();
      _statusText = '解析: $query';
      _notify();
      final localPath = await StreamServer.instance.resolveToFile(query);
      if (localPath.isEmpty || !File(localPath).existsSync()) {
        _statusText = '找不到: $query';
        _notify();
        return;
      }
      _statusText = '';
      _isPlaying = true;
      await _player.play(DeviceFileSource(localPath));
      _pushSmtc();
    } catch (e) {
      _statusText = '錯誤: $e';
      _notify();
    }
    _notify();
  }

  /// Smart play: local file if path exists, otherwise stream.
  Future<void> play(String pathOrQuery, {String? title, String? artist}) async {
    if (File(pathOrQuery).existsSync()) {
      await playFile(pathOrQuery, title: title, artist: artist);
    } else {
      await playStream(pathOrQuery, title: title, artist: artist);
    }
  }

  void setQueue(List<String> paths, {List<String>? titles, int startIndex = 0}) {
    _queue
      ..clear()
      ..addAll(paths);
    _queueTitles
      ..clear()
      ..addAll(titles ?? paths.map(_titleFromPath));
    _index = startIndex;
    _notify();
  }

  void addToQueue(String path, {String? title}) {
    _queue.add(path);
    _queueTitles.add(title ?? _titleFromPath(path));
    _notify();
  }

  void removeFromQueue(int index) {
    if (index < 0 || index >= _queue.length) return;
    _queue.removeAt(index);
    _queueTitles.removeAt(index);
    if (_index >= _queue.length) _index = _queue.length - 1;
    if (index < _index) _index--;
    _notify();
  }

  void moveInQueue(int oldIndex, int newIndex) {
    if (oldIndex < 0 || oldIndex >= _queue.length) return;
    if (newIndex < 0 || newIndex >= _queue.length) return;
    final path = _queue.removeAt(oldIndex);
    final title = _queueTitles.removeAt(oldIndex);
    _queue.insert(newIndex, path);
    _queueTitles.insert(newIndex, title);
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
    playFile(_queue[index], title: _queueTitles[index]);
  }

  void next() {
    if (_queue.isEmpty) return;
    if (_shuffle) {
      _index = DateTime.now().millisecondsSinceEpoch % _queue.length;
    } else {
      _index = (_index + 1) % _queue.length;
    }
    playFile(_queue[_index], title: _queueTitles[_index]);
  }

  void previous() {
    if (_queue.isEmpty) return;
    _index = (_index - 1 + _queue.length) % _queue.length;
    playFile(_queue[_index], title: _queueTitles[_index]);
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
      title: _title, artist: _artist,
      playing: _isPlaying, position: _position, duration: _duration,
    );
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
