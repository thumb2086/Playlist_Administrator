import 'dart:async';
import 'package:flutter/material.dart';
import '../services/config_service.dart';
import '../services/i18n.dart';
import '../services/chinese_converter.dart';
import '../pipeline/pipeline_orchestrator.dart';
import '../models/pipeline_step.dart';
import '../widgets/dark_theme.dart';

class PipelinePage extends StatefulWidget {
  const PipelinePage({super.key});
  @override
  State<PipelinePage> createState() => _PipelinePageState();
}

class _PipelinePageState extends State<PipelinePage> {
  final _logs = <String>[];
  final _scrollCtrl = ScrollController();
  PipelineState _state = PipelineState();
  bool _running = false;
  double _progress = 0;
  int _currentStep = 0;

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
    _scrollCtrl.dispose();
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
      ];
    });
  }

  void _log(String msg) { _logs.add(msg); if (mounted) setState(() {}); _autoScroll(); }

  void _autoScroll() {
    Future.delayed(const Duration(milliseconds: 50), () {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(_scrollCtrl.position.maxScrollExtent,
            duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
      }
    });
  }

  Future<void> _run({int fromStep = 0, int? toStep}) async {
    if (_running) return;
    setState(() { _running = true; _progress = 0; _currentStep = fromStep; });
    _state = PipelineState();
    _log(t('pipeline.starting'));
    await Future<void>.delayed(const Duration(milliseconds: 50));

    try {
      try {
        await ChineseConverter.instance.load();
      } catch (e) {
        _log('注意: 中文轉換器載入失敗: $e');
      }

      final orch = PipelineOrchestrator(
        config: ConfigService.instance.config,
        onLog: _log,
        onProgress: (c, t, stepIdx) {
          try {
            if (mounted) setState(() {
              _progress = t > 0 ? c / t : 0.0;
              _currentStep = stepIdx;
            });
          } catch (_) {}
        },
        state: _state,
      );
      await orch.run(fromStep: fromStep, toStep: toStep);
    } catch (e) {
      _log('  ❌ Pipeline 執行錯誤: $e');
    } finally {
      if (mounted) setState(() { _running = false; _progress = 0; });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Controls
          Wrap(spacing: 8, runSpacing: 8, children: [
            _PButton(t('pipeline.run_all'), Icons.play_arrow_rounded, () => _run(), _running, isPrimary: true),
            _PButton(t('pipeline.run_convert'), Icons.transform, () => _run(fromStep: 0, toStep: 1), _running),
            _PButton(t('pipeline.run_scrape'), Icons.cloud_download, () => _run(fromStep: 1, toStep: 2), _running),
            _PButton(t('pipeline.run_prune'), Icons.cleaning_services, () => _run(fromStep: 2, toStep: 3), _running),
            if (_running) ...[
              _PButton(t('pipeline.pause'), Icons.pause_rounded, () {
                _state.pause();
                _log('Pipeline 已暫停');
                setState(() {});
              }, false, color: Colors.orange),
              _PButton(t('pipeline.cancel'), Icons.stop_rounded, () {
                _state.cancel();
                _log('正在取消 Pipeline…');
                setState(() {});
              }, false, color: AppColors.error),
            ],
          ]),
          const SizedBox(height: 20),
          // Overall progress
          AnimatedSize(duration: const Duration(milliseconds: 300), curve: Curves.easeOut,
            child: (_running || _progress > 0) ? Column(children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: _progress, backgroundColor: AppColors.surfaceLight,
                  valueColor: const AlwaysStoppedAnimation(AppColors.accent), minHeight: 7,
                ),
              ),
              const SizedBox(height: 8),
              Row(children: [
                Text('${_stepLabels[_currentStep]}  (${(_progress * 100).toStringAsFixed(0)}%)',
                    style: const TextStyle(color: AppColors.textSecondary, fontSize: 12)),
                const Spacer(),
                if (_running)
                  const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2)),
              ]),
            ]) : const SizedBox.shrink(),
          ),
          if (_running || _progress > 0) const SizedBox(height: 16),
          // Step indicators
          Row(
            children: List.generate(_stepLabels.length, (i) {
              final active = i == _currentStep && _running;
              final done = i < _currentStep;
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
          const SizedBox(height: 16),
          // Log
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFF080808),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: AppColors.border),
              ),
              clipBehavior: Clip.antiAlias,
              child: _logs.isEmpty
                  ? Center(child: Text(t('pipeline.log_placeholder'), style: const TextStyle(color: AppColors.textMuted, fontSize: 12)))
                  : ListView.builder(
                      controller: _scrollCtrl,
                      padding: const EdgeInsets.all(10),
                      itemCount: _logs.length,
                      itemBuilder: (ctx, i) {
                        final line = _logs[i];
                        Color? color;
                        if (line.contains('❌')) { color = Colors.red[300]; }
                        else if (line.contains('✅') || line.contains('完成')) { color = AppColors.accent; }
                        else if (line.contains('---')) { color = Colors.cyan[300]; }
                        return Padding(
                          padding: const EdgeInsets.symmetric(vertical: 1),
                          child: Text(line, style: TextStyle(fontSize: 11, fontFamily: 'Consolas',
                              color: color ?? AppColors.textMuted, height: 1.4)),
                        );
                      },
                    ),
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
