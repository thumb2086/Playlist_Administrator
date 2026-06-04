import 'dart:io';

class LogManager {
  static final LogManager _instance = LogManager._();
  static LogManager get instance => _instance;
  LogManager._();

  String? _logPath;
  int _maxFiles = 10;
  bool _enabled = false;

  void enable(String basePath, {int maxFiles = 10}) {
    _maxFiles = maxFiles;
    _enabled = true;
    final logDir = Directory('$basePath\\logs');
    logDir.createSync(recursive: true);
    final now = DateTime.now();
    final name = 'session_${now.year}${_p2(now.month)}${_p2(now.day)}_'
        '${_p2(now.hour)}${_p2(now.minute)}${_p2(now.second)}.log';
    _logPath = '${logDir.path}\\$name';
    _cleanup(logDir.path);
    info('--- 系統啟動 ---');
  }

  String _p2(int n) => n.toString().padLeft(2, '0');

  void _cleanup(String dirPath) {
    try {
      final dir = Directory(dirPath);
      final files = dir.listSync()
          .whereType<File>()
          .where((f) => f.path.endsWith('.log'))
          .toList()
        ..sort((a, b) => a.lastModifiedSync().compareTo(b.lastModifiedSync()));
      while (files.length >= _maxFiles) {
        files.removeAt(0).deleteSync();
      }
    } catch (_) {}
  }

  void info(String msg) => _write('INFO', msg);
  void error(String msg) => _write('ERROR', msg);

  void _write(String level, String msg) {
    if (!_enabled || _logPath == null) return;
    try {
      final now = DateTime.now();
      final line = '[${now.hour}:${_p2(now.minute)}:${_p2(now.second)}] [$level] $msg\n';
      File(_logPath!).writeAsStringSync(line, mode: FileMode.append);
    } catch (_) {}
  }
}
