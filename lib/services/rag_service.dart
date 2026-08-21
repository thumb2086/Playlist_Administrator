import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'bridge_service.dart';
import 'config_service.dart';

/// RAG 索引服務 — 透過 Python bridge 執行 rag/build_db.py（增量）。
/// 問答不再走 GUI 頁面，改用 opencode（podcast-knowledge skill）。
class RagService {
  static RagService? _instance;
  static RagService get instance => _instance ??= RagService._();
  RagService._();

  /// 增量重建 RAG 索引；逐行回傳進度。
  Future<void> build(void Function(String line) onLog) async {
    final bridge = await BridgeService.instance.bridgePath;
    final env = Map<String, String>.from(Platform.environment);
    env['PYTHONIOENCODING'] = 'utf-8';
    env['PYTHONUNBUFFERED'] = '1';
    final basePath = ConfigService.instance.config.basePath;
    if (basePath.isNotEmpty) env['BASE_PATH'] = basePath;
    final proc = await Process.start(
      'python',
      [bridge, 'rag-build'],
      runInShell: true,
      workingDirectory: basePath.isNotEmpty ? basePath : Directory.current.path,
      environment: env,
    );
    final completer = Completer<void>();
    proc.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
      if (line.trim().isEmpty) return;
      try {
        final json = jsonDecode(line.trim()) as Map<String, dynamic>;
        final type = json['type'] as String?;
        if (type == 'log') onLog(json['message'] as String? ?? '');
        if (type == 'error' && !completer.isCompleted) {
          completer.completeError(Exception(json['message'] as String? ?? 'RAG 重建失敗'));
        }
        if (type == 'complete' && !completer.isCompleted) completer.complete();
      } catch (_) {
        onLog(line.trim());
      }
    });
    proc.stderr.transform(utf8.decoder).transform(const LineSplitter()).listen((line) {
      if (line.trim().isNotEmpty) onLog(line.trim());
    });
    await proc.exitCode;
    if (!completer.isCompleted) {
      completer.complete();
    }
    await completer.future;
  }
}
