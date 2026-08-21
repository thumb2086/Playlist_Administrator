import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:logger/logger.dart';

final _log = Logger(printer: PrettyPrinter(methodCount: 0));

/// Ollama REST API 原生 Dart 客戶端（取代 Python bridge）。
/// 直接呼叫本地 Ollama API，不需要 Python。
class OllamaNativeService {
  OllamaNativeService._();
  static final instance = OllamaNativeService._();

  String baseUrl = 'http://127.0.0.1:11434';
  bool _connected = false;
  bool get isConnected => _connected;

  /// 檢查 Ollama 是否運行中。
  Future<bool> checkConnection() async {
    try {
      final resp = await http.get(Uri.parse('$baseUrl/api/tags'))
          .timeout(const Duration(seconds: 5));
      _connected = resp.statusCode == 200;
      return _connected;
    } catch (_) {
      _connected = false;
      return false;
    }
  }

  /// 取得已安裝的模型列表。
  Future<List<String>> listModels() async {
    try {
      final resp = await http.get(Uri.parse('$baseUrl/api/tags'))
          .timeout(const Duration(seconds: 5));
      if (resp.statusCode != 200) return [];
      final data = jsonDecode(resp.body);
      final models = (data['models'] as List?) ?? [];
      return models.map<String>((m) => m['name'] as String).toList();
    } catch (_) {
      return [];
    }
  }
  /// 串流式問答（逐 token 回傳）。
  Stream<String> chatStream(String prompt, {String? model, List<Map<String, String>>? history}) async* {
    final chosenModel = model ?? await _pickModel();
    if (chosenModel == null) throw Exception('無可用模型');

    final messages = <Map<String, String>>[];
    if (history != null) messages.addAll(history);
    messages.add({'role': 'user', 'content': prompt});

    final resp = await http.post(
      Uri.parse('$baseUrl/api/chat'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'model': chosenModel,
        'messages': messages,
        'stream': false,
      }),
    ).timeout(const Duration(seconds: 300));

    if (resp.statusCode != 200) {
      throw Exception('Ollama 回應 ${resp.statusCode}');
    }

    final data = jsonDecode(resp.body);
    final content = data['message']?['content'] as String?;
    if (content != null) yield content;
  }

  /// 非串流式問答。
  Future<String> chat(String prompt, {String? model, List<Map<String, String>>? history}) async {
    final sb = StringBuffer();
    await for (final token in chatStream(prompt, model: model, history: history)) {
      sb.write(token);
    }
    return sb.toString();
  }

  /// 產生 embeddings（用於 RAG）。
  Future<List<double>> embed(String text, {String? model}) async {
    final chosenModel = model ?? 'nomic-embed-text';
    final resp = await http.post(
      Uri.parse('$baseUrl/api/embeddings'),
      headers: {'Content-Type': 'application/json'},
      body: jsonEncode({
        'model': chosenModel,
        'prompt': text,
      }),
    ).timeout(const Duration(seconds: 60));

    if (resp.statusCode != 200) {
      throw Exception('Ollama embed 失敗: ${resp.statusCode}');
    }
    final data = jsonDecode(resp.body);
    return (data['embedding'] as List?)?.cast<double>() ?? [];
  }

  Future<String?> _pickModel() async {
    final models = await listModels();
    if (models.isEmpty) return null;
    // 偏好通用對話模型。
    const preferred = ['llama3.1', 'llama3', 'qwen2.5', 'gemma2', 'mistral'];
    for (final p in preferred) {
      final match = models.where((m) => m.toLowerCase().contains(p));
      if (match.isNotEmpty) return match.first;
    }
    return models.first;
  }
}
