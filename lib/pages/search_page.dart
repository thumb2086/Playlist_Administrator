import 'dart:async';
import 'dart:io';
import 'package:flutter/material.dart';
import '../services/config_service.dart';
import '../services/spotify_session.dart';
import '../services/spotify_gql_client.dart';
import '../services/player_controller.dart';
import '../widgets/dark_theme.dart';
import '../widgets/spotify_login_dialog.dart';

/// Spotify search: native GQL search → check local library → stream or queue.
class SearchPage extends StatefulWidget {
  const SearchPage({super.key});
  @override
  State<SearchPage> createState() => _SearchPageState();
}

class _SearchPageState extends State<SearchPage> {
  final _gql = SpotifyGqlClient();
  final _searchCtrl = TextEditingController();
  Timer? _debounce;
  List<SpotifyTrackItem> _tracks = [];
  bool _searching = false;
  String _error = '';

  @override
  void initState() {
    super.initState();
    SpotifySession.instance.addListener(_onSession);
    _searchCtrl.addListener(_onQueryChanged);
  }

  @override
  void dispose() {
    SpotifySession.instance.removeListener(_onSession);
    _debounce?.cancel();
    _searchCtrl.dispose();
    super.dispose();
  }

  void _onSession() {
    if (mounted) setState(() {});
  }

  void _onQueryChanged() {
    _debounce?.cancel();
    final q = _searchCtrl.text.trim();
    if (q.isEmpty) {
      setState(() => _tracks = []);
      return;
    }
    _debounce = Timer(const Duration(milliseconds: 350), () => _search(q));
  }

  Future<void> _search(String query) async {
    if (!SpotifySession.instance.isLoggedIn) return;
    setState(() { _searching = true; _error = ''; });
    try {
      final data = await _gql.searchTracks(query, limit: 25);
      final tracks = _parseTracks(data);
      if (mounted) setState(() { _tracks = tracks; _searching = false; });
    } catch (e) {
      if (mounted) setState(() { _searching = false; _error = '$e'; });
    }
  }

  List<SpotifyTrackItem> _parseTracks(Map<String, dynamic> data) {
    final out = <SpotifyTrackItem>[];
    try {
      final search =
          (data['data'] as Map?)?['searchV2'] as Map<String, dynamic>?;
      final tracks = search?['tracksV2'] as Map<String, dynamic>?;
      final items = tracks?['items'] as List<dynamic>? ?? [];
      for (final it in items) {
        final track = (it as Map<String, dynamic>)['item'] as Map<String, dynamic>?;
        if (track == null) continue;
        final album = track['albumOfTrack'] as Map<String, dynamic>?;
        final name = (track['name'] ?? '') as String? ?? '';
        if (name.isEmpty) continue;
        final uri = (track['uri'] ?? '') as String? ?? '';
        final artists = (track['artists'] as List<dynamic>? ?? [])
            .map((a) => ((a as Map<String, dynamic>)['profile'] as Map?)?['name'] as String? ?? '')
            .where((s) => s.isNotEmpty)
            .toList();
        final duration = ((track['trackDuration'] as Map<String, dynamic>?)?['totalMilliseconds'] as num?)?.toInt() ?? 0;
        final cover = album != null ? SpotifyTrackItem.coverFromSources(album['coverArt']?['sources']) : null;
        out.add(SpotifyTrackItem(
          uri: uri, name: name, artists: artists,
          album: (album?['name'] as String?) ?? '',
          durationMs: duration, coverUrl: cover,
        ));
      }
    } catch (_) {}
    return out;
  }

  /// Returns the local music file for [t] if it exists in the library.
  String? _findLocal(SpotifyTrackItem t) {
    final cfg = ConfigService.instance.config;
    final dir = Directory(cfg.musicPath);
    if (!dir.existsSync()) return null;
    final targets = [
      t.displayName.toLowerCase(),
      '${t.name} - ${t.artists.join(' ')}'.toLowerCase(),
      t.name.toLowerCase(),
    ];
    final files = dir.listSync();
    for (final f in files) {
      if (f is! File) continue;
      final stem = File(f.path).uri.pathSegments.last
          .replaceAll(RegExp(r'\.\w+$'), '')
          .toLowerCase();
      for (final target in targets) {
        if (stem == target || stem.contains(target) || target.contains(stem)) {
          return f.path;
        }
      }
    }
    return null;
  }

  /// Play: local file if available, else resolve stream URL.
  Future<void> _play(SpotifyTrackItem t) async {
    final local = _findLocal(t);
    if (local != null) {
      PlayerController.instance.play(local, title: t.name, artist: t.artists.join(', '));
      return;
    }
    PlayerController.instance.play(t.displayName, title: t.name, artist: t.artists.join(', '));
  }

  @override
  Widget build(BuildContext context) {
    final loggedIn = SpotifySession.instance.isLoggedIn;
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (!loggedIn)
          Expanded(
            child: Center(
              child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                const Icon(Icons.search_rounded, size: 56, color: AppColors.textMuted),
                const SizedBox(height: 16),
                const Text('搜尋需要 Spotify 登入', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
                const SizedBox(height: 12),
                ElevatedButton.icon(
                  onPressed: () async {
                    await showSpotifyLogin(context);
                    await SpotifySession.instance.load();
                    if (mounted) setState(() {});
                  },
                  icon: const Icon(Icons.login_rounded, size: 18),
                  label: const Text('Spotify 登入'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF1DB954),
                    foregroundColor: Colors.black,
                  ),
                ),
              ]),
            ),
          )
        else ...[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
            decoration: BoxDecoration(
              color: AppColors.surfaceLight,
              borderRadius: BorderRadius.circular(10),
            ),
            child: TextField(
              controller: _searchCtrl,
              autofocus: false,
              decoration: const InputDecoration(
                hintText: '搜尋歌曲、藝人、專輯…',
                border: InputBorder.none,
                icon: Icon(Icons.search_rounded, color: AppColors.textMuted, size: 18),
              ),
              style: const TextStyle(fontSize: 13),
            ),
          ),
          const SizedBox(height: 12),
          if (_searching)
            const Expanded(child: Center(child: CircularProgressIndicator()))
          else if (_error.isNotEmpty)
            Expanded(child: Center(child: Text('搜尋失敗: $_error', style: const TextStyle(color: AppColors.error))))
          else if (_tracks.isEmpty)
            const Expanded(
              child: Center(child: Text('輸入關鍵字開始搜尋', style: TextStyle(color: AppColors.textMuted))),
            )
          else
            Expanded(
              child: ListView.builder(
                itemCount: _tracks.length,
                itemBuilder: (ctx, i) {
                  final t = _tracks[i];
                  final local = _findLocal(t);
                  return ListTile(
                    dense: true,
                    leading: ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: t.coverUrl != null
                          ? Image.network(t.coverUrl!, width: 40, height: 40, fit: BoxFit.cover,
                              errorBuilder: (_, __, ___) => Container(
                                  width: 40, height: 40, color: AppColors.surfaceLight,
                                  child: const Icon(Icons.music_note_rounded, size: 18, color: AppColors.textMuted)))
                          : Container(width: 40, height: 40, color: AppColors.surfaceLight,
                              child: const Icon(Icons.music_note_rounded, size: 18, color: AppColors.textMuted)),
                    ),
                    title: Text(t.name, maxLines: 1, overflow: TextOverflow.ellipsis,
                        style: const TextStyle(fontSize: 12)),
                    subtitle: Text(
                      '${t.artists.join(', ')}${local != null ? '  ● 已在本機' : ''}',
                      maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 10,
                          color: local != null ? AppColors.accent : AppColors.textMuted),
                    ),
                    trailing: Row(mainAxisSize: MainAxisSize.min, children: [
                      if (local != null)
                        IconButton(
                          icon: const Icon(Icons.play_arrow_rounded, color: AppColors.accent, size: 20),
                          onPressed: () => _play(t),
                          tooltip: '播放',
                        )
                      else
                        IconButton(
                          icon: const Icon(Icons.cloud_upload_outlined, color: AppColors.textMuted, size: 18),
                          onPressed: () => _play(t),
                          tooltip: '串流播放',
                        ),
                    ]),
                  );
                },
              ),
            ),
        ],
      ]),
    );
  }
}