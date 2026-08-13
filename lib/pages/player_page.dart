import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:http_parser/http_parser.dart';
import '../services/config_service.dart';
import '../services/favorites_service.dart';
import '../services/i18n.dart';
import '../services/smtc_service.dart';
import '../services/discord_rpc_service.dart';
import '../services/lrc_parser.dart';
import '../services/metadata_reader.dart';
import '../services/spotube_controller.dart';
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
  bool _isPlaying = false;
  bool _shuffle = false;
  bool _loop = true;
  double _volume = 0.7;
  Duration _position = Duration.zero;
  Duration _duration = Duration.zero;
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
    _statusText = t('spotube.status_ready');
    I18N.instance.addListener(() { if (mounted) setState(() {}); });
    _player.onPlayerComplete.listen((_) {
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
    );
    _pushSmtcState();
    _initDiscordRpc();
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

  void _pushSmtcState() {
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
    SmtcService.instance.update(
      title: title,
      artist: artist,
      album: _displayPlaylistName,
      artworkUrl: _currentArtworkUrl,
      playing: _isPlaying,
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
    final plPath = '${ConfigService.instance.config.playlistsPath}\\$name.m3u8';
    final file = File(plPath);
    if (!await file.exists()) {
      setState(() => _statusText = '找不到播放清單: $name');
      return;
    }
    final stat = await file.stat();
    if (stat.size == 0) {
      setState(() => _statusText = '播放清單是空的');
      return;
    }

    final lines = await file.readAsLines();
    final songs = <String>[];
    final lib = ConfigService.instance.config.libraryPath;
    for (final line in lines) {
      final raw = line.trim();
      if (raw.isEmpty || raw.startsWith('#')) continue;
      // Echo Nightly playlists store URI-encoded paths — try both forms.
      String decodePath(String s) {
        try { return Uri.decodeComponent(s); } catch (_) { return s; }
      }
      final trimmed = decodePath(raw);
      if (File(trimmed).existsSync()) { songs.add(trimmed); continue; }
      final fname = File(trimmed).uri.pathSegments.last;
      String resolved = '$lib\\$fname';
      if (await File(resolved).exists()) { songs.add(resolved); continue; }
      bool found = false;
      for (final ext in ['.mp3', '.m4a', '.flac']) {
        if (await File('$resolved$ext').exists()) { songs.add('$resolved$ext'); found = true; break; }
        if (await File('$lib\\mp3\\$fname$ext').exists()) { songs.add('$lib\\mp3\\$fname$ext'); found = true; break; }
      }
      if (found) continue;
      final stem = fname.replaceAll(RegExp(r'\.\w+$'), '').toLowerCase();
      if (stem.contains(' - ')) {
        final parts = stem.split(' - ');
        if (parts.length >= 2) {
          final rev = '${parts[1]} - ${parts[0]}';
          for (final ext in ['.mp3', '.m4a', '.flac']) {
            if (await File('$lib\\$rev$ext').exists()) { songs.add('$lib\\$rev$ext'); break; }
            if (await File('$lib\\mp3\\$rev$ext').exists()) { songs.add('$lib\\mp3\\$rev$ext'); break; }
          }
        }
        final titlePart = parts[0].trim().toLowerCase();
        if (titlePart.length >= 2) {
          final mp3Dir = Directory('$lib\\mp3');
          if (await mp3Dir.exists()) {
            await for (final f in mp3Dir.list()) {
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
    }

    if (songs.isEmpty) {
      setState(() => _statusText = '播放清單中沒有可播放的歌曲');
      return;
    }

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
      }
    });
    if (!browseOnly && songs.isNotEmpty) _play(songs[0]);
  }

  Future<void> _play(String path) async {
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
    if (_playQueue.isEmpty) return;
    int next;
    if (_shuffle) {
      next = (_queueIndex + 1 + (DateTime.now().millisecondsSinceEpoch % (_playQueue.length - 1))) % _playQueue.length;
    } else {
      next = (_queueIndex + 1) % _playQueue.length;
    }
    final path = _playQueue[next];
    final sIdx = _songs.indexOf(path);
    setState(() { _queueIndex = next; _queueIndex = sIdx >= 0 ? sIdx : _queueIndex; });
    _play(path);
  }

  void _prev() {
    if (_playQueue.isEmpty) return;
    final prev = (_queueIndex - 1 + _playQueue.length) % _playQueue.length;
    final path = _playQueue[prev];
    final sIdx = _songs.indexOf(path);
    setState(() { _queueIndex = prev; _queueIndex = sIdx >= 0 ? sIdx : _queueIndex; });
    _play(path);
  }

  void _seek(double value) {
    _player.seek(Duration(seconds: value.toInt()));
    _position = Duration(seconds: value.toInt());
    _pushSmtcState();
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

    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Row(children: [
        Expanded(flex: 3, child: _buildPlaylistPanel()),
        const SizedBox(width: 16),
        Expanded(flex: 5, child: _buildPlayerPanel(currentName, currentSong)),
      ]),
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
            const SizedBox(width: 8),
            Icon(Icons.volume_up_rounded, color: AppColors.textMuted, size: 16),
            Expanded(
              child: SliderTheme(
                data: const SliderThemeData(trackHeight: 3, thumbShape: RoundSliderThumbShape(enabledThumbRadius: 5)),
                child: Slider(
                  value: _volume,
                  max: 1.0,
                  activeColor: AppColors.accent,
                  onChanged: (v) { setState(() => _volume = v); _player.setVolume(v); },
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
