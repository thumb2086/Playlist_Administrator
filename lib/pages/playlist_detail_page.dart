import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/services.dart';
import '../models/playlist_item.dart';
import '../services/player_controller.dart';
import '../services/config_service.dart';
import '../services/favorites_service.dart';
import '../services/youtube_service.dart';
import '../widgets/dark_theme.dart';

/// Unified detail page for music playlists AND podcast shows.
/// Supports per-track download with checkmarks for already-downloaded items.
class PlaylistDetailPage extends StatefulWidget {
  final String title;
  final String? subtitle;
  final String? coverUrl;
  final List<PlaylistItem> items;
  final bool isPodcast;
  final String? spotifyUrl;

  const PlaylistDetailPage({
    super.key,
    required this.title,
    this.subtitle,
    this.coverUrl,
    required this.items,
    this.isPodcast = false,
    this.spotifyUrl,
  });

  @override
  State<PlaylistDetailPage> createState() => _PlaylistDetailPageState();
}

class _PlaylistDetailPageState extends State<PlaylistDetailPage> {
  /// Track indices currently being downloaded.
  final Set<int> _downloading = {};
  /// Track indices that have been downloaded in this session.
  final Set<int> _downloaded = {};
  /// Download progress per track (0.0 - 1.0).
  final Map<int, double> _progress = {};
  /// Which tracks are already on disk at startup.
  late Set<int> _localTracks;
  Set<String> _favorites = {};

  @override
  void initState() {
    super.initState();
    _localTracks = _findLocalTracks();
    _loadFavorites();
  }

  Future<void> _loadFavorites() async {
    final favs = await FavoritesService.load();
    if (mounted) setState(() => _favorites = favs);
  }

  bool _isFav(PlaylistItem item) {
    final key = '${item.name} - ${item.artist}'.toLowerCase();
    return _favorites.any((f) => f.toLowerCase().contains(key) || key.contains(f.toLowerCase()));
  }

  Future<void> _toggleFav(PlaylistItem item) async {
    final key = '${item.name} - ${item.artist}';
    final favs = await FavoritesService.load();
    final match = favs.firstWhere(
      (f) => f.toLowerCase().contains(key.toLowerCase()) || key.toLowerCase().contains(f.toLowerCase()),
      orElse: () => '',
    );
    if (match.isNotEmpty) {
      await FavoritesService.toggle(match);
    } else {
      await FavoritesService.toggle(key);
    }
    await _loadFavorites();
  }

  /// Check which tracks already exist in the local music library.
  Set<int> _findLocalTracks() {
    final result = <int>{};
    final cfg = ConfigService.instance.config;
    final musicDir = Directory(cfg.musicPath);
    if (!musicDir.existsSync()) return result;
    final localFiles = musicDir.listSync().whereType<File>()
        .where((f) => f.path.endsWith('.mp3'))
        .map((f) => f.uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '').toLowerCase())
        .toSet();
    for (int i = 0; i < widget.items.length; i++) {
      final query = widget.items[i].audioQuery.toLowerCase();
      for (final local in localFiles) {
        if (local == query || local.contains(query) || query.contains(local)) {
          result.add(i);
          break;
        }
      }
    }
    // Also check stream cache.
    final cacheDir = Directory(cfg.streamCachePath);
    if (cacheDir.existsSync()) {
      for (int i = 0; i < widget.items.length; i++) {
        if (result.contains(i)) continue;
        final query = widget.items[i].audioQuery.toLowerCase();
        final prefix = query.substring(0, query.length.clamp(0, 20));
        for (final f in cacheDir.listSync().whereType<File>()) {
          if (f.path.endsWith('.mp3') && f.lengthSync() > 65536) {
            final name = f.path.split(Platform.pathSeparator).last.toLowerCase();
            if (name.contains(prefix)) {
              result.add(i);
              break;
            }
          }
        }
      }
    }
    return result;
  }

  bool _isLocal(int index) => _localTracks.contains(index) || _downloaded.contains(index);
  bool _isDownloading(int index) => _downloading.contains(index);

  /// Register the Spotify playlist URL in config so Pipeline can scrape it.
  void _registerSpotifyUrl() {
    if (widget.spotifyUrl == null || widget.isPodcast) return;
    final cfg = ConfigService.instance.config;
    if (cfg.urlNames.containsKey(widget.spotifyUrl)) return;
    cfg.urlNames[widget.spotifyUrl!] = widget.title;
    ConfigService.instance.save();
  }

  Future<void> _downloadTrack(int index) async {
    if (_isLocal(index) || _isDownloading(index)) return;
    final item = widget.items[index];
    if (mounted) setState(() { _downloading.add(index); _progress[index] = 0; });
    try {
      final cfg = ConfigService.instance.config;
      final musicDir = Directory(cfg.musicPath);
      await musicDir.create(recursive: true);
      final finalName = '${item.name} - ${item.artist}'.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_');
      final finalPath = '${musicDir.path}\\$finalName.mp3';
      if (File(finalPath).existsSync()) {
        if (mounted) { _localTracks.add(index); setState(() { _downloaded.add(index); _progress[index] = 1.0; }); }
        return;
      }
      // Prefer artist+title for better YouTube matching, not ISRC.
      final searchQuery = '${item.artist} ${item.name}'.trim();
      debugPrint('[DL] $index start: query="$searchQuery" isrc=${item.isrc}');
      final streamResult = await YoutubeService.instance.resolveStream(searchQuery)
          .timeout(const Duration(seconds: 30), onTimeout: () {
        debugPrint('[DL] $index TIMEOUT resolving: $searchQuery');
        return null;
      });
      if (streamResult == null) {
        debugPrint('[DL] $index NOT FOUND: ${item.name}');
        if (mounted) ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('找不到: ${item.name}'), duration: const Duration(seconds: 2)));
        return;
      }
      debugPrint('[DL] $index resolved: ${streamResult.title}');
      if (mounted) setState(() { _progress[index] = 0.3; });
      final tmpPath = '${musicDir.path}\\dl_${finalName.hashCode.toRadixString(16)}.mp3';
      final ffmpeg = cfg.resolvedFfmpegPath;
      debugPrint('[DL] $index ffmpeg: $ffmpeg');
      final proc = await Process.start(
        ffmpeg,
        ['-y', '-i', streamResult.audioUrl, '-vn', '-acodec', 'libmp3lame', '-q:a', '0', '-ac', '2', tmpPath],
        runInShell: true,
      );
      // Capture stderr for debugging.
      final stderrOutput = await proc.stderr.transform(utf8.decoder).join();
      if (mounted) setState(() { _progress[index] = 0.5; });
      final code = await proc.exitCode.timeout(
        const Duration(seconds: 90), onTimeout: () { proc.kill(); return -1; },
      );
      if (code == 0 && File(tmpPath).existsSync()) {
        if (File(finalPath).existsSync()) await File(finalPath).delete();
        await File(tmpPath).rename(finalPath);
        debugPrint('[DL] $index OK: $finalPath');
        if (mounted) { _localTracks.add(index); setState(() { _downloaded.add(index); _progress[index] = 1.0; }); }
      } else {
        debugPrint('[DL] $index ffmpeg FAILED exit=$code stderr=$stderrOutput');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('下載失敗: ${item.name} (exit=$code)'), duration: const Duration(seconds: 3)));
        }
      }
    } catch (e) {
      debugPrint('[DL] error: $e');
    } finally {
      if (mounted) setState(() { _downloading.remove(index); });
    }
  }

  Future<void> _downloadAll() async {
    _registerSpotifyUrl();
    final toDownload = <int>[];
    for (int i = 0; i < widget.items.length; i++) {
      if (!_isLocal(i) && !_isDownloading(i)) {
        toDownload.add(i);
      }
    }
    if (toDownload.isEmpty) return;
    // Download 3 at a time, each with independent timeout.
    for (int batch = 0; batch < toDownload.length; batch += 3) {
      final chunk = toDownload.skip(batch).take(3).toList();
      await Future.wait(chunk.map((i) => _downloadTrack(i)), eagerError: false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final localCount = _localTracks.length + _downloaded.length;
    final totalCount = widget.items.length;

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: CustomScrollView(
        slivers: [
          SliverToBoxAdapter(child: _buildHeader(context, localCount, totalCount)),
          SliverToBoxAdapter(child: _buildColumnHeader()),
          SliverList(
            delegate: SliverChildBuilderDelegate(
              (ctx, i) => _buildTrackRow(ctx, i),
              childCount: widget.items.length,
            ),
          ),
          const SliverToBoxAdapter(child: SizedBox(height: 80)),
        ],
      ),
    );
  }

  Widget _buildHeader(BuildContext context, int localCount, int totalCount) {
    return Container(
      padding: const EdgeInsets.fromLTRB(24, 48, 24, 20),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: Container(
              width: 140, height: 140,
              color: AppColors.surfaceLight,
              child: widget.coverUrl != null
                  ? CachedNetworkImage(imageUrl: widget.coverUrl!, fit: BoxFit.cover,
                      placeholder: (_, __) => Container(color: AppColors.surfaceLight),
                      errorWidget: (_, __, ___) => Icon(
                          widget.isPodcast ? Icons.podcasts_rounded : Icons.music_note_rounded,
                          color: AppColors.textMuted, size: 48))
                  : Icon(
                      widget.isPodcast ? Icons.podcasts_rounded : Icons.music_note_rounded,
                      color: AppColors.textMuted, size: 48),
            ),
          ),
          const SizedBox(width: 20),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  widget.isPodcast ? 'Podcast 節目' : '歌單',
                  style: TextStyle(fontSize: 11, color: AppColors.textMuted.withValues(alpha: 0.7)),
                ),
                const SizedBox(height: 4),
                Text(widget.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
                if (widget.subtitle != null && widget.subtitle!.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(widget.subtitle!,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 12, color: AppColors.textMuted.withValues(alpha: 0.8))),
                ],
                const SizedBox(height: 8),
                Text('${totalCount} 首', style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
                const SizedBox(height: 12),
                Row(children: [
                  ElevatedButton.icon(
                    onPressed: () => _playAll(context, 0),
                    icon: const Icon(Icons.play_arrow_rounded, size: 18),
                    label: const Text('播放全部'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppColors.accent,
                      foregroundColor: Colors.black,
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    ),
                  ),
                  const SizedBox(width: 8),
                  OutlinedButton.icon(
                    onPressed: () => _playAll(context, -1),
                    icon: const Icon(Icons.shuffle_rounded, size: 16),
                    label: const Text('隨機'),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.text,
                      side: BorderSide(color: AppColors.border),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    ),
                  ),
                  if (!widget.isPodcast) ...[
                    const SizedBox(width: 8),
                    OutlinedButton.icon(
                      onPressed: _downloadAll,
                      icon: const Icon(Icons.download_rounded, size: 16),
                      label: Text(localCount > 0 ? '下載 ($localCount/$totalCount)' : '下載全部'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: AppColors.text,
                        side: BorderSide(color: AppColors.border),
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      ),
                    ),
                  ],
                ]),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildColumnHeader() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 8),
      decoration: BoxDecoration(
        border: Border(bottom: BorderSide(color: AppColors.border, width: 0.5)),
      ),
      child: Row(children: [
        const SizedBox(width: 32, child: Text('#', style: TextStyle(fontSize: 11, color: AppColors.textMuted))),
        const SizedBox(width: 48),
        const Expanded(flex: 5, child: Text('標題', style: TextStyle(fontSize: 11, color: AppColors.textMuted))),
        if (!widget.isPodcast)
          const Expanded(flex: 3, child: Text('專輯', style: TextStyle(fontSize: 11, color: AppColors.textMuted))),
        const SizedBox(width: 50, child: Text('時長', textAlign: TextAlign.right,
            style: TextStyle(fontSize: 11, color: AppColors.textMuted))),
        const SizedBox(width: 32),
        const SizedBox(width: 32),
      ]),
    );
  }

  Widget _buildTrackRow(BuildContext context, int index) {
    final item = widget.items[index];
    final isLocal = _isLocal(index);
    final isDownloading = _isDownloading(index);
    final progress = _progress[index] ?? 0;

    return InkWell(
      onTap: isDownloading ? null : () => _playTrack(context, index),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 6),
        child: Row(children: [
          // Number / play icon
          SizedBox(
            width: 32,
            child: isDownloading
                ? const Icon(Icons.downloading_rounded, size: 16, color: AppColors.accent)
                : Text('${index + 1}',
                    style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
          ),
          // Cover thumbnail
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: Container(
              width: 40, height: 40,
              color: AppColors.surfaceLight,
              child: (item.coverUrl ?? widget.coverUrl) != null
                  ? CachedNetworkImage(imageUrl: item.coverUrl ?? widget.coverUrl!, fit: BoxFit.cover,
                      placeholder: (_, __) => Container(color: AppColors.surfaceLight),
                      errorWidget: (_, __, ___) => const Icon(Icons.music_note_rounded, size: 16, color: AppColors.textMuted))
                  : const Icon(Icons.music_note_rounded, size: 16, color: AppColors.textMuted),
            ),
          ),
          const SizedBox(width: 12),
          // Title + Artist
          Expanded(
            flex: 5,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(item.name, maxLines: 1, overflow: TextOverflow.ellipsis,
                    style: TextStyle(fontSize: 13, fontWeight: FontWeight.w500,
                        color: isLocal ? AppColors.accent : AppColors.text)),
                if (item.artist.isNotEmpty)
                  Text(item.artist, maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 11, color: AppColors.textMuted)),
              ],
            ),
          ),
          // Album (music only)
          if (!widget.isPodcast)
            const Expanded(flex: 3, child: SizedBox()),
          // Duration
          SizedBox(
            width: 50,
            child: Text(item.durationText, textAlign: TextAlign.right,
                style: const TextStyle(fontSize: 11, color: AppColors.textMuted, fontFamily: 'Consolas')),
          ),
          // Favorite star
          SizedBox(
            width: 32,
            child: IconButton(
              icon: Icon(
                _isFav(item) ? Icons.star_rounded : Icons.star_border_rounded,
                size: 18,
                color: _isFav(item) ? AppColors.accent : AppColors.textMuted,
              ),
              onPressed: () => _toggleFav(item),
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 32),
            ),
          ),
          // Download / play button
          if (!widget.isPodcast)
            SizedBox(
              width: 32,
              child: isLocal
                  ? const Icon(Icons.check_circle_rounded, size: 18, color: AppColors.accent)
                  : isDownloading
                      ? const SizedBox(width: 18, height: 18)
                      : IconButton(
                          icon: const Icon(Icons.download_rounded, size: 18, color: AppColors.textMuted),
                          onPressed: () => _downloadTrack(index),
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(minWidth: 32),
                        ),
            )
          else
            IconButton(
              icon: const Icon(Icons.play_arrow_rounded, size: 18, color: AppColors.textMuted),
              onPressed: () => _playTrack(context, index),
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 32),
            ),
        ]),
      ),
    );
  }

  void _playAll(BuildContext context, int startIndex) {
    final ctrl = PlayerController.instance;
    final queries = widget.items.map((i) => i.audioQuery).toList();
    final titles = widget.items.map((i) => i.name).toList();
    ctrl.setQueue(queries, titles: titles, startIndex: startIndex < 0 ? 0 : startIndex, items: widget.items);
    final first = widget.items[startIndex < 0 ? 0 : startIndex];
    ctrl.playItem(first);
  }

  void _playTrack(BuildContext context, int index) {
    final ctrl = PlayerController.instance;
    final queries = widget.items.map((i) => i.audioQuery).toList();
    final titles = widget.items.map((i) => i.name).toList();
    ctrl.setQueue(queries, titles: titles, startIndex: index, items: widget.items);
    ctrl.playItem(widget.items[index]);
  }
}
