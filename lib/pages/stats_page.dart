import 'dart:io';
import 'dart:async';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../services/config_service.dart';

class StatsPage extends StatefulWidget {
  const StatsPage({super.key});
  @override
  State<StatsPage> createState() => _StatsPageState();
}

class _StatsPageState extends State<StatsPage> {
  int _mp3 = 0, _m4a = 0, _flac = 0;
  int _playlists = 0, _entries = 0;
  int _dualFormat = 0;
  double _totalSizeMb = 0;
  bool _loading = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    final lib = ConfigService.instance.config.libraryPath;
    final pl = ConfigService.instance.config.playlistsPath;

    try {
      int mp3 = 0, m4a = 0, flac = 0;
      double sizeMb = 0;
      final nameToExt = <String, Set<String>>{};

      if (await Directory(lib).exists()) {
        await for (final e in Directory(lib).list(recursive: true, followLinks: false)) {
          if (e is File) {
            final low = e.path.toLowerCase();
            final size = await e.length();
            sizeMb += size / (1024 * 1024);
            final stem = e.uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
            nameToExt.putIfAbsent(stem, () => {});

            if (low.endsWith('.mp3')) { mp3++; nameToExt[stem]!.add('mp3'); }
            else if (low.endsWith('.m4a')) { m4a++; nameToExt[stem]!.add('m4a'); }
            else if (low.endsWith('.flac')) { flac++; nameToExt[stem]!.add('flac'); }
          }
        }
      }

      int dual = 0;
      for (final exts in nameToExt.values) {
        if (exts.length > 1) dual++;
      }

      int plCount = 0, entries = 0;
      if (await Directory(pl).exists()) {
        await for (final e in Directory(pl).list()) {
          if (e is File && e.path.toLowerCase().endsWith('.m3u8')) {
            plCount++;
            entries += await File(e.path).readAsLines()
                .then((l) => l.where((line) => !line.startsWith('#') && line.trim().isNotEmpty).length);
          }
        }
      }

      setState(() {
        _mp3 = mp3; _m4a = m4a; _flac = flac;
        _playlists = plCount; _entries = entries;
        _dualFormat = dual; _totalSizeMb = sizeMb;
        _loading = false;
      });
    } catch (e) {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    final total = _mp3 + _m4a + _flac;

    return Padding(
      padding: const EdgeInsets.all(16),
      child: ListView(
        children: [
          // Summary cards
          Row(
            children: [
              Expanded(child: _Card('總檔案', '$total', Icons.audio_file, Colors.white)),
              const SizedBox(width: 8),
              Expanded(child: _Card('MP3', '$_mp3', Icons.music_note, Colors.blue)),
              const SizedBox(width: 8),
              Expanded(child: _Card('M4A', '$_m4a', Icons.music_video, Colors.orange)),
              const SizedBox(width: 8),
              Expanded(child: _Card('FLAC', '$_flac', Icons.library_music, Colors.purple)),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(child: _Card('容量', '${_totalSizeMb.toStringAsFixed(1)} GB', Icons.storage, const Color(0xFF1DB954))),
              const SizedBox(width: 8),
              Expanded(child: _Card('雙格式', '$_dualFormat', Icons.compare_arrows, Colors.teal)),
              const SizedBox(width: 8),
              Expanded(child: _Card('清單', '$_playlists', Icons.playlist_play, Colors.cyan)),
              const SizedBox(width: 8),
              Expanded(child: _Card('歌曲條目', '$_entries', Icons.list, Colors.amber)),
            ],
          ),
          const SizedBox(height: 24),
          // Pie chart
          if (total > 0) ...[
            const Text('格式分布', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 12),
            SizedBox(
              height: 200,
              child: PieChart(
                PieChartData(
                  sections: [
                    if (_mp3 > 0) PieChartSectionData(value: _mp3.toDouble(), color: Colors.blue, title: 'MP3', radius: 60),
                    if (_m4a > 0) PieChartSectionData(value: _m4a.toDouble(), color: Colors.orange, title: 'M4A', radius: 60),
                    if (_flac > 0) PieChartSectionData(value: _flac.toDouble(), color: Colors.purple, title: 'FLAC', radius: 60),
                  ],
                  centerSpaceRadius: 30,
                  sectionsSpace: 2,
                ),
              ),
            ),
          ],
          const SizedBox(height: 16),
          Center(
            child: ElevatedButton.icon(
              onPressed: _load,
              icon: const Icon(Icons.refresh),
              label: const Text('重新整理'),
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF1e1e1e)),
            ),
          ),
        ],
      ),
    );
  }
}

class _Card extends StatelessWidget {
  final String label;
  final String value;
  final IconData icon;
  final Color color;
  const _Card(this.label, this.value, this.icon, this.color);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF1e1e1e),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF2a2a2a)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(height: 8),
          Text(value, style: TextStyle(color: color, fontSize: 22, fontWeight: FontWeight.bold)),
          Text(label, style: TextStyle(color: Colors.grey[500], fontSize: 11)),
        ],
      ),
    );
  }
}
