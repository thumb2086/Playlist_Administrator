import 'dart:io';
import 'package:flutter/material.dart';
import '../services/config_service.dart';
import '../models/playlist.dart';

class LibraryPage extends StatefulWidget {
  const LibraryPage({super.key});
  @override
  State<LibraryPage> createState() => LibraryPageState();
}

class LibraryPageState extends State<LibraryPage> {
  final _urlCtrl = TextEditingController();
  Map<String, _PlStats> _stats = {};

  @override
  void dispose() {
    _urlCtrl.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    _refreshStats();
  }

  Future<void> _refreshStats() async {
    final plDir = Directory(ConfigService.instance.config.playlistsPath);
    final stats = <String, _PlStats>{};
    if (await plDir.exists()) {
      await for (final e in plDir.list()) {
        if (e is File && e.path.toLowerCase().endsWith('.m3u8')) {
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
        }
      }
    }
    if (mounted) setState(() => _stats = stats);
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
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // URL input row
          Row(
            children: [
              SizedBox(
                width: 420,
                child: TextField(
                  controller: _urlCtrl,
                  decoration: const InputDecoration(
                    hintText: '貼上 Spotify 播放清單 URL…',
                    border: OutlineInputBorder(),
                    contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    filled: true,
                  ),
                  style: const TextStyle(fontSize: 13),
                  onSubmitted: (_) => _addUrl(),
                ),
              ),
              const SizedBox(width: 8),
              ElevatedButton(
                onPressed: _addUrl,
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF1DB954),
                  foregroundColor: Colors.black,
                ),
                child: const Text('加入', style: TextStyle(fontWeight: FontWeight.bold)),
              ),
              const SizedBox(width: 8),
              IconButton(
                onPressed: _refreshStats,
                icon: const Icon(Icons.refresh),
                tooltip: '重新整理狀態',
              ),
            ],
          ),
          const SizedBox(height: 16),
          // Stats summary bar
          _buildSummaryBar(playlists),
          const SizedBox(height: 12),
          // Playlist grid
          Expanded(
            child: playlists.isEmpty
                ? const Center(child: Text('尚未加入歌單', style: TextStyle(color: Colors.grey)))
                : RefreshIndicator(
                    onRefresh: _refreshStats,
                    child: GridView.builder(
                      gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                        maxCrossAxisExtent: 220,
                        mainAxisExtent: 170,
                        crossAxisSpacing: 12,
                        mainAxisSpacing: 12,
                      ),
                      itemCount: playlists.length,
                      itemBuilder: (ctx, i) => _buildCard(playlists[i]),
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildSummaryBar(List<PlaylistConfig> playlists) {
    int totalTracks = 0;
    int totalMatched = 0;
    for (final p in playlists) {
      final s = _stats[p.name];
      if (s != null) {
        totalTracks += s.total;
        totalMatched += s.matched;
      }
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF1e1e1e),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          _StatChip('歌單', '${playlists.length}', Icons.playlist_play),
          const SizedBox(width: 16),
          _StatChip('歌曲', '$totalTracks', Icons.music_note),
          const SizedBox(width: 16),
          _StatChip('已匹配', '$totalMatched', Icons.check_circle, color: const Color(0xFF1DB954)),
          const SizedBox(width: 16),
          if (totalTracks > 0)
            _StatChip('完成率', '${(totalMatched / totalTracks * 100).toStringAsFixed(0)}%', Icons.pie_chart),
        ],
      ),
    );
  }

  Widget _buildCard(PlaylistConfig pl) {
    final s = _stats[pl.name];
    final total = s?.total ?? 0;
    final matched = s?.matched ?? 0;
    final pct = total > 0 ? matched / total : 0.0;
    final isFull = total > 0 && matched >= total;

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF1e1e1e),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: isFull ? const Color(0xFF1DB954).withOpacity(0.3) : const Color(0xFF2a2a2a)),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: () {},
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(isFull ? Icons.check_circle : Icons.playlist_play,
                        color: isFull ? const Color(0xFF1DB954) : Colors.grey, size: 28),
                    const Spacer(),
                    InkWell(
                      onTap: () {
                        ConfigService.instance.config.urlNames.remove(pl.url);
                        ConfigService.instance.save();
                        setState(() {});
                      },
                      child: const Icon(Icons.close, color: Colors.grey, size: 16),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(pl.name,
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                    maxLines: 2, overflow: TextOverflow.ellipsis),
                const Spacer(),
                if (total > 0) ...[
                  Row(
                    children: [
                      Text('$matched/$total', style: TextStyle(color: Colors.grey[400], fontSize: 11)),
                      const Spacer(),
                      Text('${(pct * 100).toStringAsFixed(0)}%',
                          style: TextStyle(color: isFull ? const Color(0xFF1DB954) : Colors.grey[500], fontSize: 11)),
                    ],
                  ),
                  const SizedBox(height: 4),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(2),
                    child: LinearProgressIndicator(
                      value: pct,
                      backgroundColor: const Color(0xFF2a2a2a),
                      valueColor: AlwaysStoppedAnimation<Color>(
                          isFull ? const Color(0xFF1DB954) : const Color(0xFF4a4a4a)),
                      minHeight: 4,
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

class _PlStats {
  final int total;
  final int matched;
  _PlStats(this.total, this.matched);
}

class _StatChip extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color? color;
  const _StatChip(this.label, this.value, this.icon, {this.color});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: color ?? Colors.grey),
        const SizedBox(width: 4),
        Text('$value ', style: TextStyle(color: color ?? Colors.white, fontWeight: FontWeight.bold, fontSize: 13)),
        Text(label, style: TextStyle(color: Colors.grey[500], fontSize: 12)),
      ],
    );
  }
}
