import 'dart:io';
import 'package:flutter/material.dart';
import '../services/config_service.dart';
import '../models/playlist.dart';
import '../widgets/dark_theme.dart';

class LibraryPage extends StatefulWidget {
  const LibraryPage({super.key});
  @override
  State<LibraryPage> createState() => LibraryPageState();
}

class LibraryPageState extends State<LibraryPage> {
  final _urlCtrl = TextEditingController();
  Map<String, _PlStats> _stats = {};
  bool _loading = false;

  @override
  void dispose() {
    _urlCtrl.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  Future<void> _refresh() async {
    setState(() => _loading = true);
    final plDir = Directory(ConfigService.instance.config.playlistsPath);
    final stats = <String, _PlStats>{};
    if (await plDir.exists()) {
      await for (final e in plDir.list()) {
        if (e is File && e.path.toLowerCase().endsWith('.m3u8')) {
          try {
            final lines = await e.readAsLines();
            int total = 0, matched = 0;
            for (final line in lines) {
              if (!line.startsWith('#') && line.trim().isNotEmpty) {
                total++;
                final resolved = '${ConfigService.instance.config.libraryPath}\\${File(line).uri.pathSegments.last}';
                if (await File(resolved).exists()) matched++;
              }
            }
            stats[File(e.path).uri.pathSegments.last.replaceAll('.m3u8', '')] = _PlStats(total, matched);
          } catch (_) {}
        }
      }
    }
    if (mounted) setState(() { _stats = stats; _loading = false; });
  }

  void _addUrl() {
    final url = _urlCtrl.text.trim();
    if (url.isEmpty) return;
    final cfg = ConfigService.instance.config;
    final id = url.split('/').last.split('?').first;
    cfg.urlNames[url] = id.substring(0, 12);
    ConfigService.instance.save();
    _urlCtrl.clear();
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final playlists = ConfigService.instance.config.playlists;
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // URL input
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppColors.card,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: AppColors.border),
            ),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _urlCtrl,
                    decoration: const InputDecoration(
                      hintText: '貼上 Spotify 播放清單 URL…',
                      prefixIcon: Icon(Icons.link, size: 18),
                      border: OutlineInputBorder(),
                    ),
                    style: const TextStyle(fontSize: 13),
                    onSubmitted: (_) => _addUrl(),
                  ),
                ),
                const SizedBox(width: 10),
                _GradientBtn('加入', Icons.add, _addUrl),
                const SizedBox(width: 8),
                IconButton(
                  onPressed: _refresh,
                  icon: _loading
                      ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.refresh_rounded),
                  tooltip: '重新整理',
                  style: IconButton.styleFrom(backgroundColor: AppColors.surfaceLight),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          // Stats bar
          _buildStatsBar(playlists),
          const SizedBox(height: 14),
          // Grid
          Expanded(
            child: playlists.isEmpty
                ? Center(
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.library_music_outlined, size: 64, color: AppColors.textMuted.withValues(alpha: 0.3)),
                        const SizedBox(height: 12),
                        const Text('尚未加入歌單', style: TextStyle(color: AppColors.textMuted, fontSize: 15)),
                        const SizedBox(height: 4),
                        const Text('貼上 Spotify URL 開始', style: TextStyle(color: AppColors.textMuted, fontSize: 12)),
                      ],
                    ),
                  )
                : RefreshIndicator(
                    onRefresh: _refresh,
                    child: GridView.builder(
                      padding: const EdgeInsets.only(bottom: 24),
                      gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                        maxCrossAxisExtent: 240,
                        mainAxisExtent: 190,
                        crossAxisSpacing: 14,
                        mainAxisSpacing: 14,
                      ),
                      itemCount: playlists.length,
                      itemBuilder: (ctx, i) => _PlaylistCard(
                        playlist: playlists[i],
                        stats: _stats[playlists[i].name],
                        onRemove: () {
                          ConfigService.instance.config.urlNames.remove(playlists[i].url);
                          ConfigService.instance.save();
                          setState(() {});
                        },
                      ),
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatsBar(List<PlaylistConfig> playlists) {
    int totalTracks = 0, totalMatched = 0;
    for (final p in playlists) {
      final s = _stats[p.name];
      if (s != null) { totalTracks += s.total; totalMatched += s.matched; }
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: Row(children: [
        _Chip(Icons.playlist_play, '${playlists.length}', '歌單'),
        const SizedBox(width: 20),
        _Chip(Icons.music_note, '$totalTracks', '歌曲'),
        const SizedBox(width: 20),
        _Chip(Icons.check_circle, '$totalMatched', '已匹配', color: AppColors.accent),
        if (totalTracks > 0) ...[
          const SizedBox(width: 20),
          _Chip(Icons.trending_up, totalTracks > 0 ? '${(totalMatched / totalTracks * 100).toStringAsFixed(0)}%' : '0%', '完成率'),
        ],
      ]),
    );
  }
}

class _Chip extends StatelessWidget {
  final IconData icon; final String value; final String label; final Color? color;
  const _Chip(this.icon, this.value, this.label, {this.color});
  @override
  Widget build(BuildContext context) => Row(mainAxisSize: MainAxisSize.min, children: [
    Icon(icon, size: 14, color: color ?? AppColors.textMuted),
    const SizedBox(width: 6),
    Text(value, style: TextStyle(color: color ?? AppColors.text, fontWeight: FontWeight.bold, fontSize: 13)),
    const SizedBox(width: 4),
    Text(label, style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
  ]);
}

class _PlStats { final int total; final int matched; _PlStats(this.total, this.matched); }

class _PlaylistCard extends StatelessWidget {
  final PlaylistConfig playlist; final _PlStats? stats; final VoidCallback onRemove;
  const _PlaylistCard({required this.playlist, this.stats, required this.onRemove});

  @override
  Widget build(BuildContext context) {
    final total = stats?.total ?? 0;
    final matched = stats?.matched ?? 0;
    final pct = total > 0 ? matched / total : 0.0;
    final full = total > 0 && matched >= total;

    return Container(
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: full ? AppColors.accent.withValues(alpha: 0.3) : AppColors.border),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(14),
          onTap: () {},
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      width: 36, height: 36,
                      decoration: BoxDecoration(
                        color: full ? AppColors.accentDim : AppColors.surfaceLight,
                        borderRadius: BorderRadius.circular(10),
                      ),
                      child: Icon(
                        full ? Icons.check_circle : Icons.playlist_play_rounded,
                        color: full ? AppColors.accent : AppColors.textMuted,
                        size: 20,
                      ),
                    ),
                    const Spacer(),
                    InkWell(
                      onTap: onRemove,
                      borderRadius: BorderRadius.circular(6),
                      child: Container(
                        padding: const EdgeInsets.all(4),
                        child: const Icon(Icons.close, color: AppColors.textMuted, size: 14),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
                Text(playlist.name, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13, height: 1.3),
                    maxLines: 2, overflow: TextOverflow.ellipsis),
                const Spacer(),
                if (total > 0) ...[
                  Row(
                    children: [
                      Text('$matched/$total 首', style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
                      const Spacer(),
                      Text('${(pct * 100).toStringAsFixed(0)}%',
                          style: TextStyle(color: full ? AppColors.accent : AppColors.textMuted, fontSize: 11, fontWeight: FontWeight.w600)),
                    ],
                  ),
                  const SizedBox(height: 6),
                  TweenAnimationBuilder<double>(
                    tween: Tween(begin: 0, end: pct),
                    duration: const Duration(milliseconds: 800),
                    curve: Curves.easeOutCubic,
                    builder: (ctx, v, _) => ClipRRect(
                      borderRadius: BorderRadius.circular(3),
                      child: LinearProgressIndicator(
                        value: v,
                        backgroundColor: AppColors.surfaceLight,
                        valueColor: AlwaysStoppedAnimation(full ? AppColors.accent : AppColors.textMuted.withValues(alpha: 0.4)),
                        minHeight: 5,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _GradientBtn extends StatelessWidget {
  final String label; final IconData icon; final VoidCallback onPressed;
  _GradientBtn(this.label, this.icon, this.onPressed);

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        gradient: const LinearGradient(colors: [AppColors.accent, Color(0xFF169C46)]),
        borderRadius: BorderRadius.circular(8),
      ),
      child: ElevatedButton.icon(
        onPressed: onPressed,
        icon: Icon(icon, size: 16),
        label: Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.transparent,
          shadowColor: Colors.transparent,
          foregroundColor: Colors.black,
        ),
      ),
    );
  }
}
