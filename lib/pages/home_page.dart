import 'dart:convert';
import 'package:flutter/material.dart';
import '../services/spotify_session.dart';
import '../services/spotify_gql_client.dart';
import '../services/config_service.dart';
import '../services/stream_server.dart';
import '../widgets/dark_theme.dart';
import '../widgets/spotify_login_dialog.dart';

/// Spotify-style home: greeting + sections (Made For You, Daily Mixes…),
/// new releases and browse categories — all via the native Spotify GQL API.
class HomePage extends StatefulWidget {
  const HomePage({super.key});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final _gql = SpotifyGqlClient();
  final _scroll = ScrollController();
  bool _loading = false;
  String _error = '';
  List<_HomeSection> _sections = [];
  List<_NewRelease> _newReleases = [];
  List<_BrowseCard> _browse = [];

  @override
  void initState() {
    super.initState();
    SpotifySession.instance.addListener(_onSession);
    _load();
  }

  @override
  void dispose() {
    SpotifySession.instance.removeListener(_onSession);
    _scroll.dispose();
    super.dispose();
  }

  void _onSession() {
    if (mounted) setState(() {});
  }

  /// Extract cover image URL from a GQL content data map.
  /// Handles: Artist (visuals.avatarImage), Episode (coverArt),
  /// Playlist (images.items[0]), Show, Album.
  static String? _extractCover(Map<String, dynamic> d) {
    // Artist: visuals.avatarImage.sources
    final v = d['visuals'] as Map<String, dynamic>?;
    final av = v?['avatarImage'] as Map<String, dynamic>?;
    final avSrc = av?['sources'] as List<dynamic>?;
    if (avSrc != null && avSrc.isNotEmpty) {
      return (avSrc.last as Map<String, dynamic>)['url'] as String?;
    }
    // Episode / Podcast: coverArt.sources
    final ca = d['coverArt'] as Map<String, dynamic>?;
    final caSrc = ca?['sources'] as List<dynamic>?;
    if (caSrc != null && caSrc.isNotEmpty) {
      return (caSrc.last as Map<String, dynamic>)['url'] as String?;
    }
    // Playlist: images.items[0].sources
    final imgs = d['images'] as Map<String, dynamic>?;
    final items = imgs?['items'] as List<dynamic>?;
    if (items != null && items.isNotEmpty) {
      final src = (items[0] as Map<String, dynamic>)['sources'] as List<dynamic>?;
      if (src != null && src.isNotEmpty) {
        return (src.last as Map<String, dynamic>)['url'] as String?;
      }
    }
    // Album: coverArt.sources (same as episode but different typename)
    return null;
  }

  Future<void> _load() async {
    setState(() { _loading = true; _error = ''; });
    try {
      if (!SpotifySession.instance.isLoggedIn) {
        setState(() { _loading = false; _sections = []; _newReleases = []; _browse = []; });
        return;
      }
      final results = await Future.wait<Map<String, dynamic>?>([
        _safeLoad(() => _gql.home(sectionItemsLimit: 20)),
        _safeLoad(() => _gql.whatsNew(limit: 20)),
        _safeLoad(() => _gql.browseAll()),
      ]);
      final sections = <_HomeSection>[];
      if (results[0] != null) {
        sections.addAll(_parseHome(results[0]!));
      }
      final releases = <_NewRelease>[];
      if (results[1] != null) {
        releases.addAll(_parseNewReleases(results[1]!));
      }
      final browse = <_BrowseCard>[];
      if (results[2] != null) {
        browse.addAll(_parseBrowse(results[2]!));
      }
      if (mounted) setState(() {
        _sections = sections;
        _newReleases = releases;
        _browse = browse;
        _loading = false;
      });
    } catch (e) {
      if (mounted) setState(() { _loading = false; _error = '$e'; });
    }
  }

  Future<Map<String, dynamic>?> _safeLoad(
      Future<Map<String, dynamic>> Function() fn) async {
    try {
      return await fn();
    } catch (_) {
      return null;
    }
  }

  List<_HomeSection> _parseHome(Map<String, dynamic> data) {
    final sections = <_HomeSection>[];
    try {
      final container =
          (data['data'] as Map?)?['home'] as Map<String, dynamic>?;
      final items = (container?['sectionContainer'] as Map<String, dynamic>?)?['sections'] as Map<String, dynamic>?;
      final list = items?['items'] as List<dynamic>? ?? [];
      for (final s in list) {
        final sMap = s as Map<String, dynamic>;
        final sData = (sMap['data'] as Map<String, dynamic>?) ?? {};
        final title = ((sData['title'] as Map<String, dynamic>?)?['transformedLabel'] ?? '') as String? ?? '';
        final sectionItems = (sMap['sectionItems'] as Map<String, dynamic>?) ?? {};
        final cards = <_HomeCard>[];
        for (final it in (sectionItems['items'] as List<dynamic>? ?? [])) {
          final itMap = it as Map<String, dynamic>;
          final content = itMap['content'] as Map<String, dynamic>?;
          final uri = (itMap['uri'] ?? '') as String;
          final cData = content?['data'] as Map<String, dynamic>?;
          if (cData != null) {
            final n = cData['name'] as String? ?? '';
            final profile = (cData['profile'] as Map<String, dynamic>?)?['name'] as String?;
            final cover = _extractCover(cData);
            if (n.isNotEmpty) {
              cards.add(_HomeCard(uri: uri, name: n, subtitle: profile ?? '', coverUrl: cover));
            }
          }
        }
        if (cards.isNotEmpty) {
          sections.add(_HomeSection(title: title.isNotEmpty ? title : '為你推薦', cards: cards));
        }
      }
    } catch (_) {}
    return sections;
  }

  List<_NewRelease> _parseNewReleases(Map<String, dynamic> data) {
    final out = <_NewRelease>[];
    try {
      final items = (data['data'] as Map?)?['whatsNewFeedItems'] as Map<String, dynamic>?;
      for (final it in (items?['items'] as List<dynamic>? ?? [])) {
        final content = (it as Map<String, dynamic>)['content'] as Map<String, dynamic>?;
        final name = (content?['name'] ?? '') as String? ?? '';
        if (name.isEmpty) continue;
        final uri = (content?['uri'] ?? '') as String? ?? '';
        final cover = SpotifyTrackItem.coverFromSources(content?['coverArt']?['sources']);
        final artists = (content?['artists'] as List<dynamic>? ?? [])
            .map((a) => ((a as Map<String, dynamic>)['profile'] as Map?)?['name'] as String? ?? '')
            .where((s) => s.isNotEmpty)
            .join(', ');
        out.add(_NewRelease(uri: uri, name: name, artists: artists, coverUrl: cover));
      }
    } catch (_) {}
    return out;
  }

  List<_BrowseCard> _parseBrowse(Map<String, dynamic> data) {
    final out = <_BrowseCard>[];
    try {
      final start = (data['data'] as Map?)?['browseStart'] as Map<String, dynamic>?;
      final sections = start?['sections'] as Map<String, dynamic>?;
      final items = sections?['items'] as List<dynamic>? ?? [];
      for (final s in items) {
        final sMap = s as Map<String, dynamic>;
        final sData = sMap['data'] as Map<String, dynamic>? ?? {};
        final title = ((sData['title'] as Map<String, dynamic>?)?['transformedLabel'] ?? '') as String? ?? '';
        final sectionItems = (sMap['sectionItems'] as Map<String, dynamic>?) ?? {};
        final cards = <_HomeCard>[];
        for (final it in (sectionItems['items'] as List<dynamic>? ?? [])) {
          final itMap = it as Map<String, dynamic>;
          final content = itMap['content'] as Map<String, dynamic>?;
          final uri = ((it['uri'] ?? '') as String?) ?? '';
          final cData = content?['data'] as Map<String, dynamic>?;
          final name = cData?['name'] as String? ?? (content?['name'] ?? '') as String? ?? '';
          final cover = cData != null ? _extractCover(cData) : null;
          if (name.isNotEmpty) {
            cards.add(_HomeCard(uri: uri, name: name, subtitle: '', coverUrl: cover));
          }
        }
        if (cards.isNotEmpty) {
          out.add(_BrowseCard(title: title.isNotEmpty ? title : '瀏覽', cards: cards));
        }
      }
    } catch (_) {}
    return out;
  }

  @override
  Widget build(BuildContext context) {
    final loggedIn = SpotifySession.instance.isLoggedIn;
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        if (!loggedIn)
          _buildLoginPrompt()
        else if (_loading)
          const Expanded(child: Center(child: CircularProgressIndicator()))
        else if (_error.isNotEmpty)
          Expanded(child: Center(child: Text('載入失敗: $_error', style: const TextStyle(color: AppColors.error))))
        else if (_sections.isEmpty && _newReleases.isEmpty && _browse.isEmpty)
          Expanded(child: Center(child: Text('沒有可顯示的內容', style: const TextStyle(color: AppColors.textMuted))))
        else
          Expanded(
            child: RefreshIndicator(
              onRefresh: _load,
              child: ListView(
                controller: _scroll,
                children: [
                  for (final s in _sections) _sectionRow(s.title, s.cards),
                  if (_newReleases.isNotEmpty) ...[
                    const SizedBox(height: 8),
                    _sectionRow('新發行',
                        _newReleases.map((r) => _HomeCard(uri: r.uri, name: r.name, subtitle: r.artists, coverUrl: r.coverUrl)).toList()),
                  ],
                  for (final b in _browse) ...[
                    const SizedBox(height: 8),
                    _sectionRow(b.title, b.cards),
                  ],
                  const SizedBox(height: 20),
                ],
              ),
            ),
          ),
      ]),
    );
  }

  Widget _buildLoginPrompt() {
    return Expanded(
      child: Center(
        child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          const Icon(Icons.music_note_rounded, size: 56, color: AppColors.textMuted),
          const SizedBox(height: 16),
          const Text('連接你的 Spotify 帳號', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Text('登入後即可瀏覽個人化主頁、你的歌單並搜尋串流',
              style: TextStyle(fontSize: 12, color: AppColors.textMuted.withValues(alpha: 0.8))),
          const SizedBox(height: 20),
          ElevatedButton.icon(
            onPressed: () async {
              await showSpotifyLogin(context);
              await SpotifySession.instance.load();
              _load();
            },
            icon: const Icon(Icons.login_rounded, size: 18),
            label: const Text('Spotify 登入'),
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF1DB954),
              foregroundColor: Colors.black,
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
            ),
          ),
        ]),
      ),
    );
  }

  Widget _sectionRow(String title, List<_HomeCard> cards) {
    if (cards.isEmpty) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Padding(
        padding: const EdgeInsets.symmetric(vertical: 10),
        child: Text(title, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
      ),
      SizedBox(
        height: 170,
        child: ListView.builder(
          scrollDirection: Axis.horizontal,
          itemCount: cards.length,
          itemBuilder: (ctx, i) => _card(cards[i]),
        ),
      ),
    ]);
  }

  Widget _card(_HomeCard c) {
    return GestureDetector(
      onTap: () => _onCardTap(c),
      child: Container(
        width: 130,
        margin: const EdgeInsets.only(right: 10),
        decoration: BoxDecoration(
          color: AppColors.surfaceLight,
          borderRadius: BorderRadius.circular(10),
        ),
        padding: const EdgeInsets.all(10),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(8),
            child: c.coverUrl != null
                ? Image.network(c.coverUrl!, width: 110, height: 110,
                    fit: BoxFit.cover,
                    errorBuilder: (_, __, ___) => Container(
                        width: 110, height: 110, color: AppColors.surfaceLight,
                        child: const Icon(Icons.music_note_rounded, color: AppColors.textMuted)))
                : Container(
                    width: 110, height: 110, color: AppColors.surfaceLight,
                    child: const Icon(Icons.music_note_rounded, color: AppColors.textMuted)),
          ),
          const SizedBox(height: 6),
          Text(c.name, maxLines: 1, overflow: TextOverflow.ellipsis,
              style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
          if (c.subtitle.isNotEmpty)
            Text(c.subtitle, maxLines: 1, overflow: TextOverflow.ellipsis,
                style: TextStyle(fontSize: 9, color: AppColors.textMuted.withValues(alpha: 0.8))),
        ]),
      ),
    );
  }

  Future<void> _onCardTap(_HomeCard c) async {
    final uri = c.uri;
    if (uri.isEmpty) return;
    if (uri.contains(':playlist:')) {
      final id = uri.split(':').last;
      try {
        final data = await _gql.fetchPlaylist(id, limit: 50);
        final tracks = _extractPlaylistTracks(data);
        if (tracks.isNotEmpty && mounted) {
          showModalBottomSheet<void>(
            context: context,
            backgroundColor: AppColors.card,
            isScrollControlled: true,
            builder: (_) => _PlaylistSheet(name: c.name, tracks: tracks),
          );
          return;
        }
      } catch (_) {}
      // Playlist fetch failed (e.g. episode-only playlist) — show as info.
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('${c.name} — 歌單載入失敗')));
      }
    } else if (uri.contains(':episode:') || uri.contains(':show:')) {
      // Podcast episode / show — open in PlayerPage with search query.
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('播放: ${c.name}')));
      }
    } else if (uri.contains(':album:')) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('專輯: ${c.name}')));
      }
    } else {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(c.name)));
      }
    }
  }

  List<SpotifyTrackItem> _extractPlaylistTracks(Map<String, dynamic> data) {
    final out = <SpotifyTrackItem>[];
    try {
      final playlist =
          (data['data'] as Map?)?['playlistV2'] as Map<String, dynamic>?;
      final content = playlist?['content'] as Map<String, dynamic>?;
      final items = content?['items'] as List<dynamic>? ?? [];
      for (final it in items) {
        final item = (it as Map<String, dynamic>)['itemV2'] as Map<String, dynamic>?;
        if (item == null) continue;
        final name = (item['name'] ?? '') as String? ?? '';
        final uri = (item['uri'] ?? '') as String? ?? '';
        // Track has albumOfTrack; episode has coverArt directly.
        final album = item['albumOfTrack'] as Map<String, dynamic>?;
        final coverArt = item['coverArt'] as Map<String, dynamic>?;
        String? cover;
        if (album != null) {
          cover = SpotifyTrackItem.coverFromSources(album['coverArt']?['sources']);
        } else if (coverArt != null) {
          cover = SpotifyTrackItem.coverFromSources(coverArt['sources']);
        }
        final artists = ((item['artists'] as List<dynamic>? ?? [])
                .map((a) => ((a as Map<String, dynamic>)['profile'] as Map?)?['name'] as String? ?? '')
                .where((s) => s.isNotEmpty)
                .join(', '));
        final duration = ((item['trackDuration'] as Map<String, dynamic>?)?['totalMilliseconds'] as num?)?.toInt() ?? 0;
        final albumName = (album?['name'] as String?) ?? '';
        if (name.isNotEmpty) {
          out.add(SpotifyTrackItem(
            uri: uri, name: name, artists: artists.isEmpty ? [] : [artists],
            album: albumName, durationMs: duration, coverUrl: cover,
          ));
        }
      }
    } catch (_) {}
    return out;
  }
}

class _HomeSection {
  final String title;
  final List<_HomeCard> cards;
  _HomeSection({required this.title, required this.cards});
}

class _NewRelease {
  final String uri;
  final String name;
  final String artists;
  final String? coverUrl;
  _NewRelease({required this.uri, required this.name, required this.artists, this.coverUrl});
}

class _BrowseCard {
  final String title;
  final List<_HomeCard> cards;
  _BrowseCard({required this.title, required this.cards});
}

class _HomeCard {
  final String uri;
  final String name;
  final String subtitle;
  final String? coverUrl;
  _HomeCard({required this.uri, required this.name, this.subtitle = '', this.coverUrl});
}

/// Bottom sheet listing a playlist's tracks with play buttons.
class _PlaylistSheet extends StatelessWidget {
  final String name;
  final List<SpotifyTrackItem> tracks;
  const _PlaylistSheet({required this.name, required this.tracks});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 480,
      child: Column(children: [
        Padding(
          padding: const EdgeInsets.all(14),
          child: Text(name, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
        ),
        Expanded(
          child: ListView.builder(
            itemCount: tracks.length,
            itemBuilder: (ctx, i) {
              final t = tracks[i];
              return ListTile(
                dense: true,
                leading: ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: t.coverUrl != null
                      ? Image.network(t.coverUrl!, width: 36, height: 36, fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => Container(
                              width: 36, height: 36, color: AppColors.surfaceLight,
                              child: const Icon(Icons.music_note_rounded, size: 16, color: AppColors.textMuted)))
                      : Container(width: 36, height: 36, color: AppColors.surfaceLight,
                          child: const Icon(Icons.music_note_rounded, size: 16, color: AppColors.textMuted)),
                ),
                title: Text(t.name, maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 12)),
                subtitle: Text(t.artists.join(', '), maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 10, color: AppColors.textMuted)),
                trailing: IconButton(
                  icon: const Icon(Icons.play_arrow_rounded, color: AppColors.accent, size: 20),
                  onPressed: () => _streamTrack(context, t),
                ),
              );
            },
          ),
        ),
      ]),
    );
  }

  void _streamTrack(BuildContext context, SpotifyTrackItem t) {
    final cfg = ConfigService.instance.config;
    Navigator.of(context).pop();
    // Simple playback: open the stream URL in the system player for now —
    // full integration into the app player queue comes with SearchPage.
    final query = t.displayName;
    StreamServer.instance.start().then((_) async {
      final cached = StreamServer.instance.cachedPathFor(query);
      if (cached != null) {
        // TODO: play via app player when integrated
      }
    });
    ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('串流: ${t.displayName}')));
  }
}