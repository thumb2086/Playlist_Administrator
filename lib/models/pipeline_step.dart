enum PipelineStepStatus { pending, running, completed, failed, skipped }

class PipelineStepInfo {
  final String name;
  final double weight;
  PipelineStepStatus status;

  PipelineStepInfo({required this.name, required this.weight, this.status = PipelineStepStatus.pending});
}

class PipelineState {
  bool _paused = false;
  bool _cancelled = false;

  bool get isPaused => _paused;
  bool get isCancelled => _cancelled;

  void pause() => _paused = true;
  void resume() => _paused = false;
  void cancel() {
    _cancelled = true;
    _paused = false;
  }
  void reset() {
    _paused = false;
    _cancelled = false;
  }

  Future<void> waitIfPaused() async {
    while (_paused && !_cancelled) {
      await Future.delayed(const Duration(milliseconds: 200));
    }
  }
}
