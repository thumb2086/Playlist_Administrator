import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:logger/logger.dart';
import 'config_service.dart';

final _log = Logger(printer: PrettyPrinter(methodCount: 0));

/// Groq REST API 原生 Dart 客戶端（取代 Python bridge）。
/// 直接呼叫 api.groq.com，不需要 Python/yt-dlp。
class GroqNativeService {
  GroqNativeService._();
  static final instance = GroqNativeService._();

  String _apiKey = '';
  String get apiKey => _apiKey;
  bool get hasApiKey => _apiKey.isNotEmpty;

  void setApiKey(String key) => _apiKey = key;

  Future<void> loadFromEnv() async {
    const envKey = String.fromEnvironment('GROQ_API_KEY', defaultValue: '');
    if (envKey.isNotEmpty) _apiKey = envKey;
  }

  /// Whisper 語音轉文字。
  Future<String> transcribe(String filePath, {String model = 'whisper-large-v3-turbo', String? language}) async {
    if (!hasApiKey) throw Exception('未設定 Groq API Key');
    final file = await http.MultipartFile.fromPath('file', filePath);
    final request = http.MultipartRequest(
      'POST',
      Uri.parse('https://api.groq.com/openai/v1/audio/transcriptions'),
    )
      ..headers['Authorization'] = 'Bearer $_apiKey'
      ..fields['model'] = model
      ..fields['response_format'] = 'verbose_json'
      ..files.add(file);

    final streamedResponse = await request.send().timeout(const Duration(seconds: 300));
    final body = await streamedResponse.stream.bytesToString();
    if (streamedResponse.statusCode != 200) {
      throw Exception('Groq 轉錄失敗 ${streamedResponse.statusCode}: $body');
    }
    final data = jsonDecode(body);
    return data['text'] as String? ?? '';
  }

  /// Chat completion（用於 RAG 問答）。
  Future<String> chat(List<Map<String, String>> messages, {String model = 'llama-3.1-8b-instant', int maxTokens = 2048}) async {
    if (!hasApiKey) throw Exception('未設定 Groq API Key');
    final resp = await http.post(
      Uri.parse('https://api.groq.com/openai/v1/chat/completions'),
      headers: {
        'Authorization': 'Bearer $_apiKey',
        'Content-Type': 'application/json',
      },
      body: jsonEncode({
        'model': model,
        'messages': messages,
        'max_tokens': maxTokens,
      }),
    ).timeout(const Duration(seconds: 120));

    if (resp.statusCode != 200) {
      throw Exception('Groq chat 失敗 ${resp.statusCode}: ${resp.body}');
    }
    final data = jsonDecode(resp.body);
    return data['choices'][0]['message']['content'] as String? ?? '';
  }
}
