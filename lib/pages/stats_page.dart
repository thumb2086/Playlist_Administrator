import 'dart:io';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../services/config_service.dart';
import '../services/i18n.dart';
import '../services/history_recorder.dart';
import '../widgets/dark_theme.dart';

class StatsPage extends StatefulWidget {
  const StatsPage({super.key});
  @override
  State<StatsPage> createState() => _StatsPageState();
}

class _StatsPageState extends State<StatsPage> {
  int _mp3 = 0, _m4a = 0, _flac = 0, _playlists = 0, _entries = 0, _dual = 0, _duplicates = 0;
  double _sizeGb = 0, _freeGb = 0;
  bool _loading = false;
  List<Snapshot> _history = [];

  @override
  void initState() {
    super.initState();
    I18N.instance.addListener(() { if (mounted) setState(() {}); });
    _history = HistoryRecorder.load();
    _load();
  }

  Future<void> _load() async {
    setState(() => _loading = true);
    try {
      final lib = ConfigService.instance.config.libraryPath;
      final pl = ConfigService.instance.config.playlistsPath;
      int mp3 = 0, m4a = 0, flac = 0;
      double size = 0;
      double freeGb = 0;
      final nameExts = <String, Set<String>>{};
      final nameCount = <String, int>{};  // stem -> total occurrences

      if (await Directory(lib).exists()) {
        await for (final e in Directory(lib).list(recursive: true, followLinks: false)) {
          if (e is File) {
            final low = e.path.toLowerCase();
            size += await e.length() / (1024 * 1024 * 1024);
            final stem = e.uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
            nameExts.putIfAbsent(stem, () => {});
            nameCount[stem] = (nameCount[stem] ?? 0) + 1;
            if (low.endsWith('.mp3')) { mp3++; nameExts[stem]!.add('mp3'); }
            else if (low.endsWith('.m4a')) { m4a++; nameExts[stem]!.add('m4a'); }
            else if (low.endsWith('.flac')) { flac++; nameExts[stem]!.add('flac'); }
          }
        }
      }

      // Get free disk space
      final drive = lib.length >= 2 ? lib.substring(0, 2) : 'C:';
      try {
        final ps = await Process.run('powershell', [
          '-NoProfile', '-NonInteractive', '-Command',
          '(Get-PSDrive -Name ${drive.substring(0, 1)}).Free'
        ]);
        if (ps.exitCode == 0) {
          freeGb = (double.tryParse(ps.stdout.toString().trim()) ?? 0) / (1024 * 1024 * 1024);
        }
      } catch (_) {}

      int dual = 0, duplicates = 0;
      for (final exts in nameExts.values) { if (exts.length > 1) dual++; }
      for (final cnt in nameCount.values) { if (cnt > 1) duplicates += cnt - 1; }

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
      setState(() { _mp3 = mp3; _m4a = m4a; _flac = flac; _playlists = plCount; _entries = entries; _dual = dual; _sizeGb = size; _freeGb = freeGb; _duplicates = duplicates; _loading = false; });
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
          Expanded(child: _MetricCard(t('stats.used'), '${_sizeGb.toStringAsFixed(1)} GB', Icons.storage_rounded, const Color(0xFFFFB74D), _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.free'), '${_freeGb.toStringAsFixed(1)} GB', Icons.space_dashboard_rounded, AppColors.accent, _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.dual_format'), '$_dual', Icons.compare_arrows_rounded, const Color(0xFF80CBC4), _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.duplicates'), '$_duplicates', Icons.copy_rounded, const Color(0xFFF06292), _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.playlists'), '$_playlists', Icons.playlist_play_rounded, const Color(0xFF81D4FA), _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.entries'), '$_entries', Icons.list_alt_rounded, const Color(0xFFFFF176), _loading)),
        ]),
        const SizedBox(height: 24),
        // History charts
        if (_history.length >= 2) ...[
          _ChartCard('總檔案數變化', total, _buildFileChart()),
          const SizedBox(height: 14),
          _ChartCard('歌曲完成度變化', _entries, _buildPlaylistChart()),
          const SizedBox(height: 14),
        ],
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
            onPressed: () async {
              await HistoryRecorder.record();
              setState(() => _history = HistoryRecorder.load());
              await _load();
            },
            icon: const Icon(Icons.refresh_rounded, size: 16),
            label: Text(t('stats.refresh')),
          ),
        ),
        const SizedBox(height: 24),
      ]),
    );
  }

  Widget _buildFileChart() {
    final spots = <FlSpot>[];
    double minY = double.infinity, maxY = 0;
    for (int i = 0; i < _history.length; i++) {
      final v = (_history[i].mp3 + _history[i].m4a + _history[i].flac).toDouble();
      spots.add(FlSpot(i.toDouble(), v));
      if (v < minY) minY = v; if (v > maxY) maxY = v;
    }
    final yRange = (maxY - minY).clamp(50, double.infinity);
    return LineChart(LineChartData(
      gridData: FlGridData(show: true, drawVerticalLine: false,
        getDrawingHorizontalLine: (_) => FlLine(color: AppColors.border.withValues(alpha: 0.2), strokeWidth: 1)),
      titlesData: FlTitlesData(
        leftTitles: AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 50,
          getTitlesWidget: (v, _) => Text('${v.toInt()}', style: const TextStyle(color: AppColors.textMuted, fontSize: 9)))),
        rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        bottomTitles: AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 20,
          getTitlesWidget: (v, _) {
            final idx = v.toInt();
            if (idx < 0 || idx >= _history.length) return const SizedBox();
            return Text('${_history[idx].time.month}/${_history[idx].time.day}',
                style: const TextStyle(color: AppColors.textMuted, fontSize: 9));
          })),
      ),
      borderData: FlBorderData(show: false),
      minY: (minY - yRange * 0.05).clamp(0, double.infinity),
      maxY: maxY + yRange * 0.05,
      lineBarsData: [
        LineChartBarData(spots: spots, isCurved: true,
          color: AppColors.accent, barWidth: 2,
          dotData: FlDotData(show: _history.length < 20,
            getDotPainter: (_, __, ___, ____) => FlDotCirclePainter(radius: 2, color: AppColors.accent)),
          belowBarData: BarAreaData(show: true, color: AppColors.accent.withValues(alpha: 0.1))),
      ],
    ));
  }

  Widget _buildPlaylistChart() {
    final colors = [AppColors.accent, const Color(0xFF4FC3F7), const Color(0xFFFFB74D),
                    const Color(0xFFCE93D8), const Color(0xFF80CBC4), const Color(0xFFF06292)];
    final plNames = <String>{};
    for (final s in _history) {
      plNames.addAll(s.playlistMatched.keys);
    }
    final plList = plNames.take(8).toList();

    return Row(children: [
      Expanded(flex: 3, child: LineChart(LineChartData(
        gridData: FlGridData(show: true, drawVerticalLine: false,
          getDrawingHorizontalLine: (_) => FlLine(color: AppColors.border.withValues(alpha: 0.2), strokeWidth: 1)),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 35,
            getTitlesWidget: (v, _) => Text('${v.toInt()}', style: const TextStyle(color: AppColors.textMuted, fontSize: 9)))),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          bottomTitles: AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 20,
            getTitlesWidget: (v, _) {
              final idx = v.toInt();
              if (idx < 0 || idx >= _history.length) return const SizedBox();
              return Text('${_history[idx].time.month}/${_history[idx].time.day}',
                  style: const TextStyle(color: AppColors.textMuted, fontSize: 9));
            })),
        ),
        borderData: FlBorderData(show: false),
        lineBarsData: plList.asMap().entries.map((entry) {
          final pi = entry.key;
          final name = entry.value;
          final spots = <FlSpot>[];
          for (int i = 0; i < _history.length; i++) {
            final matched = _history[i].playlistMatched[name] ?? 0;
            spots.add(FlSpot(i.toDouble(), matched.toDouble()));
          }
          return LineChartBarData(spots: spots, isCurved: true,
            color: colors[pi % colors.length], barWidth: 1.5,
            dotData: const FlDotData(show: false));
        }).toList(),
      ))),
      const SizedBox(width: 12),
      Expanded(flex: 2, child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start,
        children: plList.asMap().entries.map((e) => Padding(padding: const EdgeInsets.symmetric(vertical: 2),
          child: Row(children: [
            Container(width: 8, height: 8, decoration: BoxDecoration(color: colors[e.key % colors.length], shape: BoxShape.circle)),
            const SizedBox(width: 6),
            Expanded(child: Text(e.value, style: const TextStyle(color: AppColors.textSecondary, fontSize: 9), overflow: TextOverflow.ellipsis)),
          ]),
        )).toList(),
      )),
    ]);
  }
}

class _ChartCard extends StatelessWidget {
  final String title;
  final int currentValue;
  final Widget chart;
  const _ChartCard(this.title, this.currentValue, this.chart);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card, borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Text(title, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
          const Spacer(),
          Text('目前 $currentValue', style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
        ]),
        const SizedBox(height: 12),
        SizedBox(height: 140, child: chart),
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
