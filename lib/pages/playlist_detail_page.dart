import 'package:flutter/material.dart';
import '../models/playlist_item.dart';
import '../services/player_controller.dart';
import '../widgets/dark_theme.dart';

/// Unified detail page for music playlists AND podcast shows.
/// Receives a list of PlaylistItem (tracks or episodes) + metadata.
class PlaylistDetailPage extends StatelessWidget {
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
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.bg,
      body: CustomScrollView(
        slivers: [
          // --- Header ---
          SliverToBoxAdapter(child: _buildHeader(context)),
          // --- Column header ---
          SliverToBoxAdapter(child: _buildColumnHeader()),
          // --- Track list ---
          SliverList(
            delegate: SliverChildBuilderDelegate(
              (ctx, i) => _buildTrackRow(ctx, i),
              childCount: items.length,
            ),
          ),
          const SliverToBoxAdapter(child: SizedBox(height: 80)),
        ],
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(24, 48, 24, 20),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Cover
          ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: Container(
              width: 140, height: 140,
              color: AppColors.surfaceLight,
              child: coverUrl != null
                  ? Image.network(coverUrl!, fit: BoxFit.cover,
                      errorBuilder: (_, __, ___) => Icon(
                          isPodcast ? Icons.podcasts_rounded : Icons.music_note_rounded,
                          color: AppColors.textMuted, size: 48))
                  : Icon(
                      isPodcast ? Icons.podcasts_rounded : Icons.music_note_rounded,
                      color: AppColors.textMuted, size: 48),
            ),
          ),
          const SizedBox(width: 20),
          // Info + actions
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  isPodcast ? 'Podcast 節目' : '歌單',
                  style: TextStyle(fontSize: 11, color: AppColors.textMuted.withValues(alpha: 0.7)),
                ),
                const SizedBox(height: 4),
                Text(title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
                if (subtitle != null && subtitle!.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(subtitle!,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 12, color: AppColors.textMuted.withValues(alpha: 0.8))),
                ],
                const SizedBox(height: 8),
                Text('${items.length} 首', style: const TextStyle(fontSize: 12, color: AppColors.textMuted)),
                const SizedBox(height: 12),
                Row(children: [
                  // Play All
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
                  // Shuffle
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
        if (!isPodcast)
          const Expanded(flex: 3, child: Text('專輯', style: TextStyle(fontSize: 11, color: AppColors.textMuted))),
        const SizedBox(width: 50, child: Text('時長', textAlign: TextAlign.right,
            style: TextStyle(fontSize: 11, color: AppColors.textMuted))),
      ]),
    );
  }

  Widget _buildTrackRow(BuildContext context, int index) {
    final item = items[index];
    return InkWell(
      onTap: () => _playTrack(context, index),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 6),
        child: Row(children: [
          // Number / play icon
          SizedBox(
            width: 32,
            child: Text('${index + 1}',
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
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500)),
                if (item.artist.isNotEmpty)
                  Text(item.artist, maxLines: 1, overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontSize: 11, color: AppColors.textMuted)),
              ],
            ),
          ),
          // Album (music only)
          if (!isPodcast)
            const Expanded(flex: 3, child: SizedBox()),
          // Duration
          SizedBox(
            width: 50,
            child: Text(item.durationText, textAlign: TextAlign.right,
                style: const TextStyle(fontSize: 11, color: AppColors.textMuted, fontFamily: 'Consolas')),
          ),
          // Play button
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
    final queries = items.map((i) => i.audioQuery).toList();
    final titles = items.map((i) => i.name).toList();
    ctrl.setQueue(queries, titles: titles, startIndex: startIndex < 0 ? 0 : startIndex);
    final first = items[startIndex < 0 ? 0 : startIndex];
    ctrl.playItem(first);
  }

  void _playTrack(BuildContext context, int index) {
    final ctrl = PlayerController.instance;
    final queries = items.map((i) => i.audioQuery).toList();
    final titles = items.map((i) => i.name).toList();
    ctrl.setQueue(queries, titles: titles, startIndex: index);
    ctrl.playItem(items[index]);
  }
}
