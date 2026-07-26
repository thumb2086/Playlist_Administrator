import 'dart:convert';
import 'dart:io';
import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../services/config_service.dart';
import '../services/groq_service.dart';
import '../services/i18n.dart';
import '../services/history_recorder.dart';
import '../widgets/dark_theme.dart';

class StatsPage extends StatefulWidget {
  const StatsPage({super.key});
  @override
  State<StatsPage> createState() => _StatsPageState();
}

class _StatsPageState extends State<StatsPage> {
  int _mp3 = 0, _m4a = 0, _flac = 0, _txt = 0, _podcast = 0, _playlists = 0, _entries = 0, _dual = 0, _duplicates = 0;
  double _sizeGb = 0, _savedGb = 0;
  bool _loading = false;
  List<Snapshot> _history = [];
  List<double> _m4aLufs = [], _mp3Lufs = [];
  bool _lufsReady = false;

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
      int mp3 = 0, m4a = 0, flac = 0, txt = 0, podcast = 0;

      final podcastDir = Directory('${ConfigService.instance.config.basePath}\\podcast_downloads');
      if (await podcastDir.exists()) {
        await for (final e in podcastDir.list(recursive: true, followLinks: false)) {
          if (e is File) {
            final low = e.path.toLowerCase();
            if (low.endsWith('.mp3') || low.endsWith('.m4a') || low.endsWith('.wav') || low.endsWith('.flac')) podcast++;
            else if (low.endsWith('.txt')) txt++;
          }
        }
      }
      double size = 0, savedGb = 0;
      final nameExts = <String, Set<String>>{};
      final nameCount = <String, int>{};  // stem -> total occurrences
      final firstSize = <String, double>{};  // stem -> size of first occurrence

      if (await Directory(lib).exists()) {
        await for (final e in Directory(lib).list(recursive: true, followLinks: false)) {
          if (e is File) {
            final low = e.path.toLowerCase();
            final lenGb = await e.length() / (1024 * 1024 * 1024);
            size += lenGb;
            final stem = e.uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
            nameExts.putIfAbsent(stem, () => {});
            final cnt = nameCount[stem] ?? 0;
            nameCount[stem] = cnt + 1;
            // First occurrence: record size; subsequent: add to saved
            if (cnt == 0) {
              firstSize[stem] = lenGb;
            } else {
              savedGb += lenGb;
            }
            if (low.endsWith('.mp3')) { mp3++; nameExts[stem]!.add('mp3'); }
            else if (low.endsWith('.m4a')) { m4a++; nameExts[stem]!.add('m4a'); }
            else if (low.endsWith('.flac')) { flac++; nameExts[stem]!.add('flac'); }
            else if (low.endsWith('.txt')) { txt++; nameExts[stem]!.add('txt'); }
          }
        }
      }

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
      setState(() { _mp3 = mp3; _m4a = m4a; _flac = flac; _txt = txt; _podcast = podcast; _playlists = plCount; _entries = entries; _dual = dual; _sizeGb = size; _savedGb = savedGb; _duplicates = duplicates; _loading = false; });
    } catch (_) { setState(() => _loading = false); }
    _loadLufsCache();
  }

  Future<void> _loadLufsCache() async {
    final base = ConfigService.instance.config.basePath;
    List<double> loadOne(String name) {
      try {
        final f = File('$base\\${name}_lufs_cache.json');
        if (!f.existsSync()) return [];
        final json = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
        return json.values.whereType<num>().map((e) => e.toDouble()).toList();
      } catch (_) { return []; }
    }
    final m4a = loadOne('m4a');
    final mp3 = loadOne('mp3');
    if (mounted) setState(() { _m4aLufs = m4a; _mp3Lufs = mp3; _lufsReady = true; });
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    final total = _mp3 + _m4a + _flac + _txt;

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
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.txt'), '$_txt', Icons.description_outlined, const Color(0xFFA5D6A7), _loading)),
        ]),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(child: _MetricCard(t('stats.storage'), '${_sizeGb.toStringAsFixed(1)} GB', Icons.storage_rounded, AppColors.accent, _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.saved'), '${_savedGb.toStringAsFixed(1)} GB', Icons.save_alt_rounded, const Color(0xFF4FC3F7), _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.dual_format'), '$_dual', Icons.compare_arrows_rounded, const Color(0xFF80CBC4), _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.duplicates'), '$_duplicates', Icons.copy_rounded, const Color(0xFFF06292), _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.playlists'), '$_playlists', Icons.playlist_play_rounded, const Color(0xFF81D4FA), _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.entries'), '$_entries', Icons.list_alt_rounded, const Color(0xFFFFF176), _loading)),
          const SizedBox(width: 10),
          Expanded(child: _MetricCard(t('stats.podcast'), '$_podcast', Icons.podcasts, const Color(0xFFEF5350), _loading)),
        ]),
        const SizedBox(height: 24),
        // History charts
        if (_history.length >= 2) ...[
          _ChartCard('總檔案數變化', total, _buildFileChart()),
          const SizedBox(height: 14),
          _ChartCard('歌曲完成度變化', _entries, _buildPlaylistChart()),
          const SizedBox(height: 14),
        ],
        _buildGroqRpmChart(),
        const SizedBox(height: 14),
        if (total > 0) ...[
          Text(t('stats.format_distribution'), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: AppColors.card, borderRadius: BorderRadius.circular(14),
              border: Border.all(color: AppColors.border),
            ),
            child: Column(children: [
              Row(children: [
                Expanded(
                  flex: 3,
                  child: SizedBox(
                    height: 180,
                    child: PieChart(PieChartData(
                      sections: [
                        if (_mp3 > 0) PieChartSectionData(value: _mp3.toDouble(), color: const Color(0xFF4FC3F7), title: '', radius: 50),
                        if (_m4a > 0) PieChartSectionData(value: _m4a.toDouble(), color: const Color(0xFFFFB74D), title: '', radius: 50),
                        if (_flac > 0) PieChartSectionData(value: _flac.toDouble(), color: const Color(0xFFCE93D8), title: '', radius: 50),
                        if (_txt > 0) PieChartSectionData(value: _txt.toDouble(), color: const Color(0xFFA5D6A7), title: '', radius: 50),
                      ],
                      centerSpaceRadius: 30,
                      sectionsSpace: 3,
                    )),
                  ),
                ),
                const SizedBox(width: 20),
                Expanded(
                  flex: 2,
                  child: Column(mainAxisAlignment: MainAxisAlignment.center, crossAxisAlignment: CrossAxisAlignment.start, children: [
                    _Legend('MP3', '$_mp3', const Color(0xFF4FC3F7)),
                    const SizedBox(height: 6),
                    _Legend('M4A', '$_m4a', const Color(0xFFFFB74D)),
                    const SizedBox(height: 6),
                    _Legend('FLAC', '$_flac', const Color(0xFFCE93D8)),
                    const SizedBox(height: 6),
                    _Legend('TXT', '$_txt', const Color(0xFFA5D6A7)),
                  ]),
                ),
              ]),
              if (_txt > 0 || _mp3 > 0 || _m4a > 0 || _flac > 0) ...[
                const Divider(height: 24),
                _buildTextDistribution(),
                if (_lufsReady) ...[
                  if (_mp3Lufs.isNotEmpty) _buildLufsSection('MP3', _mp3Lufs),
                  if (_m4aLufs.isNotEmpty) _buildLufsSection('M4A', _m4aLufs),
                ],
              ],
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

  Widget _buildTextDistribution() {
    final items = <MapEntry<String, int>>[];
    if (_mp3 > 0) items.add(MapEntry('MP3', _mp3));
    if (_m4a > 0) items.add(MapEntry('M4A', _m4a));
    if (_flac > 0) items.add(MapEntry('FLAC', _flac));
    if (_txt > 0) items.add(MapEntry('TXT', _txt));
    final totalItems = items.fold(0, (sum, e) => sum + e.value);

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF080808),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text('📄 ${t('stats.format_breakdown')}',
            style: const TextStyle(color: AppColors.textSecondary, fontSize: 11, fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        ...items.map((e) {
          final pct = totalItems > 0 ? (e.value / totalItems * 100) : 0.0;
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 2),
            child: Row(children: [
              SizedBox(
                width: 40,
                child: Text(e.key, style: const TextStyle(color: AppColors.textMuted, fontSize: 10, fontFamily: 'Consolas')),
              ),
              SizedBox(
                width: 50,
                child: Text('${e.value}', style: const TextStyle(color: AppColors.text, fontSize: 10, fontFamily: 'Consolas')),
              ),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(2),
                  child: LinearProgressIndicator(
                    value: pct / 100,
                    backgroundColor: AppColors.surfaceLight,
                    valueColor: AlwaysStoppedAnimation(_colorForFormat(e.key)),
                    minHeight: 8,
                  ),
                ),
              ),
              SizedBox(
                width: 45,
                child: Text('${pct.toStringAsFixed(1)}%',
                    style: const TextStyle(color: AppColors.textMuted, fontSize: 10, fontFamily: 'Consolas'), textAlign: TextAlign.right),
              ),
            ]),
          );
        }),
        const SizedBox(height: 4),
        Text('${t('stats.total_files')}: $totalItems',
            style: const TextStyle(color: AppColors.textMuted, fontSize: 10, fontFamily: 'Consolas')),
      ]),
    );
  }

  Color _colorForFormat(String fmt) {
    switch (fmt) {
      case 'MP3': return const Color(0xFF4FC3F7);
      case 'M4A': return const Color(0xFFFFB74D);
      case 'FLAC': return const Color(0xFFCE93D8);
      case 'TXT': return const Color(0xFFA5D6A7);
      default: return AppColors.textMuted;
    }
  }

  Widget _buildLufsSection(String label, List<double> values) {
    if (values.isEmpty) return const SizedBox.shrink();
    final sorted = List<double>.from(values)..sort();
    final avg = sorted.reduce((a, b) => a + b) / values.length;
    final minV = sorted.first;
    final maxV = sorted.last;
    final p10 = sorted[(values.length * 0.1).toInt()];
    final p90 = sorted[(values.length * 0.9).clamp(0, values.length - 1).toInt()];
    final accent = label == 'MP3' ? const Color(0xFF4FC3F7) : const Color(0xFFFFB74D);

    // Narrower buckets centered around -14 for better distribution visibility
    final ranges = [const [-35.0, -16.0], const [-16.0, -15.5], const [-15.5, -15.0],
                    const [-15.0, -14.5], const [-14.5, -14.0], const [-14.0, -13.5],
                    const [-13.5, -13.0], const [-13.0, -12.5], const [-12.5, -12.0],
                    const [-12.0, -11.5], const [-11.5, -11.0], const [-11.0, -10.5],
                    const [-10.5, -10.0], const [-10.0, 0.0]];
    final labels = ['-16', '-15.5', '-15', '-14.5', '-14', '-13.5', '-13', '-12.5',
                    '-12', '-11.5', '-11', '-10.5', '-10', '-9'];
    final buckets = List<int>.filled(ranges.length, 0);
    for (final v in values) {
      bool found = false;
      for (int i = 0; i < ranges.length; i++) {
        if (v >= ranges[i][0] && v < ranges[i][1]) { buckets[i]++; found = true; break; }
      }
      if (!found) buckets[ranges.length - 1]++;
    }
    final maxCount = buckets.reduce((a, b) => a > b ? a : b);
    final peakIdx = buckets.indexOf(maxCount);

    return Padding(padding: const EdgeInsets.only(top: 16),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(color: AppColors.card, borderRadius: BorderRadius.circular(14), border: Border.all(color: AppColors.border)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Text('$label LUFS 分佈 (${values.length} 個檔案)', style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
          ]),
          const SizedBox(height: 2),
          Text('平均 ${avg.toStringAsFixed(1)}  |  ${p10.toStringAsFixed(1)} ~ ${p90.toStringAsFixed(1)} (P10-P90)  |  ${minV.toStringAsFixed(1)} ~ ${maxV.toStringAsFixed(1)}',
            style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
          const SizedBox(height: 10),
          SizedBox(
            height: 200,
            child: BarChart(BarChartData(
              alignment: BarChartAlignment.spaceEvenly,
              maxY: (maxCount * 1.15).ceilToDouble(),
              groupsSpace: 2,
              baselineY: 0,
              barTouchData: BarTouchData(enabled: true,
                touchTooltipData: BarTouchTooltipData(
                  tooltipPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  getTooltipItem: (group, i, v, d) {
                    final pct = (buckets[group.x.toInt()] / values.length * 100).toStringAsFixed(1);
                    return BarTooltipItem('${labels[group.x.toInt()]}\n${buckets[group.x.toInt()]} 個 ($pct%)',
                      TextStyle(color: Colors.white, fontSize: 13, height: 1.5));
                  })),
              titlesData: FlTitlesData(
                leftTitles: AxisTitles(sideTitles: SideTitles(
                  showTitles: true, reservedSize: 32,
                  getTitlesWidget: (v, _) {
                    if (v == 0) return const SizedBox.shrink();
                    return Text('${v.toInt()}', style: const TextStyle(fontSize: 12, color: AppColors.textMuted));
                  })),
                rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                bottomTitles: AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 16,
                  getTitlesWidget: (v, _) {
                    final i = v.toInt();
                    if (i < 0 || i >= labels.length) return const SizedBox.shrink();
                    if (i > 0 && i < labels.length - 1 && i % 2 != 0) return const SizedBox(width: 0);
                    return Text(labels[i], style: TextStyle(
                      fontSize: 10, color: i == peakIdx ? accent : AppColors.textMuted,
                      fontWeight: i == peakIdx ? FontWeight.bold : FontWeight.normal));
                  })),
              ),
              gridData: FlGridData(show: true, drawVerticalLine: false,
                getDrawingHorizontalLine: (v) => FlLine(
                  color: v == 0 ? AppColors.border : AppColors.border.withValues(alpha: 0.12),
                  strokeWidth: v == 0 ? 1.0 : 0.5)),
              borderData: FlBorderData(show: false),
              extraLinesData: label == 'MP3' ? ExtraLinesData(horizontalLines: [
                HorizontalLine(y: 14, color: Colors.white.withValues(alpha: 0.3),
                  strokeWidth: 1, dashArray: [4, 4]),
              ]) : null,
              barGroups: List.generate(ranges.length, (i) =>
                BarChartGroupData(x: i, barRods: [
                  BarChartRodData(toY: buckets[i].toDouble(),
                    color: i == peakIdx ? accent : accent.withValues(alpha: 0.55),
                    width: 32,
                    borderRadius: const BorderRadius.vertical(top: Radius.circular(4))),
                ]),
              ),
            )),
          ),
        ]),
      ),
    );
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

  Widget _buildGroqRpmChart() {
    final rpm = GroqService.instance.rpmHistory;
    final maxRpm = rpm.fold<int>(0, (m, e) => e[1] > m ? e[1] : m);
    return _ChartCard('Groq RPM (最近60分鐘)', maxRpm, SizedBox(
      height: 140,
      child: maxRpm == 0 ? const Center(child: Text('尚無 Groq 呼叫紀錄', style: TextStyle(color: AppColors.textMuted, fontSize: 11)))
      : LineChart(LineChartData(
        gridData: FlGridData(show: true, drawVerticalLine: false,
          horizontalInterval: (maxRpm > 4 ? (maxRpm / 4).ceilToDouble() : 1)),
        titlesData: FlTitlesData(leftTitles: AxisTitles(sideTitles: SideTitles(showTitles: true, reservedSize: 24, getTitlesWidget: (v, _) => Text('${v.toInt()}', style: const TextStyle(fontSize: 8, color: AppColors.textMuted)))),
          bottomTitles: AxisTitles(sideTitles: SideTitles(showTitles: true, interval: 10, getTitlesWidget: (v, _) => Text('${-60 + v.toInt()}', style: const TextStyle(fontSize: 8, color: AppColors.textMuted)))),
          topTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: AxisTitles(sideTitles: SideTitles(showTitles: false))),
        borderData: FlBorderData(show: false),
        lineBarsData: [LineChartBarData(spots: rpm.map((e) => FlSpot(e[0].toDouble(), e[1].toDouble())).toList(),
          isCurved: true, color: AppColors.accent, barWidth: 2, dotData: FlDotData(show: false),
          belowBarData: BarAreaData(show: true, color: AppColors.accent.withValues(alpha: 0.15)))],
        minY: 0,
      )),
    ));
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
