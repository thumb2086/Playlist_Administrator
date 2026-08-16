import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show LogicalKeyboardKey;
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import '../services/config_service.dart';
import '../services/favorites_service.dart';
import '../services/i18n.dart';
import '../services/smtc_service.dart';
import '../services/discord_rpc_service.dart';
import '../services/lrc_parser.dart';
import '../services/metadata_reader.dart';
import '../services/playback_history.dart';
import '../widgets/dark_theme.dart';

class PlayerPage extends StatefulWidget {
  const PlayerPage({super.key});
  @override
  State<PlayerPage> createState() => _PlayerPageState();
}

class _PlayerPageState extends State<PlayerPage> {
  final _player = AudioPlayer();
  final _playlistCtrl = ScrollController();
  final _searchCtrl = TextEditingController();

  List<String> _songs = [];
  List<String> _displaySongs = [];
  List<String> _filteredSongs = [];
  List<String> _playQueue = [];
  int _queueIndex = -1;
  bool _playInFlight = false;
  int _loadGen = 0;
  bool _isPlaying = false;
  bool _shuffle = false;
  bool _loop = true;
  double _volume = 0.7;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
  String _smtcTitle = '';
  String _smtcArtist = '';
  Timer? _smtcTimer;
  String _recordedSongKey = '';
  String _recordedSongTitle = '';
  String _recordedSongArtist = '';
  Timer? _sleepTimer;
  DateTime? _sleepEndsAt;
  List<LrcLine> _lyrics = [];
  double _lyricsOffset = 0.0;
  String _currentLyric = '';
  String _statusText = '';
  String _displayPlaylistName = '';
  List<String> _playlistNames = [];
  Timer? _positionTimer;
  StreamSubscription? _positionSub;

  final Map<String, List<LrcLine>> _lyricsCache = {};
  final Map<String, Uint8List?> _artworkCache = {};
  Uint8List? _currentArtwork;
  Set<String> _favorites = {};

  @override
  void initState() {
    super.initState();
    _volume = ConfigService.instance.config.volume.clamp(0.0, 1.0);
    _player.setVolume(_volume);
    _loadQueue();
    _statusText = t('common.done');
    I18N.instance.addListener(() { if (mounted) setState(() {}); });
    _player.onPlayerComplete.listen((_) {
      if (!mounted) return;
      if (_loop || _shuffle) {
        _next();
      } else {
        setState(() => _isPlaying = false);
      }
    });
    _positionSub = _player.onPositionChanged.listen((p) {
      if (!mounted) return;
      setState(() => _position = p);
      _updateLyrics(p);
      _checkPlaybackRecord(p);
    });
    _player.onDurationChanged.listen((d) {
      if (mounted) setState(() => _duration = d);
    });
    _searchCtrl.addListener(_onSearchChanged);
    _refreshPlaylistNames();
    _initSmtc();
  }

  void _initSmtc() {
    SmtcService.instance.attach(
      onPlayPause: () {
        if (_songs.isEmpty) return;
        _togglePlay();
        _pushSmtcState();
      },
      onNext: () { _next(); _pushSmtcState(); },
      onPrevious: () { _prev(); _pushSmtcState(); },
      onStop: () {
        if (_isPlaying) {
          _player.pause();
          setState(() => _isPlaying = false);
          _pushSmtcState();
        }
      },
      onSeek: (pos) {
        if (_queueIndex < 0 || _queueIndex >= _playQueue.length) return;
        _seekTo(pos);
      },
    );
    _pushSmtcState();
    _initDiscordRpc();
    // Keep the OS timeline in sync while playing (throttled).
    _smtcTimer = Timer.periodic(const Duration(seconds: 1), (_) async {
      if (!_isPlaying) return;
      final pos = await _player.getCurrentPosition();
      final dur = await _player.getDuration();
      if ((pos == null || pos.inMilliseconds <= 0) &&
          (dur == null || dur.inMilliseconds <= 0)) return;
      SmtcService.instance.update(
        title: _smtcTitle,
        artist: _smtcArtist,
        album: _displayPlaylistName,
        artworkUrl: _currentArtworkUrl,
        playing: true,
        position: pos ?? Duration.zero,
        duration: dur ?? Duration.zero,
      );
    });
  }

  void _initDiscordRpc() {
    final config = ConfigService.instance.config;
    if (!config.discordPresenceEnabled) return;
    DiscordRpcService.instance.attach(
      enabled: true,
      applicationId: config.discordApplicationId,
      onReady: _pushSmtcState,
    );
  }

  void _pushSmtcState() async {
    final song = _queueIndex >= 0 && _queueIndex < _playQueue.length
        ? _playQueue[_queueIndex]
        : null;
    if (song == null) {
      SmtcService.instance.update(playing: _isPlaying);
      return;
    }
    final stem = File(song).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
    String title = stem;
    String artist = '';
    if (stem.contains(' - ')) {
      final parts = stem.split(' - ');
      if (parts.length >= 2) {
        title = parts.first.trim();
        artist = parts.sublist(1).join(' - ').trim();
      }
    }
    _smtcTitle = title;
    _smtcArtist = artist;
    final pos = await _player.getCurrentPosition();
    final dur = await _player.getDuration();
    _position = pos ?? Duration.zero;
    _duration = dur ?? Duration.zero;
    SmtcService.instance.update(
      title: title,
      artist: artist,
      album: _displayPlaylistName,
      artworkUrl: _currentArtworkUrl,
      playing: _isPlaying,
      position: _position,
      duration: _duration,
    );
    DiscordRpcService.instance.update(
      title: title,
      artist: artist,
      album: _displayPlaylistName,
      artworkUrl: _currentArtworkUrl,
      playing: _isPlaying,
      position: _position,
      duration: _duration,
    );
  }

  Future<void> _refreshPlaylistNames() async {
    final plDir = Directory(ConfigService.instance.config.playlistsPath);
    final names = await _listPlaylists(plDir);
    final favs = await FavoritesService.load();
    if (mounted) setState(() {
      _playlistNames = names;
      _favorites = favs;
    });
  }

  @override
  void dispose() {
    _positionSub?.cancel();
    _positionTimer?.cancel();
    _smtcTimer?.cancel();
    _player.dispose();
    _playlistCtrl.dispose();
    _searchCtrl.dispose();
    super.dispose();
  }

  void _onSearchChanged() {
    final q = _searchCtrl.text.trim().toLowerCase();
    setState(() {
      if (q.isEmpty) {
        _filteredSongs = List.from(_displaySongs);
      } else {
        _filteredSongs = _displaySongs.where((s) {
          final name = File(s).uri.pathSegments.last.toLowerCase();
          return name.contains(q);
        }).toList();
      }
    });
  }

  void _scrollToCurrent() {
    if (_queueIndex < 0 || _queueIndex >= _playQueue.length) return;
    final song = _playQueue[_queueIndex];
    final idx = _filteredSongs.indexOf(song);
    if (idx < 0) return;
    Future.delayed(const Duration(milliseconds: 100), () {
      if (_playlistCtrl.hasClients) {
        _playlistCtrl.animateTo(
          (idx * 40.0).clamp(0.0, _playlistCtrl.position.maxScrollExtent),
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _loadPlaylist(String name, {bool browseOnly = false}) async {
    final gen = ++_loadGen;
    final plPath = '${ConfigService.instance.config.playlistsPath}\\$name.m3u8';
    final file = File(plPath);
    if (!await file.exists()) {
      if (gen != _loadGen) return;
      setState(() => _statusText = '找不到播放清單: $name');
      return;
    }
    final stat = await file.stat();
    if (stat.size == 0) {
      if (gen != _loadGen) return;
      setState(() => _statusText = '播放清單是空的');
      return;
    }

    final lines = await file.readAsLines();
    final songs = <String>[];
    final musicDir = ConfigService.instance.config.musicPath;
    for (final line in lines) {
      if (gen != _loadGen) return;
      final raw = line.trim();
      if (raw.isEmpty || raw.startsWith('#')) continue;
      String decodePath(String s) {
        try { return Uri.decodeComponent(s); } catch (_) { return s; }
      }
      final trimmed = decodePath(raw);
      if (File(trimmed).existsSync()) { songs.add(trimmed); continue; }
      final fname = File(trimmed).uri.pathSegments.last;
      bool found = false;
      for (final ext in ['.mp3', '.m4a', '.flac']) {
        if (await File('$musicDir\\$fname$ext').exists()) { songs.add('$musicDir\\$fname$ext'); found = true; break; }
      }
      if (found) continue;
      final stem = fname.replaceAll(RegExp(r'\.\w+$'), '').toLowerCase();
      if (stem.contains(' - ')) {
        final parts = stem.split(' - ');
        if (parts.length >= 2) {
          final rev = '${parts[1]} - ${parts[0]}';
          for (final ext in ['.mp3', '.m4a', '.flac']) {
            if (await File('$musicDir\\$rev$ext').exists()) { songs.add('$musicDir\\$rev$ext'); break; }
          }
        }
        final titlePart = parts[0].trim().toLowerCase();
        if (titlePart.length >= 2 && await Directory(musicDir).exists()) {
          await for (final f in Directory(musicDir).list()) {
            if (f is File) {
              final fn = f.uri.pathSegments.last.toLowerCase();
              if (fn.contains(titlePart) && fn.endsWith('.mp3')) {
                songs.add(f.path); break;
              }
            }
          }
        }
      }
    }

    if (songs.isEmpty) {
      if (gen != _loadGen) return;
      setState(() => _statusText = '播放清單中沒有可播放的歌曲');
      return;
    }

    if (gen != _loadGen) return;
    setState(() {
      _displaySongs = songs;
      _filteredSongs = List.from(songs);
      _displayPlaylistName = name;
      _statusText = '已載入 ${songs.length} 首歌曲';
      _searchCtrl.clear();
      if (!browseOnly) {
        _songs = songs;
        _playQueue = List.from(songs);
        _queueIndex = 0;
        _persistQueue();
      }
    });
    if (!browseOnly && songs.isNotEmpty) _play(songs[0]);
  }

  Future<void> _play(String path) async {
    if (_playInFlight) return;
    _playInFlight = true;
    _recordedSongKey = '';
    try {
      await _player.stop();
      await _player.play(DeviceFileSource(path));
      final stem = File(path).uri.pathSegments.last;
      _currentArtworkUrl = '';
      final qIdx = _playQueue.indexOf(path);
      final sIdx = _songs.indexOf(path);
setState(() {
      _isPlaying = true;
      _currentLyric = '';
      _currentArtwork = _artworkCache[stem];
      _queueIndex = qIdx >= 0 ? qIdx : 0;
      _queueIndex = sIdx >= 0 ? sIdx : _queueIndex;
    });
    _pushSmtcState();
    _loadLyrics(path);
      _loadArtwork(path, stem);
      _loadArtworkUrl(stem);
      _scrollToCurrent();
    } catch (e) {
      setState(() => _statusText = '播放錯誤: $e');
    } finally {
      _playInFlight = false;
    }
  }

  String _currentArtworkUrl = '';
  final Map<String, String> _coverUrlCache = {};
  final Set<String> _coverUrlTried = {};

  /// Discord largeImage 用：內嵌圖優先（上傳 catbox 取 URL），
  /// 再退回 spotify_cache，最後 iTunes API。
  Future<void> _loadArtworkUrl(String songPath) async {
    final stem = File(songPath).uri.pathSegments.last
        .replaceAll(RegExp(r'\.\w+$'), '');
    if (stem.isEmpty) return;
    final cached = _coverUrlCache[stem];
    if (cached != null) {
      if (cached.isNotEmpty) {
        _currentArtworkUrl = cached;
        if (mounted) setState(() {});
        _pushSmtcState();
      }
      return;
    }
    final bytes = _artworkCache[File(songPath).uri.pathSegments.last];
    if (bytes != null && bytes.isNotEmpty) {
      final url = await _uploadCover(bytes);
      if (url != null) {
        _coverUrlCache[stem] = url;
        _currentArtworkUrl = url;
        if (mounted) setState(() {});
        _pushSmtcState();
        return;
      }
    }
    final cacheDir =
        '${ConfigService.instance.config.basePath}${Platform.pathSeparator}spotify_cache';
    final dir = Directory(cacheDir);
    if (await dir.exists()) {
      final q = _tokenize(stem);
      String? best;
      double bestScore = 0.0;
      await for (final f in dir.list()) {
        if (!f.path.toLowerCase().endsWith('.json')) continue;
        final fstem = f.uri.pathSegments.last
            .replaceAll(RegExp(r'\.json$'), '');
        final s = _jaccard(q, _tokenize(fstem));
        if (s > bestScore) {
          bestScore = s;
          best = f.path;
        }
      }
      if (bestScore >= 0.8 && best != null) {
        try {
          final data = jsonDecode(await File(best).readAsString())
              as Map<String, dynamic>;
          final url = data['cover_url'] as String?;
          if (url != null && url.isNotEmpty) {
            _coverUrlCache[stem] = url;
            _currentArtworkUrl = url;
            if (mounted) setState(() {});
            _pushSmtcState();
            return;
          }
        } catch (_) {}
      }
    }
    final fallback = await _resolveCoverUrl(stem);
    if (fallback != null) {
      _coverUrlCache[stem] = fallback;
      _currentArtworkUrl = fallback;
      if (mounted) setState(() {});
      _pushSmtcState();
    } else {
      _coverUrlCache[stem] = '';
      if (_currentArtworkUrl.isNotEmpty) {
        _currentArtworkUrl = '';
        if (mounted) setState(() {});
        _pushSmtcState();
      }
    }
  }

  /// 上傳圖片到 uguu.se（匿名、URL 帶副檔名、回傳正確 image/* MIME；
  /// catbox 的 URL 無副檔名會被 Discord 拒絕）。
  Future<String?> _uploadCover(Uint8List bytes) async {
    if (bytes.length > 5 * 1024 * 1024) return null;
    try {
      final isJpeg = bytes.length > 3 &&
          bytes[0] == 0xFF && bytes[1] == 0xD8 && bytes[2] == 0xFF;
      final isPng = bytes.length > 4 &&
          bytes[0] == 0x89 && bytes[1] == 0x50 &&
          bytes[2] == 0x4E && bytes[3] == 0x47;
      final ext = isJpeg ? 'jpg' : (isPng ? 'png' : 'jpg');
      final req = http.MultipartRequest(
          'POST', Uri.parse('https://uguu.se/upload'))
        ..files.add(http.MultipartFile.fromBytes(
          'files[]',
          bytes,
          filename: 'cover.$ext',
          contentType: MediaType('image', ext),
        ));
      final res = await req.send().timeout(const Duration(seconds: 30));
      final body = await res.stream.bytesToString();
      if (res.statusCode != 200) return null;
      final json = jsonDecode(body) as Map<String, dynamic>;
      final files = (json['files'] as List<dynamic>?) ?? const [];
      if (files.isEmpty) return null;
      final url = (files.first as Map<String, dynamic>)['url'] as String?;
      if (url == null || !url.startsWith('https://')) return null;
      return url;
    } catch (_) {
      return null;
    }
  }

  /// iTunes Search API 補封面（免 key）。檔案名格式「歌名 - 藝人」。
  Future<String?> _resolveCoverUrl(String stem) async {
    final cached = _coverUrlCache[stem];
    if (cached != null) return cached.isEmpty ? null : cached;
    if (_coverUrlTried.contains(stem)) return null;
    _coverUrlTried.add(stem);
    final parts = stem.split(' - ');
    final title = parts.first.trim();
    final artist = parts.length > 1 ? parts.sublist(1).join(' - ').trim() : '';
    if (title.isEmpty) return null;
    try {
      final term = artist.isNotEmpty ? '$title $artist' : title;
      final res = await http.get(Uri.parse(
          'https://itunes.apple.com/search?term=${Uri.encodeQueryComponent(term)}&entity=song&limit=10'));
      if (res.statusCode != 200) return null;
      final list = (jsonDecode(utf8.decode(res.bodyBytes))['results']
              as List<dynamic>?)
          ?.cast<Map<String, dynamic>>() ??
          const [];
      if (list.isEmpty) return null;
      final q = _tokenize(title);
      String? bestUrl;
      double bestScore = 0.0;
      for (final r in list) {
        final t = (r['trackName'] as String?) ?? '';
        final a = (r['artistName'] as String?) ?? '';
        double s = 0.0;
        if (q.isNotEmpty) {
          final inter =
              q.where((tok) => t.toLowerCase().contains(tok)).length;
          s = inter / q.length;
        }
        if (a.isNotEmpty &&
            (a.toLowerCase() == artist.toLowerCase() ||
                a.contains(artist) ||
                artist.contains(a))) {
          s += 0.3;
        }
        final u = (r['artworkUrl100'] as String?) ?? '';
        if (u.isNotEmpty && s > bestScore) {
          bestScore = s;
          bestUrl = u.replaceAll('100x100bb', '600x600bb');
        }
      }
      if (bestScore < 0.4 || bestUrl == null) {
        _coverUrlCache[stem] = '';
        return null;
      }
      _coverUrlCache[stem] = bestUrl;
      return bestUrl;
    } catch (_) {
      return null;
    }
  }

  List<String> _tokenize(String s) {
    final clean = s.toLowerCase().replaceAll(
        RegExp(r'[^\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af ]'), ' ');
    return clean.split(RegExp(r'\s+')).where((t) => t.isNotEmpty).toSet().toList();
  }

  double _jaccard(List<String> a, List<String> b) {
    final sa = a.toSet(), sb = b.toSet();
    if (sa.isEmpty || sb.isEmpty) return 0;
    final inter = sa.intersection(sb).length;
    return inter / sa.union(sb).length;
  }

  Future<void> _loadArtwork(String path, String stem) async {
    if (_artworkCache.containsKey(stem)) {
      setState(() => _currentArtwork = _artworkCache[stem]);
      return;
    }
    Uint8List? artwork;
    try {
      final meta = await MetadataReader.read(path);
      artwork = meta.artwork;
    } catch (_) {}
    if (artwork == null || artwork.isEmpty) {
      final cleanStem = stem.replaceAll(RegExp(r'\.\w+$'), '');
      final url = await _resolveCoverUrl(cleanStem);
      if (url != null) {
        try {
          final res = await http.get(Uri.parse(url));
          if (res.statusCode == 200 && res.bodyBytes.isNotEmpty) {
            artwork = res.bodyBytes;
          }
        } catch (_) {}
      }
    }
    _artworkCache[stem] = artwork;
    if (mounted) setState(() => _currentArtwork = artwork);
    if (artwork != null &&
        artwork.isNotEmpty &&
        !_coverUrlCache.containsKey(stem.replaceAll(RegExp(r'\.\w+$'), ''))) {
      _loadArtworkUrl(path);
    }
  }

  Future<void> _loadLyrics(String songPath) async {
    final stem = File(songPath).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
    final lyricsPath = '${ConfigService.instance.config.lyricsPath}\\$stem.lrc';
    final lrcFile = File(lyricsPath);

    if (_lyricsCache.containsKey(stem)) {
      setState(() => _lyrics = _lyricsCache[stem]!);
      return;
    }

    if (await lrcFile.exists()) {
      final content = await lrcFile.readAsString();
      final parsed = LrcParser.parse(content);
      _lyricsCache[stem] = parsed;
      setState(() => _lyrics = parsed);
    } else {
      setState(() => _lyrics = []);
    }
  }

  void _updateLyrics(Duration position) {
    final offsetMs = (_lyricsOffset * 1000).round();
    final lyric = LrcParser.getCurrentLyric(_lyrics, position.inMilliseconds, offsetMs: offsetMs);
    if (lyric != _currentLyric) {
      setState(() => _currentLyric = lyric);
    }
  }

  void _togglePlay() {
    if (_songs.isEmpty) return;
    if (_isPlaying) {
      _player.pause();
      setState(() => _isPlaying = false);
    } else {
      _player.resume();
      setState(() => _isPlaying = true);
    }
    _pushSmtcState();
  }

  void _next() {
    if (_playQueue.isEmpty || _queueIndex < 0) return;
    if (_queueIndex >= _playQueue.length) _queueIndex = 0;
    int next;
    if (_shuffle) {
      if (_playQueue.length <= 1) return;
      next = (_queueIndex + 1 + (DateTime.now().millisecondsSinceEpoch % (_playQueue.length - 1))) % _playQueue.length;
    } else {
      next = (_queueIndex + 1) % _playQueue.length;
    }
    final path = _playQueue[next];
    final sIdx = _songs.indexOf(path);
    setState(() { _queueIndex = next; _queueIndex = sIdx >= 0 ? sIdx : _queueIndex; });
    final cf = ConfigService.instance.config;
    if (cf.crossfadeEnabled && cf.crossfadeSeconds >= 1.0 && _isPlaying) {
      _crossfadePlay(path);
    } else {
      _play(path);
    }
  }

  /// Fade-out current → switch → fade-in next (audioplayers single-instance
  /// limitation; a soft crossfade instead of true overlap).
  Future<void> _crossfadePlay(String path) async {
    if (_playInFlight) return;
    _playInFlight = true;
    try {
      final total = Duration(milliseconds:
          (ConfigService.instance.config.crossfadeSeconds * 1000).round());
      final half = total ~/ 2;
      await _fadePlayer(_player, _volume, 0.0, half);
      await _player.stop();
      await _player.setVolume(0.0);
      await _player.play(DeviceFileSource(path));
      final stem = File(path).uri.pathSegments.last;
      _currentArtworkUrl = '';
      setState(() {
        _isPlaying = true;
        _currentLyric = '';
        _currentArtwork = _artworkCache[stem];
      });
      _pushSmtcState();
      _loadLyrics(path);
      _loadArtwork(path, stem);
      _loadArtworkUrl(stem);
      _scrollToCurrent();
      await _fadePlayer(_player, 0.0, _volume, half);
    } catch (e) {
      setState(() => _statusText = '播放錯誤: $e');
    } finally {
      _playInFlight = false;
    }
  }

  void _prev() {
    if (_playQueue.isEmpty || _queueIndex < 0) return;
    final prev = (_queueIndex - 1 + _playQueue.length) % _playQueue.length;
    final path = _playQueue[prev];
    final sIdx = _songs.indexOf(path);
    setState(() { _queueIndex = prev; _queueIndex = sIdx >= 0 ? sIdx : _queueIndex; });
    _play(path);
  }

  void _seek(double value) {
    _seekTo(Duration(seconds: value.toInt()));
  }

  void _seekTo(Duration target) {
    _player.seek(target);
    _position = target;
    _pushSmtcState();
  }

  /// Records a play once the user has listened to at least half the track
  /// (or 4 minutes, whichever is less) — the scrobble rule from Spotube.
  void _checkPlaybackRecord(Duration position) {
    final song = _queueIndex >= 0 && _queueIndex < _playQueue.length
        ? _playQueue[_queueIndex]
        : null;
    if (song == null) return;
    final stem = File(song).uri.pathSegments.last
        .replaceAll(RegExp(r'\.\w+$'), '');
    if (_recordedSongKey == stem) return;
    if (_duration.inMilliseconds <= 0) return;
    final thresholdMs = (_duration.inMilliseconds ~/ 2)
        .clamp(0, const Duration(minutes: 4).inMilliseconds);
    if (position.inMilliseconds < thresholdMs) return;
    _recordedSongKey = stem;
    String title = stem;
    String artist = '';
    if (stem.contains(' - ')) {
      final parts = stem.split(' - ');
      if (parts.length >= 2) {
        title = parts.first.trim();
        artist = parts.sublist(1).join(' - ').trim();
      }
    }
    _recordedSongTitle = title;
    _recordedSongArtist = artist;
    PlaybackHistory.instance.record(title, artist, _duration);
  }

  // --- Queue management ------------------------------------------------
  void _persistQueue() {
    try {
      final f = File('${ConfigService.instance.config.cachePath}\\queue.json');
      f.createSync(recursive: true);
      f.writeAsStringSync(jsonEncode({
        'index': _queueIndex,
        'playlist': _displayPlaylistName,
        'queue': _playQueue,
      }));
    } catch (_) {}
  }

  void _loadQueue() {
    try {
      final f = File('${ConfigService.instance.config.cachePath}\\queue.json');
      if (!f.existsSync()) return;
      final data = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
      final q = (data['queue'] as List? ?? [])
          .whereType<String>()
          .where((p) => File(p).existsSync())
          .toList();
      if (q.isEmpty) return;
      _playQueue = q;
      _queueIndex = ((data['index'] as num?)?.toInt() ?? 0).clamp(0, q.length - 1);
      _songs = List.from(q);
      _filteredSongs = List.from(q);
      _displayPlaylistName = (data['playlist'] as String?) ?? '';
    } catch (_) {}
  }

  void _openQueuePanel() {
    if (_playQueue.isEmpty) return;
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppColors.card,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
      isScrollControlled: true,
      builder: (_) => _QueuePanel(
        queue: _playQueue,
        currentIndex: _queueIndex,
        onReorder: (oldIndex, newIndex) {
          setState(() {
            final item = _playQueue.removeAt(oldIndex);
            _playQueue.insert(newIndex, item);
            if (oldIndex == _queueIndex) {
              _queueIndex = newIndex;
            } else if (oldIndex < _queueIndex && newIndex >= _queueIndex) {
              _queueIndex--;
            } else if (oldIndex > _queueIndex && newIndex <= _queueIndex) {
              _queueIndex++;
            }
          });
          _persistQueue();
        },
        onRemove: (index) {
          setState(() {
            if (_queueIndex == index) {
              if (_playQueue.length > 1) {
                _queueIndex = index.clamp(0, _playQueue.length - 2);
                _play(_playQueue[_queueIndex]);
              }
            } else if (index < _queueIndex) {
              _queueIndex--;
            }
            _playQueue.removeAt(index);
          });
          _persistQueue();
        },
        onJump: (index) {
          setState(() => _queueIndex = index);
          _play(_playQueue[index]);
        },
      ),
    );
  }

  void _playNext(String path) {
    if (_playQueue.isEmpty || _queueIndex < 0) return;
    final insertAt = _queueIndex + 1;
    setState(() {
      _playQueue.insert(insertAt, path);
    });
    _persistQueue();
  }

  // --- Sleep timer --------------------------------------------------------
  void _setSleepTimer(Duration? duration) {
    _sleepTimer?.cancel();
    _sleepTimer = null;
    setState(() => _sleepEndsAt = null);
    if (duration == null) return;
    _sleepTimer = Timer(duration, () {
      if (!mounted) return;
      if (_isPlaying) {
        _player.pause();
        setState(() => _isPlaying = false);
        _pushSmtcState();
      }
      setState(() => _sleepEndsAt = null);
    });
    setState(() => _sleepEndsAt = DateTime.now().add(duration));
  }

  String _sleepRemaining() {
    final end = _sleepEndsAt;
    if (end == null) return '';
    final left = end.difference(DateTime.now());
    if (left.isNegative) return '';
    final m = left.inMinutes.remainder(60);
    final h = left.inHours;
    return h > 0 ? '$h時$m分' : '$m分';
  }

  void _showSleepMenu() {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppColors.card,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(16))),
      builder: (ctx) => SafeArea(
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          const Padding(
            padding: EdgeInsets.all(14),
            child: Text('睡眠定時器', style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
          ),
          ...const [15, 30, 60, 120].map((m) => ListTile(
                dense: true,
                leading: const Icon(Icons.timer_outlined, color: AppColors.textMuted, size: 18),
                title: Text('$m 分鐘', style: const TextStyle(fontSize: 13)),
                onTap: () { Navigator.pop(ctx); _setSleepTimer(Duration(minutes: m)); },
              )),
          ListTile(
            dense: true,
            leading: const Icon(Icons.stop_circle_outlined, color: AppColors.error, size: 18),
            title: const Text('取消定時器', style: TextStyle(fontSize: 13)),
            onTap: () { Navigator.pop(ctx); _setSleepTimer(null); },
          ),
        ]),
      ),
    );
  }

  // --- Crossfade ----------------------------------------------------------
  Future<void> _fadePlayer(AudioPlayer p, double from, double to,
      Duration duration) async {
    final steps = 20;
    final dt = duration.inMilliseconds ~/ steps;
    for (var i = 0; i <= steps; i++) {
      final v = from + (to - from) * i / steps;
      await p.setVolume(v);
      await Future.delayed(Duration(milliseconds: dt));
    }
  }

  String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60);
    final s = d.inSeconds.remainder(60);
    return '${m}:${s.toString().padLeft(2, '0')}';
  }

  String _songName(String path) => File(path).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');

  bool _isFav(String path) =>
      _favorites.contains(FavoritesService.normalize(File(path).absolute.path));

  Future<void> _toggleFavorite(String path) async {
    final nowFav = await FavoritesService.toggle(path);
    final favs = await FavoritesService.load();
    if (mounted) setState(() {
      _favorites = favs;
      _statusText = nowFav
          ? '${t('player.fave_added')}: ${_songName(path)}'
          : '${t('player.fave_removed')}: ${_songName(path)}';
    });
  }

  @override
  Widget build(BuildContext context) {
    final currentSong = _queueIndex >= 0 && _queueIndex < _playQueue.length ? _playQueue[_queueIndex] : null;
    final currentName = currentSong != null ? _songName(currentSong) : '';

    return CallbackShortcuts(
      bindings: {
        // Space: play/pause
        const SingleActivator(LogicalKeyboardKey.space): () {
          if (_songs.isNotEmpty) _togglePlay();
        },
        // Arrow left/right: seek ±5s
        const SingleActivator(LogicalKeyboardKey.arrowRight): () {
          if (_queueIndex < 0) return;
          _seekTo(_position + const Duration(seconds: 5));
        },
        const SingleActivator(LogicalKeyboardKey.arrowLeft): () {
          if (_queueIndex < 0) return;
          _seekTo(_position - const Duration(seconds: 5));
        },
        // N: next track, P: previous track
        const SingleActivator(LogicalKeyboardKey.keyN): () {
          if (_songs.isNotEmpty) _next();
        },
        const SingleActivator(LogicalKeyboardKey.keyP): () {
          if (_songs.isNotEmpty) _prev();
        },
      },
      child: Focus(
        autofocus: true,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
          child: Row(children: [
            Expanded(flex: 3, child: _buildPlaylistPanel()),
            const SizedBox(width: 16),
            Expanded(flex: 5, child: _buildPlayerPanel(currentName, currentSong)),
          ]),
        ),
      ),
    );
  }

  Widget _buildPlaylistPanel() {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.card, borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Column(children: [
            Row(children: [
              if (_displaySongs.isNotEmpty && _displayPlaylistName.isNotEmpty)
                PopupMenuButton<String>(
                  onSelected: (name) { if (name != _displayPlaylistName) _loadPlaylist(name, browseOnly: true); },
                  offset: const Offset(0, 24),
                  constraints: const BoxConstraints(maxWidth: 260),
                  child: Row(mainAxisSize: MainAxisSize.min, children: [
                    const Icon(Icons.playlist_play_rounded, size: 16, color: AppColors.accent),
                    const SizedBox(width: 4),
                    ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 180),
                      child: Text(_displayPlaylistName,
                          style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600),
                          overflow: TextOverflow.ellipsis, maxLines: 1),
                    ),
                    const Icon(Icons.arrow_drop_down, size: 18),
                  ]),
                  itemBuilder: (ctx) => _playlistNames
                      .map((n) => PopupMenuItem<String>(
                            value: n,
                            child: Text(n, style: TextStyle(
                              fontSize: 13,
                              fontWeight: n == _displayPlaylistName ? FontWeight.bold : FontWeight.normal,
                              color: n == _displayPlaylistName ? AppColors.accent : null,
                            )),
                          ))
                      .toList(),
                )
              else
                const Text('播放清單', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
              const Spacer(),
              Text(_statusText, style: const TextStyle(color: AppColors.textMuted, fontSize: 10)),
            ]),
            if (_displaySongs.isNotEmpty) ...[
              const SizedBox(height: 8),
              SizedBox(
                height: 32,
                child: TextField(
                  controller: _searchCtrl,
                  decoration: InputDecoration(
                    hintText: '搜尋歌曲…',
                    prefixIcon: const Icon(Icons.search, size: 16),
                    suffixIcon: _searchCtrl.text.isNotEmpty
                        ? IconButton(
                            icon: const Icon(Icons.clear, size: 14),
                            onPressed: () { _searchCtrl.clear(); },
                          )
                        : null,
                    border: const OutlineInputBorder(),
                    isDense: true,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  ),
                  style: const TextStyle(fontSize: 12),
                ),
              ),
            ],
          ]),
        ),
        const Divider(height: 1),
        if (_displaySongs.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            child: Text(
              _searchCtrl.text.isEmpty
                  ? '${_displaySongs.length} 首歌曲'
                  : '搜尋結果: ${_filteredSongs.length}/${_displaySongs.length}',
              style: const TextStyle(color: AppColors.textMuted, fontSize: 10),
            ),
          ),
        Expanded(
          child: _displaySongs.isEmpty
              ? _buildPlaylistSelector()
              : _buildSongList(),
        ),
      ]),
    );
  }

  Widget _buildPlaylistSelector() {
    final plDir = Directory(ConfigService.instance.config.playlistsPath);
    return FutureBuilder<List<String>>(
      future: _listPlaylists(plDir),
      builder: (ctx, snap) {
        if (!snap.hasData) return const Center(child: CircularProgressIndicator(strokeWidth: 2));
        final items = snap.data!;
        if (items.isEmpty) return Center(child: Text(t('library.empty_title'), style: const TextStyle(color: AppColors.textMuted)));
        return ListView.builder(
          controller: _playlistCtrl,
          padding: const EdgeInsets.symmetric(vertical: 4),
          itemCount: items.length,
          itemBuilder: (ctx, i) => ListTile(
            dense: true,
            leading: const Icon(Icons.playlist_play_rounded, color: AppColors.accent, size: 18),
            title: Text(items[i], style: const TextStyle(fontSize: 13)),
            onTap: () => _loadPlaylist(items[i]),
          ),
        );
      },
    );
  }

  Widget _buildSongList() {
    return ListView.builder(
      controller: _playlistCtrl,
      padding: const EdgeInsets.symmetric(vertical: 4),
      itemCount: _filteredSongs.length,
      itemBuilder: (ctx, i) {
        final song = _filteredSongs[i];
        final isCurrent = _playQueue.isNotEmpty && _queueIndex >= 0 && _queueIndex < _playQueue.length && _playQueue[_queueIndex] == song;
        return ListTile(
          dense: true,
          leading: isCurrent
              ? Icon(_isPlaying ? Icons.volume_up_rounded : Icons.pause_rounded, color: AppColors.accent, size: 16)
              : Text('${i + 1}', style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
          title: Text(
            _songName(song),
            style: TextStyle(
              fontSize: 12,
              fontWeight: isCurrent ? FontWeight.w600 : FontWeight.normal,
              color: isCurrent ? AppColors.accent : AppColors.text,
            ),
            maxLines: 1, overflow: TextOverflow.ellipsis,
          ),
          trailing: IconButton(
            onPressed: () => _toggleFavorite(song),
            tooltip: _isFav(song) ? t('player.fave_remove') : t('player.fave_add'),
            icon: Icon(
              _isFav(song) ? Icons.star_rounded : Icons.star_border_rounded,
              color: _isFav(song) ? const Color(0xFFFFD700) : AppColors.textMuted,
              size: 18,
            ),
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(),
            visualDensity: VisualDensity.compact,
          ),
          onTap: () {
            _songs = List.from(_displaySongs);
            _playQueue = List.from(_filteredSongs);
            final idx = _playQueue.indexOf(song);
            setState(() { _queueIndex = idx >= 0 ? idx : 0; });
            _play(song);
          },
        );
      },
    );
  }

  Future<List<String>> _listPlaylists(Directory dir) async {
    if (!await dir.exists()) return [];
    final names = <String>[];
    await for (final e in dir.list()) {
      if (e is File && e.path.toLowerCase().endsWith('.m3u8')) {
        names.add(e.uri.pathSegments.last.replaceAll('.m3u8', ''));
      }
    }
    names.sort();
    return names;
  }

  Widget _buildPlayerPanel(String currentName, String? currentSong) {
    return Container(
      decoration: BoxDecoration(
        color: AppColors.card, borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 8),
          child: Row(children: [
            Container(
              width: 80, height: 80,
              decoration: BoxDecoration(
                color: AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(12),
              ),
              clipBehavior: Clip.antiAlias,
              child: _currentArtwork != null
                  ? Image.memory(_currentArtwork!, fit: BoxFit.cover)
                  : const Icon(Icons.music_note_rounded, color: AppColors.textMuted, size: 36),
            ),
            const SizedBox(width: 16),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(
                  child: Text(currentName.isNotEmpty ? currentName : t('player.select_playlist'),
                      style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                      maxLines: 1, overflow: TextOverflow.ellipsis),
                ),
                if (currentSong != null)
                  IconButton(
                    onPressed: () => _toggleFavorite(currentSong),
                    tooltip: _isFav(currentSong) ? t('player.fave_remove') : t('player.fave_add'),
                    icon: Icon(
                      _isFav(currentSong) ? Icons.star_rounded : Icons.star_border_rounded,
                      color: _isFav(currentSong) ? const Color(0xFFFFD700) : AppColors.textMuted,
                      size: 26,
                    ),
                    padding: EdgeInsets.zero,
                    constraints: const BoxConstraints(),
                  ),
              ]),
              const SizedBox(height: 4),
              Text(_queueIndex >= 0 ? '${_queueIndex + 1}/${_playQueue.length}' : '',
                  style: const TextStyle(color: AppColors.textSecondary, fontSize: 12)),
            ])),
          ]),
        ),
        const SizedBox(height: 8),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Column(children: [
            SliderTheme(
              data: SliderThemeData(
                trackHeight: 4,
                thumbShape: const RoundSliderThumbShape(enabledThumbRadius: 6),
                activeTrackColor: AppColors.accent,
                inactiveTrackColor: AppColors.surfaceLight,
                thumbColor: AppColors.accent,
                overlayColor: AppColors.accentDim,
              ),
              child: Slider(
                value: _position.inSeconds.toDouble().clamp(0, _duration.inSeconds > 0 ? _duration.inSeconds.toDouble() : 1),
                max: _duration.inSeconds > 0 ? _duration.inSeconds.toDouble() : 1,
                onChanged: _seek,
              ),
            ),
            Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
              Text(_fmt(_position), style: const TextStyle(color: AppColors.textMuted, fontSize: 11, fontFamily: 'Consolas')),
              Text(_fmt(_duration), style: const TextStyle(color: AppColors.textMuted, fontSize: 11, fontFamily: 'Consolas')),
            ]),
          ]),
        ),
        const SizedBox(height: 8),
        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          IconButton(
            onPressed: _prev,
            icon: const Icon(Icons.skip_previous_rounded, color: AppColors.text, size: 28),
          ),
          const SizedBox(width: 8),
          Container(
            decoration: const BoxDecoration(
              color: AppColors.accent, shape: BoxShape.circle,
            ),
            child: IconButton(
              onPressed: _togglePlay,
              icon: Icon(_isPlaying ? Icons.pause_rounded : Icons.play_arrow_rounded, color: Colors.black, size: 28),
              style: IconButton.styleFrom(backgroundColor: Colors.transparent),
            ),
          ),
          const SizedBox(width: 8),
          IconButton(
            onPressed: _next,
            icon: const Icon(Icons.skip_next_rounded, color: AppColors.text, size: 28),
          ),
        ]),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Row(children: [
            IconButton(
              onPressed: () => setState(() => _shuffle = !_shuffle),
              icon: Icon(Icons.shuffle_rounded, color: _shuffle ? AppColors.accent : AppColors.textMuted, size: 20),
            ),
            IconButton(
              onPressed: () => setState(() => _loop = !_loop),
              icon: Icon(_loop ? Icons.repeat_rounded : Icons.repeat_one_rounded,
                  color: _loop ? AppColors.accent : AppColors.textMuted, size: 20),
              tooltip: _loop ? '循環播放' : '單曲循環',
            ),
            IconButton(
              onPressed: _openQueuePanel,
              icon: const Icon(Icons.queue_music_rounded, color: AppColors.text, size: 20),
              tooltip: '播放佇列 (${_playQueue.length})',
            ),
            IconButton(
              onPressed: _showSleepMenu,
              icon: Icon(_sleepEndsAt != null ? Icons.bedtime_rounded : Icons.bedtime_outlined,
                  color: _sleepEndsAt != null ? AppColors.error : AppColors.textMuted, size: 20),
              tooltip: _sleepEndsAt != null ? '睡眠定時器 (${_sleepRemaining()})' : '睡眠定時器',
            ),
            IconButton(
              onPressed: () {
                final c = ConfigService.instance.config;
                c.crossfadeEnabled = !c.crossfadeEnabled;
                ConfigService.instance.save();
                setState(() {});
              },
              icon: Icon(Icons.linear_scale_rounded,
                  color: ConfigService.instance.config.crossfadeEnabled ? AppColors.accent : AppColors.textMuted, size: 20),
              tooltip: ConfigService.instance.config.crossfadeEnabled
                  ? 'Crossfade 開啟 (${ConfigService.instance.config.crossfadeSeconds}s)'
                  : 'Crossfade 關閉',
            ),
            const SizedBox(width: 8),
            Icon(Icons.volume_up_rounded, color: AppColors.textMuted, size: 16),
            Expanded(
              child: SliderTheme(
                data: const SliderThemeData(trackHeight: 3, thumbShape: RoundSliderThumbShape(enabledThumbRadius: 5)),
                child: Slider(
                  value: _volume,
                  max: 1.0,
                  activeColor: AppColors.accent,
                  onChanged: (v) {
                    setState(() => _volume = v);
                    _player.setVolume(v);
                    final c = ConfigService.instance.config;
                    c.volume = v;
                    ConfigService.instance.save();
                  },
                ),
              ),
            ),
          ]),
        ),
        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          Text('歌詞偏移:', style: TextStyle(color: AppColors.textMuted, fontSize: 11)),
          IconButton(
            icon: const Icon(Icons.remove_circle_outline, size: 16),
            onPressed: () => setState(() => _lyricsOffset = (_lyricsOffset - 0.5).clamp(-10.0, 10.0)),
            color: AppColors.textMuted,
            constraints: const BoxConstraints(),
            padding: const EdgeInsets.all(4),
          ),
          Text('${_lyricsOffset.toStringAsFixed(1)}s', style: TextStyle(color: AppColors.accent, fontSize: 12, fontWeight: FontWeight.bold)),
          IconButton(
            icon: const Icon(Icons.add_circle_outline, size: 16),
            onPressed: () => setState(() => _lyricsOffset = (_lyricsOffset + 0.5).clamp(-10.0, 10.0)),
            color: AppColors.textMuted,
            constraints: const BoxConstraints(),
            padding: const EdgeInsets.all(4),
          ),
        ]),
        const SizedBox(height: 4),
        Expanded(
          child: Container(
            margin: const EdgeInsets.fromLTRB(16, 4, 16, 16),
            decoration: BoxDecoration(
              color: const Color(0xFF0A0A0A),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Center(
              child: SingleChildScrollView(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Text(
                    _currentLyric.isNotEmpty ? _currentLyric : (_lyrics.isNotEmpty ? '' : t('player.no_lyrics')),
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: _currentLyric.isNotEmpty ? 22 : 14,
                      fontWeight: _currentLyric.isNotEmpty ? FontWeight.bold : FontWeight.normal,
                      color: AppColors.accent,
                      height: 1.5,
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ]),
    );
  }
}

class _QueuePanel extends StatefulWidget {
  final List<String> queue;
  final int currentIndex;
  final void Function(int oldIndex, int newIndex) onReorder;
  final void Function(int index) onRemove;
  final void Function(int index) onJump;

  const _QueuePanel({
    required this.queue,
    required this.currentIndex,
    required this.onReorder,
    required this.onRemove,
    required this.onJump,
  });

  @override
  State<_QueuePanel> createState() => _QueuePanelState();
}

class _QueuePanelState extends State<_QueuePanel> {
  @override
  Widget build(BuildContext context) {
    final height = (widget.queue.length * 52.0 + 80).clamp(200.0, 560.0);
    return SizedBox(
      height: height,
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 14, 12, 4),
          child: Row(children: [
            const Icon(Icons.queue_music_rounded, color: AppColors.textMuted, size: 18),
            const SizedBox(width: 8),
            Text('播放佇列 (${widget.queue.length})',
                style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
            const Spacer(),
            IconButton(
              icon: const Icon(Icons.close_rounded, color: AppColors.textMuted, size: 18),
              onPressed: () => Navigator.of(context).pop(),
            ),
          ]),
        ),
        Expanded(
          child: ReorderableListView.builder(
            padding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
            itemCount: widget.queue.length,
            onReorder: widget.onReorder,
            itemBuilder: (ctx, i) {
              final path = widget.queue[i];
              final stem = File(path).uri.pathSegments.last
                  .replaceAll(RegExp(r'\.\w+$'), '');
              final isCurrent = i == widget.currentIndex;
              return ListTile(
                key: ValueKey('$path-$i'),
                dense: true,
                leading: ReorderableDragStartListener(
                  index: i,
                  child: const Icon(Icons.drag_handle_rounded,
                      color: AppColors.textMuted, size: 18),
                ),
                title: Text(stem,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 12,
                      color: isCurrent ? AppColors.accent : AppColors.text,
                      fontWeight: isCurrent ? FontWeight.w600 : FontWeight.normal,
                    )),
                trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                  if (!isCurrent)
                    IconButton(
                      icon: const Icon(Icons.play_arrow_rounded,
                          color: AppColors.textMuted, size: 18),
                      onPressed: () => widget.onJump(i),
                      tooltip: '播放此曲',
                    ),
                  IconButton(
                    icon: const Icon(Icons.close_rounded,
                        color: AppColors.textMuted, size: 18),
                    onPressed: () => widget.onRemove(i),
                    tooltip: '從佇列移除',
                  ),
                ]),
                onTap: isCurrent ? null : () => widget.onJump(i),
              );
            },
          ),
        ),
      ]),
    );
  }
}
