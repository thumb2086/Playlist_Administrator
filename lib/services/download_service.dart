import 'dart:convert';
import 'dart:io';
import 'config_service.dart';

class DownloadService {
  static DownloadService? _instance;
  static DownloadService get instance => _instance ??= DownloadService._();
  DownloadService._();

  String get _pythonPath => 'python';

  String get _bridgePath {
    final exeDir = Directory(File(Platform.resolvedExecutable).parent.path);
    Directory? d = exeDir;
    while (d != null) {
      final candidate = '${d.path}\\tools\\flutter_download_bridge.py';
      if (File(candidate).existsSync()) return candidate;
      final parent = d.parent;
      d = parent.path == d.path ? null : parent;
    }
    return '';
  }

  Future<void> downloadSong({
    required String songName,
    required String libraryPath,
    String format = 'mp3',
    required void Function(String log) onLog,
    required void Function(double progress) onProgress,
  }) async {
    final bridge = _bridgePath;
    if (bridge.isEmpty) throw Exception('Base path not configured');

    final env = Map<String, String>.from(Platform.environment);
    env['PYTHONIOENCODING'] = 'utf-8';
    final proc = await Process.start(
      _pythonPath,
      [bridge, 'download-song', songName, libraryPath, format],
      runInShell: true,
      workingDirectory: ConfigService.instance.config.basePath,
      environment: env,
    );

    proc.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen(
      (line) {
        if (line.trim().isEmpty) return;
        try {
          final json = jsonDecode(line.trim()) as Map<String, dynamic>;
          final type = json['type'] as String?;
          if (type == 'log') {
            onLog(json['message'] as String? ?? '');
          } else if (type == 'progress') {
            final pct = (json['percent'] as num?)?.toDouble() ?? 0;
            onProgress(pct / 100);
          } else if (type == 'complete') {
            onLog('✅ 下載完成: ${json['path']}');
            onProgress(1.0);
          } else if (type == 'error') {
            onLog('❌ ${json['message']}');
            throw Exception(json['message'] as String? ?? 'Download failed');
          }
        } catch (e) {
          onLog(line);
        }
      },
    );

    final exitCode = await proc.exitCode;
    if (exitCode != 0) {
      onLog('❌ Python 程序異常退出 (code: $exitCode)');
    }
  }

  Future<void> downloadYouTube({
    required String url,
    required String outputPath,
    String format = 'mp3',
    required void Function(String log) onLog,
    required void Function(double progress) onProgress,
  }) async {
    final bridge = _bridgePath;
    if (bridge.isEmpty) throw Exception('Base path not configured');

    final env = Map<String, String>.from(Platform.environment);
    env['PYTHONIOENCODING'] = 'utf-8';
    final proc = await Process.start(
      _pythonPath,
      [bridge, 'download-youtube', url, outputPath, format],
      runInShell: true,
      workingDirectory: ConfigService.instance.config.basePath,
      environment: env,
    );

    proc.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen(
      (line) {
        if (line.trim().isEmpty) return;
        try {
          final json = jsonDecode(line.trim()) as Map<String, dynamic>;
          final type = json['type'] as String?;
          if (type == 'log') {
            onLog(json['message'] as String? ?? '');
          } else if (type == 'progress') {
            final pct = (json['percent'] as num?)?.toDouble() ?? 0;
            onProgress(pct / 100);
          } else if (type == 'complete') {
            onLog('✅ 下載完成: ${json['path']}');
            onProgress(1.0);
          } else if (type == 'error') {
            onLog('❌ ${json['message']}');
            throw Exception(json['message'] as String? ?? 'Download failed');
          }
        } catch (e) {
          onLog(line);
        }
      },
    );

    final exitCode = await proc.exitCode;
    if (exitCode != 0) {
      onLog('❌ Python 程序異常退出 (code: $exitCode)');
    }
  }
}
