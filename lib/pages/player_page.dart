import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import '../services/config_service.dart';
import '../services/i18n.dart';
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
  Timer? _positionTimer;
  StreamSubscription? _positionSub;

  final Map<String, List<LrcLine>> _lyricsCache = {};
  final Map<String, Uint8List?> _artworkCache = {};
  Uint8List? _currentArtwork;

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
        _filteredSongs = List.from(_songs);
        _playQueue = List.from(_songs);
        _queueIndex = _queueIndex >= 0 && _queueIndex < _songs.length ? _queueIndex : 0;
      } else {
        _filteredSongs = _songs.where((s) {
          final name = File(s).uri.pathSegments.last.toLowerCase();
          return name.contains(q);
        }).toList();
        _playQueue = List.from(_filteredSongs);
        _queueIndex = 0;
        if (_playQueue.isNotEmpty) _play(_playQueue[0]);
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

  Future<void> _loadPlaylist(String name) async {
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
      final trimmed = line.trim();
      if (trimmed.isEmpty || trimmed.startsWith('#')) continue;
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
      _songs = songs;
      _filteredSongs = List.from(songs);
      _playQueue = List.from(songs);
      _queueIndex = 0;
      _queueIndex = 0;
      _statusText = '已載入 ${songs.length} 首歌曲';
      _searchCtrl.clear();
    });
    _play(songs[0]);
  }

  Future<void> _play(String path) async {
    try {
      await _player.stop();
      await _player.play(DeviceFileSource(path));
      final stem = File(path).uri.pathSegments.last;
      final qIdx = _playQueue.indexOf(path);
      final sIdx = _songs.indexOf(path);
      setState(() {
        _isPlaying = true;
        _currentLyric = '';
        _currentArtwork = _artworkCache[stem];
        _queueIndex = qIdx >= 0 ? qIdx : 0;
        _queueIndex = sIdx >= 0 ? sIdx : _queueIndex;
      });
      _loadLyrics(path);
      _loadArtwork(path, stem);
      _scrollToCurrent();
    } catch (e) {
      setState(() => _statusText = '播放錯誤: $e');
    }
  }

  Future<void> _loadArtwork(String path, String stem) async {
    if (_artworkCache.containsKey(stem)) {
      setState(() => _currentArtwork = _artworkCache[stem]);
      return;
    }
    try {
      final meta = await MetadataReader.read(path);
      _artworkCache[stem] = meta.artwork;
      if (mounted) setState(() => _currentArtwork = meta.artwork);
    } catch (_) {}
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
  }

  String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60);
    final s = d.inSeconds.remainder(60);
    return '${m}:${s.toString().padLeft(2, '0')}';
  }

  String _songName(String path) => File(path).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');

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
              const Text('播放清單', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
              const Spacer(),
              Text(_statusText, style: const TextStyle(color: AppColors.textMuted, fontSize: 10)),
            ]),
            if (_songs.isNotEmpty) ...[
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
        if (_songs.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            child: Text(
              _searchCtrl.text.isEmpty
                  ? '${_songs.length} 首歌曲'
                  : '搜尋結果: ${_filteredSongs.length}/${_songs.length}',
              style: const TextStyle(color: AppColors.textMuted, fontSize: 10),
            ),
          ),
        Expanded(
          child: _songs.isEmpty
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
          onTap: () {
            _playQueue = List.from(_filteredSongs);
            final idx = _playQueue.indexOf(song);
            final sIdx = _songs.indexOf(song);
            setState(() { _queueIndex = idx >= 0 ? idx : 0; _queueIndex = sIdx >= 0 ? sIdx : _queueIndex; });
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
              Text(currentName.isNotEmpty ? currentName : t('player.select_playlist'),
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  maxLines: 1, overflow: TextOverflow.ellipsis),
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
