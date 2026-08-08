import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'bridge_service.dart';
import 'config_service.dart';

/// GUI 端的 RAG 查詢/索引服務 — 透過 Python bridge 執行 rag/query.py 與 rag/build_db.py。
class RagService {
  static RagService? _instance;
  static RagService get instance => _instance ??= RagService._();
  RagService._();

  Future<List<String>> _runPython(List<String> args) async {
    final bridge = await BridgeService.instance.bridgePath;
    final env = Map<String, String>.from(Platform.environment);
    env['PYTHONIOENCODING'] = 'utf-8';
    final basePath = ConfigService.instance.config.basePath;
    if (basePath.isNotEmpty) env['BASE_PATH'] = basePath;
    final proc = await Process.start(
      'python',
      [bridge, ...args],
      runInShell: true,
      workingDirectory: basePath.isNotEmpty ? basePath : Directory.current.path,
      environment: env,
    );
    final lines = <String>[];
    final stderrLines = <String>[];
    proc.stdout.transform(utf8.decoder).transform(const LineSplitter()).listen(
      (line) {
        if (line.trim().isNotEmpty) lines.add(line.trim());
      },
    );
    proc.stderr.transform(utf8.decoder).transform(const LineSplitter()).listen(
      (line) {
        if (line.trim().isNotEmpty) stderrLines.add(line.trim());
      },
    );
    await proc.exitCode;
    if (stderrLines.isNotEmpty) {
      throw Exception(stderrLines.join('\n'));
    }
    return lines;
  }

  /// 查詢 RAG，回傳 {answer, hits:[...], answerError} 之類的結構。
  Future<Map<String, dynamic>> query(String question, {int topk = 8, String show = ''}) async {
    final lines = await _runPython(['rag-query', question, '$topk', show]);
    for (final line in lines) {
      try {
        final json = jsonDecode(line) as Map<String, dynamic>;
        if (json['type'] == 'error') {
          throw Exception(json['message'] as String? ?? 'RAG 查詢失敗');
        }
        if (json['type'] == 'rag_result') {
          final data = json['data'] as Map<String, dynamic>? ?? {};
          final hits = (data['results'] as List<dynamic>? ?? [])
              .whereType<Map<String, dynamic>>()
              .toList();
          return {
            'question': data['question'] ?? question,
            'answer': data['answer'],
            'answerError': data['answer_error'],
            'hits': hits,
          };
        }
      } catch (e) {
        if (e is Exception) rethrow;
      }
    }
    throw Exception('RAG 查詢無回應');
  }

  /// 增量重建 RAG 索引；逐行回傳進度。
  Future<void> build(void Function(String line) onLog) async {
    final bridge = await BridgeService.instance.bridgePath;
    final env = Map<String, String>.from(Platform.environment);
    env['PYTHONIOENCODING'] = 'utf-8';
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
