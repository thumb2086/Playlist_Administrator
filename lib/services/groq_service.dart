import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'config_service.dart';

class GroqService {
  static GroqService? _instance;
  static GroqService get instance => _instance ??= GroqService._();
  GroqService._();

  String _keysCsv = '';
  String _model = 'whisper-large-v3';

  void setApiKey(String csv) { _keysCsv = csv; }
  String? get apiKey => _keysCsv.isNotEmpty ? _keysCsv.split(',')[0].trim() : null;
  int get keyCount => _keysCsv.split(',').where((k) => k.trim().isNotEmpty).length;
  String get defaultModel => _model;

  Future<void> loadFromEnv() async {
    final f = File('.env');
    if (!await f.exists()) return;
    try {
      for (final line in await f.readAsLines()) {
        final l = line.trim();
        if (l.isEmpty || l.startsWith('#')) continue;
        final eq = l.indexOf('=');
        if (eq <= 0) continue;
        final k = l.substring(0, eq).trim();
        final v = l.substring(eq + 1).trim();
        if (k == 'GROQ_API_KEY' && v.isNotEmpty) _keysCsv = v;
        else if (k == 'GROQ_MODEL' && v.isNotEmpty) _model = v;
      }
    } catch (e) { debugPrint('[Groq] .env error: $e'); }
  }

  String get _bridgePath {
    final exeDir = File(Platform.resolvedExecutable).parent.path;
    final dir = Directory(exeDir);
    Directory? d = dir;
    while (d != null) {
      final c = '${d.path}\\tools\\flutter_download_bridge.py';
      if (File(c).existsSync()) return c;
      final p = d.parent;
      d = p.path == d.path ? null : p;
    }
    return '';
  }

  Future<String> transcribeFile({
    required String filePath, required String model, String? language,
    void Function(String chunk, double pct)? onChunk,
  }) async {
    if (_keysCsv.isEmpty) throw Exception('請先設定 Groq API Key');
    if (!File(filePath).existsSync()) throw Exception('檔案不存在: $filePath');

    final bridge = _bridgePath;
    if (bridge.isEmpty) throw Exception('找不到 bridge script');

    final env = Map<String, String>.from(Platform.environment);
    env['PYTHONIOENCODING'] = 'utf-8';

    // Extract base path for Python's ConfigService
    final basePath = ConfigService.instance.config.basePath;
    if (basePath.isNotEmpty) env['BASE_PATH'] = basePath;

    final proc = await Process.start(
      'python',
      [bridge, 'groq-transcribe', filePath, _keysCsv, model, language ?? 'zh'],
      runInShell: true,
      workingDirectory: basePath.isNotEmpty ? basePath : Directory.current.path,
      environment: env,
    );

    final lastLine = Completer<String>();

    proc.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen(
      (line) {
        final t = line.trim();
        if (t.isEmpty) return;
        try {
          final json = jsonDecode(t) as Map<String, dynamic>;
          if (json['type'] == 'error' && !lastLine.isCompleted) {
            lastLine.completeError(Exception(json['message'] as String? ?? 'Groq error'));
          }
          if (json['type'] == 'progress') {
            final pct = (json['percent'] as num?)?.toDouble() ?? 0;
            onChunk?.call(json['message'] as String? ?? '', pct / 100);
          }
          if (json['type'] == 'transcription' && !lastLine.isCompleted) {
            lastLine.complete(json['text'] as String? ?? '');
          }
        } catch (e) {
          // Could be non-JSON line, skip
        }
      },
    );

    proc.stderr.transform(utf8.decoder).transform(const LineSplitter()).listen(
      (line) {
        final t = line.trim();
        if (t.isNotEmpty) {
          debugPrint('[Groq] stderr: $t');
        }
      },
    );

    await proc.exitCode;

    if (lastLine.isCompleted) {
      return lastLine.future;
    }

    // Check stderr for clues
    final procExit = await proc.exitCode;
    if (procExit != 0) {
      // Try to read remaining stderr
      final errBuf = await proc.stderr.transform(utf8.decoder).transform(const LineSplitter()).toList();
      final errMsg = errBuf.where((l) => l.trim().isNotEmpty).join('\n');
      throw Exception('Python exit $procExit: ${errMsg.isNotEmpty ? errMsg.substring(0, errMsg.length.clamp(0, 200)) : "no output"}');
    }
    throw Exception('未收到 Groq 回應');
  }

  Future<String> transcribeUrl({required String audioUrl, required String model, String? language}) async {
    throw UnimplementedError('URL 轉錄尚未支援，請先下載音檔');
  }

  static const models = ['whisper-large-v3', 'whisper-large-v3-turbo'];
  static const languages = ['', 'zh', 'en', 'ja', 'ko', 'es', 'fr', 'de', 'th', 'vi'];
}
