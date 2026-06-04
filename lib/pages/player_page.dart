import 'dart:async';
import 'dart:io';
import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import '../services/config_service.dart';
import '../services/i18n.dart';
import '../services/lrc_parser.dart';
import '../widgets/dark_theme.dart';

class PlayerPage extends StatefulWidget {
  const PlayerPage({super.key});
  @override
  State<PlayerPage> createState() => _PlayerPageState();
}

class _PlayerPageState extends State<PlayerPage> {
  final _player = AudioPlayer();
  final _playlistCtrl = ScrollController();

  List<String> _songs = [];
  int _currentIndex = -1;
  bool _isPlaying = false;
  bool _shuffle = false;
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

  @override
  void initState() {
    super.initState();
    _statusText = t('spotube.status_ready');
    I18N.instance.addListener(() { if (mounted) setState(() {}); });
    _player.onPlayerComplete.listen((_) => _next());
    _positionSub = _player.onPositionChanged.listen((p) {
      if (!mounted) return;
      setState(() => _position = p);
      _updateLyrics(p);
    });
    _player.onDurationChanged.listen((d) {
      if (mounted) setState(() => _duration = d);
    });
  }

  @override
  void dispose() {
    _positionSub?.cancel();
    _positionTimer?.cancel();
    _player.dispose();
    _playlistCtrl.dispose();
    super.dispose();
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
    for (final line in lines) {
      final trimmed = line.trim();
      if (trimmed.isEmpty || trimmed.startsWith('#')) continue;
      String resolved = trimmed;
      if (!File(trimmed).existsSync()) {
        resolved = '${ConfigService.instance.config.libraryPath}\\${File(trimmed).uri.pathSegments.last}';
      }
      if (await File(resolved).exists()) songs.add(resolved);
    }

    if (songs.isEmpty) {
      setState(() => _statusText = '播放清單中沒有可播放的歌曲');
      return;
    }

    setState(() {
      _songs = songs;
      _currentIndex = 0;
      _statusText = '已載入 ${songs.length} 首歌曲';
    });
    _play(songs[0]);
  }

  Future<void> _play(String path) async {
    try {
      await _player.stop();
      await _player.play(DeviceFileSource(path));
      setState(() {
        _isPlaying = true;
        _currentLyric = '';
      });
      _loadLyrics(path);
    } catch (e) {
      setState(() => _statusText = '播放錯誤: $e');
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
  }

  void _next() {
    if (_songs.isEmpty) return;
    int next;
    if (_shuffle) {
      next = (_currentIndex + 1 + (DateTime.now().millisecondsSinceEpoch % (_songs.length - 1))) % _songs.length;
    } else {
      next = (_currentIndex + 1) % _songs.length;
    }
    setState(() => _currentIndex = next);
    _play(_songs[next]);
  }

  void _prev() {
    if (_songs.isEmpty) return;
    final prev = (_currentIndex - 1 + _songs.length) % _songs.length;
    setState(() => _currentIndex = prev);
    _play(_songs[prev]);
  }

  void _seek(double value) {
    _player.seek(Duration(seconds: value.toInt()));
  }

  String _fmt(Duration d) {
    final m = d.inMinutes.remainder(60);
    final s = d.inSeconds.remainder(60);
    return '${m}:${s.toString().padLeft(2, '0')}';
  }

  @override
  Widget build(BuildContext context) {
    final currentSong = _currentIndex >= 0 && _currentIndex < _songs.length ? _songs[_currentIndex] : null;
    final currentName = currentSong != null
        ? File(currentSong).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '')
        : '';

    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Row(children: [
        // Playlist selector (left)
        Expanded(flex: 3, child: _buildPlaylistPanel()),
        const SizedBox(width: 16),
        // Player (right)
        Expanded(flex: 5, child: _buildPlayerPanel(currentName, currentSong)),
      ]),
    );
  }

  Widget _buildPlaylistPanel() {
    final plDir = Directory(ConfigService.instance.config.playlistsPath);
    return Container(
      decoration: BoxDecoration(
        color: AppColors.card, borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: Row(children: [
            const Text('播放清單', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
            const Spacer(),
            Text(_statusText, style: const TextStyle(color: AppColors.textMuted, fontSize: 10)),
          ]),
        ),
        const Divider(height: 1),
        Expanded(
          child: FutureBuilder<List<String>>(
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
          ),
        ),
      ]),
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
        // Song info
        Padding(
          padding: const EdgeInsets.fromLTRB(24, 24, 24, 8),
          child: Row(children: [
            Container(
              width: 80, height: 80,
              decoration: BoxDecoration(
                color: AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(Icons.music_note_rounded, color: AppColors.textMuted, size: 36),
            ),
            const SizedBox(width: 16),
            Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(currentName.isNotEmpty ? currentName : t('player.select_playlist'),
                  style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  maxLines: 1, overflow: TextOverflow.ellipsis),
              const SizedBox(height: 4),
              Text(_currentIndex >= 0 ? '${_currentIndex + 1}/${_songs.length}' : '',
                  style: const TextStyle(color: AppColors.textSecondary, fontSize: 12)),
            ])),
          ]),
        ),
        const SizedBox(height: 8),
        // Progress
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
        // Controls
        Row(mainAxisAlignment: MainAxisAlignment.center, children: [
          IconButton(
            onPressed: _prev,
            icon: const Icon(Icons.skip_previous_rounded, color: AppColors.text, size: 28),
          ),
          const SizedBox(width: 8),
          Container(
            decoration: BoxDecoration(
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
        // Shuffle + Volume
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: Row(children: [
            IconButton(
              onPressed: () => setState(() => _shuffle = !_shuffle),
              icon: Icon(Icons.shuffle_rounded, color: _shuffle ? AppColors.accent : AppColors.textMuted, size: 20),
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
        // Lyrics offset
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
        // Lyrics display
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
