import 'dart:async';
import 'package:flutter/material.dart';
import '../services/config_service.dart';
import '../pipeline/pipeline_orchestrator.dart';
import '../models/pipeline_step.dart';

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
  void dispose() {
    _scrollCtrl.dispose();
    super.dispose();
  }

  void _log(String msg) {
    _logs.add(msg);
    if (mounted) setState(() {});
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
          _currentStep = _stepLabels.indexOf(s);
          if (_currentStep < 0) _currentStep = 0;
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
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Control buttons
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              _Btn('完整流程', Icons.play_arrow, () => _run(), _running, const Color(0xFF1DB954)),
              _Btn('只轉檔', Icons.transform, () => _run(fromStep: 0), _running, const Color(0xFF2a2a2a)),
              _Btn('只爬取', Icons.cloud_download, () => _run(fromStep: 1), _running, const Color(0xFF2a2a2a)),
              _Btn('只清理', Icons.cleaning_services, () => _run(fromStep: 2), _running, const Color(0xFF2a2a2a)),
              if (_running) ...[
                _Btn('暫停', Icons.pause, () => _state.pause(), false, Colors.orange),
                _Btn('取消', Icons.stop, () => _state.cancel(), false, Colors.red[700]!),
              ],
            ],
          ),
          const SizedBox(height: 16),
          // Progress
          if (_running || _progress > 0) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: _progress,
                backgroundColor: const Color(0xFF2a2a2a),
                valueColor: const AlwaysStoppedAnimation(Color(0xFF1DB954)),
                minHeight: 8,
              ),
            ),
            const SizedBox(height: 6),
            Text('Step ${_currentStep + 1}/5: ${_stepLabels[_currentStep]}  (${(_progress * 100).toStringAsFixed(0)}%)',
                style: TextStyle(color: Colors.grey[400], fontSize: 12)),
          ],
          const SizedBox(height: 12),
          // Step indicators
          Row(
            children: List.generate(_stepLabels.length, (i) {
              final active = i == _currentStep && _running;
              final done = i < _currentStep;
              return Expanded(
                child: Container(
                  margin: const EdgeInsets.symmetric(horizontal: 2),
                  child: Column(
                    children: [
                      Container(
                        height: 4,
                        decoration: BoxDecoration(
                          color: done ? const Color(0xFF1DB954) : (active ? Colors.orange : const Color(0xFF2a2a2a)),
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(_stepLabels[i],
                          style: TextStyle(
                            color: done ? const Color(0xFF1DB954) : (active ? Colors.white : Colors.grey[600]),
                            fontSize: 10,
                          )),
                    ],
                  ),
                ),
              );
            }),
          ),
          const SizedBox(height: 12),
          // Log
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFF0d0d0d),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: const Color(0xFF2a2a2a)),
              ),
              child: ListView.builder(
                controller: _scrollCtrl,
                itemCount: _logs.length,
                itemBuilder: (ctx, i) {
                  final line = _logs[i];
                  Color? color;
                  if (line.contains('❌')) color = Colors.red[300];
                  else if (line.contains('✅') || line.contains('完成')) color = const Color(0xFF1DB954);
                  else if (line.contains('---')) color = Colors.cyan[300];
                  return Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
                    child: Text(line,
                        style: TextStyle(
                          fontSize: 12,
                          fontFamily: 'monospace',
                          color: color ?? const Color(0xFFb3b3b3),
                        )),
                  );
                },
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _Btn extends StatelessWidget {
  final String label;
  final IconData icon;
  final VoidCallback onPressed;
  final bool disabled;
  final Color color;
  const _Btn(this.label, this.icon, this.onPressed, this.disabled, this.color);

  @override
  Widget build(BuildContext context) {
    return ElevatedButton.icon(
      onPressed: disabled ? null : onPressed,
      icon: Icon(icon, size: 14),
      label: Text(label, style: const TextStyle(fontSize: 11)),
      style: ElevatedButton.styleFrom(
        backgroundColor: color,
        foregroundColor: Colors.white,
        disabledBackgroundColor: Colors.grey[800],
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        minimumSize: Size.zero,
      ),
    );
  }
}
