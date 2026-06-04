import 'dart:io';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../services/config_service.dart';
import '../services/i18n.dart';
import '../widgets/dark_theme.dart';

class StatsPage extends StatefulWidget {
  const StatsPage({super.key});
  @override
  State<StatsPage> createState() => _StatsPageState();
}

class _StatsPageState extends State<StatsPage> {
  int _mp3 = 0, _m4a = 0, _flac = 0, _playlists = 0, _entries = 0, _dual = 0;
  double _sizeGb = 0;
  bool _loading = false;

  @override
  void initState() { super.initState(); I18N.instance.addListener(() { if (mounted) setState(() {}); }); _load(); }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final lib = ConfigService.instance.config.libraryPath;
      final pl = ConfigService.instance.config.playlistsPath;
      int mp3 = 0, m4a = 0, flac = 0;
      double size = 0;
      final nameExts = <String, Set<String>>{};

      if (await Directory(lib).exists()) {
        await for (final e in Directory(lib).list(recursive: true, followLinks: false)) {
          if (e is File) {
            final low = e.path.toLowerCase();
            size += await e.length() / (1024 * 1024 * 1024);
            final stem = e.uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
            nameExts.putIfAbsent(stem, () => {});
            if (low.endsWith('.mp3')) { mp3++; nameExts[stem]!.add('mp3'); }
            else if (low.endsWith('.m4a')) { m4a++; nameExts[stem]!.add('m4a'); }
            else if (low.endsWith('.flac')) { flac++; nameExts[stem]!.add('flac'); }
          }
        }
      }

      int dual = 0;
      for (final exts in nameExts.values) { if (exts.length > 1) dual++; }

      int plCount = 0, entries = 0;
      if (await Directory(pl).exists()) {
        await for (final e in Directory(pl).list()) {
          if (e is File && e.path.toLowerCase().endsWith('.m3u8')) {
            plCount++;
            entries += await e.readAsLines()
                .then((l) => l.where((line) => !line.startsWith('#') && line.trim().isNotEmpty).length);
          }
        }
      }
      setState(() { _mp3 = mp3; _m4a = m4a; _flac = flac; _playlists = plCount; _entries = entries; _dual = dual; _sizeGb = size; _loading = false; });
    } catch (_) { setState(() => _loading = false); }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    final total = _mp3 + _m4a + _flac;

    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: ListView(children: [
        // Metric cards
        Row(children: [
          Expanded(child: _MetricCard(t('stats.total_files'), '$total', Icons.audio_file_rounded, Colors.white, _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.mp3'), '$_mp3', Icons.music_note_rounded, const Color(0xFF4FC3F7), _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.m4a'), '$_m4a', Icons.music_video_rounded, const Color(0xFFFFB74D), _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.flac'), '$_flac', Icons.library_music_rounded, const Color(0xFFCE93D8), _loading)),
        ]),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(child: _MetricCard(t('stats.storage'), '${_sizeGb.toStringAsFixed(1)} GB', Icons.storage_rounded, AppColors.accent, _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.dual_format'), '$_dual', Icons.compare_arrows_rounded, const Color(0xFF80CBC4), _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.playlists'), '$_playlists', Icons.playlist_play_rounded, const Color(0xFF81D4FA), _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.entries'), '$_entries', Icons.list_alt_rounded, const Color(0xFFFFF176), _loading)),
        ]),
        const SizedBox(height: 24),
        if (total > 0) ...[
          Text(t('stats.format_distribution'), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          const SizedBox(height: 12),
          Container(
            height: 220,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppColors.card, borderRadius: BorderRadius.circular(14),
              border: Border.all(color: AppColors.border),
            ),
            child: Row(children: [
              Expanded(
                child: PieChart(PieChartData(
                  sections: [
                    if (_mp3 > 0) PieChartSectionData(value: _mp3.toDouble(), color: const Color(0xFF4FC3F7), title: '', radius: 55),
                    if (_m4a > 0) PieChartSectionData(value: _m4a.toDouble(), color: const Color(0xFFFFB74D), title: '', radius: 55),
                    if (_flac > 0) PieChartSectionData(value: _flac.toDouble(), color: const Color(0xFFCE93D8), title: '', radius: 55),
                  ],
                  centerSpaceRadius: 35,
                  sectionsSpace: 3,
                )),
              ),
              const SizedBox(width: 20),
              Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
                _Legend('MP3', '$_mp3', const Color(0xFF4FC3F7)),
                const SizedBox(height: 8),
                _Legend('M4A', '$_m4a', const Color(0xFFFFB74D)),
                const SizedBox(height: 8),
                _Legend('FLAC', '$_flac', const Color(0xFFCE93D8)),
              ]),
            ]),
          ),
        ],
        const SizedBox(height: 16),
        Center(
          child: TextButton.icon(
            onPressed: _load,
            icon: const Icon(Icons.refresh_rounded, size: 16),
            label: Text(t('stats.refresh')),
          ),
        ),
        const SizedBox(height: 24),
      ]),
    );
  }
}

class _MetricCard extends StatelessWidget {
  final String label; final String value; final IconData icon; final Color color; final bool loading;
  const _MetricCard(this.label, this.value, this.icon, this.color, this.loading);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.card, borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, color: color, size: 20),
        const SizedBox(height: 10),
        Text(value, style: TextStyle(color: color, fontSize: 22, fontWeight: FontWeight.bold)),
        Text(label, style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
      ]),
    );
  }
}

class _Legend extends StatelessWidget {
  final String label; final String count; final Color color;
  const _Legend(this.label, this.count, this.color);

  @override
  Widget build(BuildContext context) {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Container(width: 10, height: 10, decoration: BoxDecoration(color: color, borderRadius: BorderRadius.circular(3))),
      const SizedBox(width: 6),
      Text('$label ', style: const TextStyle(fontSize: 12, color: AppColors.textSecondary)),
      Text(count, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
    ]);
  }
}
