import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/playlist_item.dart';
import '../services/player_controller.dart';
import '../services/config_service.dart';
import '../services/stream_server.dart';
import '../widgets/dark_theme.dart';

/// Unified detail page for music playlists AND podcast shows.
/// Supports per-track download with checkmarks for already-downloaded items.
class PlaylistDetailPage extends StatefulWidget {
  final String title;
  final String? subtitle;
  final String? coverUrl;
  final List<PlaylistItem> items;
  final bool isPodcast;

  const PlaylistDetailPage({
    super.key,
    required this.title,
    this.subtitle,
    this.coverUrl,
    required this.items,
    this.isPodcast = false,
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

  @override
  void initState() {
    super.initState();
    _localTracks = _findLocalTracks();
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

  Future<void> _downloadTrack(int index) async {
    if (_isLocal(index) || _isDownloading(index)) return;
    final item = widget.items[index];
    setState(() { _downloading.add(index); _progress[index] = 0; });
    try {
      await StreamServer.instance.start();
      final cacheDir = Directory(ConfigService.instance.config.streamCachePath);
      await cacheDir.create(recursive: true);
      final safeName = item.audioQuery.replaceAll(RegExp(r'[\\/:*?"<>|]'), '_').replaceAll(RegExp(r'\s+'), ' ').trim();
      final outBase = '${cacheDir.path}\\dl_${safeName.hashCode.toRadixString(16)}';
      final proc = await Process.start(
        'python',
        ['${ConfigService.instance.config.toolsPath}\\flutter_download_bridge.py',
         'stream-download', item.audioQuery, outBase] + (item.isrc != null ? [item.isrc!] : []),
        runInShell: true,
        workingDirectory: ConfigService.instance.config.basePath,
        environment: {'PYTHONIOENCODING': 'utf-8'},
      );
      final out = await proc.stdout.transform(utf8.decoder).join();
      final code = await proc.exitCode;
      if (code == 0) {
        for (final line in out.split('\n')) {
          final trimmed = line.trim();
          if (trimmed.isEmpty) continue;
          try {
            final data = Map<String, dynamic>.from(
                Map<String, dynamic>.from({'type': ''}));
            // Manual JSON parse for safety
            if (!trimmed.startsWith('{')) continue;
            final parsed = _simpleJsonParse(trimmed);
            if (parsed['type'] == 'complete' && parsed['path'] != null) {
              final srcPath = parsed['path'] as String;
              final finalPath = '${cacheDir.path}\\$safeName.mp3';
              if (srcPath != finalPath && File(srcPath).existsSync()) {
                await File(srcPath).rename(finalPath);
              }
              if (mounted) setState(() { _downloaded.add(index); _progress[index] = 1.0; });
              break;
            }
          } catch (_) {}
        }
      }
    } catch (e) {
      debugPrint('[PlaylistDetail] download error: $e');
    } finally {
      if (mounted) setState(() { _downloading.remove(index); });
    }
  }

  /// Simple JSON string parser — extracts key-value pairs we care about.
  Map<String, dynamic> _simpleJsonParse(String json) {
    final result = <String, dynamic>{};
    // Extract "type": "value"
    final typeMatch = RegExp(r'"type"\s*:\s*"([^"]*)"').firstMatch(json);
    if (typeMatch != null) result['type'] = typeMatch.group(1);
    // Extract "path": "value"
    final pathMatch = RegExp(r'"path"\s*:\s*"([^"]*)"').firstMatch(json);
    if (pathMatch != null) result['path'] = pathMatch.group(1);
    // Extract "message": "value"
    final msgMatch = RegExp(r'"message"\s*:\s*"([^"]*)"').firstMatch(json);
    if (msgMatch != null) result['message'] = msgMatch.group(1);
    return result;
  }

  Future<void> _downloadAll() async {
    for (int i = 0; i < widget.items.length; i++) {
      if (!_isLocal(i) && !_isDownloading(i)) {
        await _downloadTrack(i);
      }
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
                  ? Image.network(widget.coverUrl!, fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => Icon(
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
                ? SizedBox(width: 14, height: 14, child: CircularProgressIndicator(
                    strokeWidth: 2, value: progress > 0 ? progress : null,
                    color: AppColors.accent))
                : Text('${index + 1}',
                    style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
          ),
          // Cover thumbnail
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: Container(
              width: 40, height: 40,
              color: AppColors.surfaceLight,
              child: item.coverUrl != null
                  ? Image.network(item.coverUrl!, fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => const Icon(Icons.music_note_rounded, size: 16, color: AppColors.textMuted))
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
