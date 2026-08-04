import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../services/config_service.dart';
import '../services/i18n.dart';
import '../services/chinese_converter.dart';
import '../services/history_recorder.dart';
import '../pipeline/pipeline_orchestrator.dart';
import '../pipeline/podcast_pipeline.dart';
import '../models/pipeline_step.dart';
import '../widgets/dark_theme.dart';

class PipelinePage extends StatefulWidget {
  const PipelinePage({super.key});
  @override
  State<PipelinePage> createState() => _PipelinePageState();
}

class _PipelinePageState extends State<PipelinePage> {
  final _musicLogs = <String>[];
  final _podcastLogs = <String>[];
  final _musicScrollCtrl = ScrollController();
  final _podcastScrollCtrl = ScrollController();
  PipelineState _musicState = PipelineState();
  PipelineState _podcastState = PipelineState();
  bool _musicRunning = false;
  bool _podcastRunning = false;
  double _musicProgress = 0;
  double _podcastProgress = 0;
  int _musicStep = 0;

  late List<String> _stepLabels;

  @override
  void initState() {
    super.initState();
    _rebuildStepLabels();
    I18N.instance.addListener(_rebuildStepLabels);
  }

  @override
  void dispose() {
    I18N.instance.removeListener(_rebuildStepLabels);
    _musicScrollCtrl.dispose();
    _podcastScrollCtrl.dispose();
    super.dispose();
  }

  void _rebuildStepLabels() {
    setState(() {
      _stepLabels = [
        t('pipeline.step_convert'),
        t('pipeline.step_scrape'),
        t('pipeline.step_prune'),
        t('pipeline.step_unsorted'),
        t('pipeline.step_metadata'),
        t('pipeline.step_lufs'),
        t('pipeline.step_srt'),
      ];
    });
  }

  void _musicLog(String msg) {
    if (mounted) setState(() { _musicLogs.add(msg); });
    _autoScroll(_musicScrollCtrl);
  }

  void _podcastLog(String msg) {
    if (mounted) setState(() { _podcastLogs.add(msg); });
    _autoScroll(_podcastScrollCtrl);
  }

  void _autoScroll(ScrollController ctrl) {
    Future.delayed(const Duration(milliseconds: 50), () {
      if (ctrl.hasClients) {
        ctrl.animateTo(ctrl.position.maxScrollExtent,
            duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
      }
    });
  }

  Future<void> _run({int fromStep = 0, int? toStep}) async {
    if (_musicRunning) return;
    setState(() { _musicRunning = true; _musicProgress = 0; _musicStep = fromStep; });
    _musicState = PipelineState();
    _musicLog(t('pipeline.starting'));
    await Future<void>.delayed(const Duration(milliseconds: 50));

    try {
      try { await ChineseConverter.instance.load(); } catch (e) { _musicLog('注意: 中文轉換器載入失敗: $e'); }

      final orch = PipelineOrchestrator(
        config: ConfigService.instance.config,
        onLog: _musicLog,
        onProgress: (c, t, stepIdx) {
          try { if (mounted) setState(() { _musicProgress = t > 0 ? c / t : 0.0; _musicStep = stepIdx; }); } catch (_) {}
        },
        state: _musicState,
      );
      await orch.run(fromStep: fromStep, toStep: toStep);
      HistoryRecorder.record().ignore();
    } catch (e) {
      _musicLog('  ❌ Pipeline 執行錯誤: $e');
    } finally {
      if (mounted) setState(() { _musicRunning = false; _musicProgress = 0; });
    }
  }

  Future<void> _runPodcast() async {
    if (_podcastRunning) return;
    setState(() { _podcastRunning = true; _podcastProgress = 0; });
    _podcastState = PipelineState();
    _podcastLog('Podcast Pipeline 啟動中…');
    await Future<void>.delayed(const Duration(milliseconds: 50));

    try {
      try { await ChineseConverter.instance.load(); } catch (e) { _podcastLog('注意: 中文轉換器載入失敗: $e'); }

      final pipeline = PodcastPipeline(
        onLog: _podcastLog,
        onProgress: (c, t, stepIdx) {
          try { if (mounted) setState(() { _podcastProgress = t > 0 ? c / t : 0.0; }); } catch (_) {}
        },
        state: _podcastState,
      );
      await pipeline.run();
    } catch (e) {
      _podcastLog('  ❌ Podcast Pipeline 錯誤: $e');
    } finally {
      if (mounted) setState(() { _podcastRunning = false; _podcastProgress = 0; });
    }
  }

  Widget _buildLogPanel({
    required List<String> logs,
    required ScrollController scrollCtrl,
    required String title,
    required Color accentColor,
    bool empty = false,
  }) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(bottom: 6),
              child: Text(title, style: TextStyle(
                color: accentColor, fontSize: 12, fontWeight: FontWeight.w600)),
          ),
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFF080808),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.border),
              ),
              clipBehavior: Clip.antiAlias,
              child: logs.isEmpty
                  ? Center(child: Text(empty ? '' : t('pipeline.log_placeholder'),
                      style: const TextStyle(color: AppColors.textMuted, fontSize: 12)))
                  : SelectionArea(child: ListView.builder(
                      controller: scrollCtrl,
                      padding: const EdgeInsets.all(10),
                      itemCount: logs.length,
                      itemBuilder: (ctx, i) {
                        final line = logs[i];
                        Color? color;
                        if (line.contains('❌')) { color = Colors.red[300]; }
                        else if (line.contains('✅') || line.contains('完成')) { color = accentColor; }
                        else if (line.contains('---')) { color = Colors.cyan[300]; }
                        return Padding(
                          padding: const EdgeInsets.symmetric(vertical: 1),
                          child: Text(line, style: TextStyle(fontSize: 11, fontFamily: 'Consolas',
                              color: color ?? AppColors.textMuted, height: 1.4)),
                        );
                      },
                    )),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final hasLogs = _musicLogs.isNotEmpty || _podcastLogs.isNotEmpty;

    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(spacing: 8, runSpacing: 8, children: [
            _PButton(t('pipeline.run_all'), Icons.play_arrow_rounded, () => _run(), _musicRunning, isPrimary: true),
            _PButton(t('pipeline.run_convert'), Icons.transform, () => _run(fromStep: 0, toStep: 1), _musicRunning),
            _PButton(t('pipeline.run_scrape'), Icons.cloud_download, () => _run(fromStep: 1, toStep: 2), _musicRunning),
            _PButton(t('pipeline.run_prune'), Icons.cleaning_services, () => _run(fromStep: 2, toStep: 3), _musicRunning),
            _PButton(t('pipeline.run_podcast'), Icons.podcasts, _runPodcast, _podcastRunning, color: const Color(0xFFCE93D8)),
            if (_musicRunning) ...[
              _PButton(t('pipeline.pause'), Icons.pause_rounded, () {
                _musicState.pause();
                _musicLog('Pipeline 已暫停');
                setState(() {});
              }, false, color: Colors.orange),
              _PButton(t('pipeline.cancel'), Icons.stop_rounded, () {
                _musicState.cancel();
                _musicLog('正在取消 Pipeline…');
                setState(() {});
              }, false, color: AppColors.error),
            ],
            if (_podcastRunning) ...[
              _PButton(t('pipeline.pause'), Icons.pause_rounded, () {
                _podcastState.pause();
                _podcastLog('Podcast Pipeline 已暫停');
                setState(() {});
              }, false, color: Colors.orange),
              _PButton(t('pipeline.cancel'), Icons.stop_rounded, () {
                _podcastState.cancel();
                _podcastLog('正在取消 Podcast Pipeline…');
                setState(() {});
              }, false, color: AppColors.error),
            ],
            if (hasLogs) ...[
              _PButton(t('pipeline.clear_log'), Icons.delete_outline_rounded, () {
                _musicLogs.clear();
                _podcastLogs.clear();
                setState(() {});
              }, false, color: AppColors.textMuted),
              if (_musicLogs.isNotEmpty)
                _PButton('複製音樂', Icons.copy_rounded, () {
                  Clipboard.setData(ClipboardData(text: _musicLogs.join('\n')));
                  if (mounted) {
                    setState(() {});
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('已複製'), duration: Duration(seconds: 1)),
                    );
                  }
                }, false, color: AppColors.textSecondary),
              if (_podcastLogs.isNotEmpty)
                _PButton('複製 Podcast', Icons.copy_rounded, () {
                  Clipboard.setData(ClipboardData(text: _podcastLogs.join('\n')));
                  if (mounted) {
                    setState(() {});
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('已複製'), duration: Duration(seconds: 1)),
                    );
                  }
                }, false, color: AppColors.textSecondary),
            ],
          ]),
          const SizedBox(height: 20),
          AnimatedSize(duration: const Duration(milliseconds: 300), curve: Curves.easeOut,
            child: (_musicRunning || _musicProgress > 0 || _podcastRunning || _podcastProgress > 0)
                ? Column(children: [
                    if (_musicRunning || _musicProgress > 0) ...[
                      ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: LinearProgressIndicator(
                          value: _musicProgress, backgroundColor: AppColors.surfaceLight,
                          valueColor: const AlwaysStoppedAnimation(AppColors.accent), minHeight: 7,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Row(children: [
                        Text('${_stepLabels[_musicStep]}  (${(_musicProgress * 100).toStringAsFixed(0)}%)',
                            style: const TextStyle(color: AppColors.textSecondary, fontSize: 12)),
                        const Spacer(),
                        if (_musicRunning)
                          const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2)),
                      ]),
                      const SizedBox(height: 16),
                    ],
                    if (_podcastRunning || _podcastProgress > 0) ...[
                      ClipRRect(
                        borderRadius: BorderRadius.circular(4),
                        child: LinearProgressIndicator(
                          value: _podcastProgress, backgroundColor: AppColors.surfaceLight,
                          valueColor: const AlwaysStoppedAnimation(Color(0xFFCE93D8)), minHeight: 7,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Row(children: [
                        Text('Podcast  (${(_podcastProgress * 100).toStringAsFixed(0)}%)',
                            style: const TextStyle(color: AppColors.textSecondary, fontSize: 12)),
                        const Spacer(),
                        if (_podcastRunning)
                          const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2)),
                      ]),
                    ],
                  ])
                : const SizedBox.shrink(),
          ),
          if (_musicRunning || _musicProgress > 0 || _podcastRunning || _podcastProgress > 0) const SizedBox(height: 16),
          if (_musicRunning || _musicProgress > 0)
            Row(
              children: List.generate(_stepLabels.length, (i) {
                final active = i == _musicStep && _musicRunning;
                final done = i < _musicStep;
                return Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 3),
                    child: Column(children: [
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 300),
                        height: 5,
                        decoration: BoxDecoration(
                          color: done ? AppColors.accent : (active ? AppColors.accent.withValues(alpha: 0.6) : AppColors.surfaceLight),
                          borderRadius: BorderRadius.circular(3),
                        ),
                      ),
                      const SizedBox(height: 5),
                      Text(_stepLabels[i], style: TextStyle(
                        color: done ? AppColors.accent : (active ? AppColors.text : AppColors.textMuted),
                        fontSize: 10, fontWeight: done || active ? FontWeight.w600 : FontWeight.normal,
                      )),
                    ]),
                  ),
                );
              }),
            ),
          if (_podcastRunning)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Text('Podcast Pipeline 執行中…',
                  style: const TextStyle(color: AppColors.accent, fontSize: 12, fontWeight: FontWeight.w600)),
            ),
          const SizedBox(height: 16),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _buildLogPanel(
                  logs: _musicLogs, scrollCtrl: _musicScrollCtrl,
                  title: '🎵 音樂 Pipeline', accentColor: AppColors.accent,
                ),
                const SizedBox(width: 12),
                _buildLogPanel(
                  logs: _podcastLogs, scrollCtrl: _podcastScrollCtrl,
                  title: '🎙️ Podcast Pipeline', accentColor: const Color(0xFFCE93D8),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],
      ),
    );
  }
}

class _PButton extends StatelessWidget {
  final String label; final IconData icon; final VoidCallback onPressed;
  final bool disabled; final bool isPrimary; final Color? color;
  const _PButton(this.label, this.icon, this.onPressed, this.disabled,
      {this.isPrimary = false, this.color});

  @override
  Widget build(BuildContext context) {
    return ElevatedButton.icon(
      onPressed: disabled ? null : onPressed,
      icon: Icon(icon, size: 15),
      label: Text(label, style: const TextStyle(fontSize: 12)),
      style: ElevatedButton.styleFrom(
        backgroundColor: color ?? (isPrimary ? AppColors.accent : AppColors.surfaceLight),
        foregroundColor: isPrimary ? Colors.black : AppColors.text,
        disabledBackgroundColor: AppColors.surfaceLight.withValues(alpha: 0.5),
        disabledForegroundColor: AppColors.textMuted,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      ),
    );
  }
}
