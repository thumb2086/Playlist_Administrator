import 'dart:async';
import 'package:flutter/material.dart';
import '../services/config_service.dart';
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
  final _stepLabels = ['轉檔', '爬取', '清理', '分類', '元資料'];

  @override
  void dispose() { _scrollCtrl.dispose(); super.dispose(); }

  void _log(String msg) { _logs.add(msg); if (mounted) setState(() {}); _autoScroll(); }

  void _autoScroll() {
    Future.delayed(const Duration(milliseconds: 50), () {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(_scrollCtrl.position.maxScrollExtent,
            duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
      }
    });
  }

  Future<void> _run({int fromStep = 0}) async {
    if (_running) return;
    setState(() { _running = true; _progress = 0; _currentStep = fromStep; });
    _state = PipelineState();

    final orch = PipelineOrchestrator(
      config: ConfigService.instance.config,
      onLog: _log,
      onProgress: (c, t, s) {
        if (mounted) setState(() {
          _progress = t > 0 ? c / t : 0.0;
          final idx = _stepLabels.indexOf(s);
          if (idx >= 0) _currentStep = idx;
        });
      },
      state: _state,
    );
    await orch.run(fromStep: fromStep);
    if (mounted) setState(() => _running = false);
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
            _PButton('完整流程', Icons.play_arrow_rounded, () => _run(), _running, isPrimary: true),
            _PButton('只轉檔', Icons.transform, () => _run(fromStep: 0), _running),
            _PButton('只爬取', Icons.cloud_download, () => _run(fromStep: 1), _running),
            _PButton('只清理', Icons.cleaning_services, () => _run(fromStep: 2), _running),
            const Spacer(),
            if (_running) ...[
              _PButton('暫停', Icons.pause_rounded, () => _state.pause(), false, color: Colors.orange),
              _PButton('取消', Icons.stop_rounded, () => _state.cancel(), false, color: AppColors.error),
            ],
          ]),
          const SizedBox(height: 20),
          // Overall progress
          if (_running || _progress > 0) ...[
            TweenAnimationBuilder<double>(
              tween: Tween(begin: 0, end: _running ? _progress : 1.0),
              duration: const Duration(milliseconds: 500),
              curve: Curves.easeOutCubic,
              builder: (ctx, v, _) => Column(children: [
                ClipRRect(
                  borderRadius: BorderRadius.circular(4),
                  child: LinearProgressIndicator(
                    value: v, backgroundColor: AppColors.surfaceLight,
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
              ]),
            ),
          ],
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
                  ? const Center(child: Text('日誌將顯示在這裡', style: TextStyle(color: AppColors.textMuted, fontSize: 12)))
                  : ListView.builder(
                      controller: _scrollCtrl,
                      padding: const EdgeInsets.all(10),
                      itemCount: _logs.length,
                      itemBuilder: (ctx, i) {
                        final line = _logs[i];
                        Color? color;
                        if (line.contains('❌')) color = Colors.red[300];
                        else if (line.contains('✅') || line.contains('完成')) color = AppColors.accent;
                        else if (line.contains('---')) color = Colors.cyan[300];
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
