import 'package:flutter/material.dart';
import '../services/rag_service.dart';
import '../widgets/dark_theme.dart';

/// Podcast RAG 頁面：語意搜尋逐字稿，Ollama 生成回答。
class RagPage extends StatefulWidget {
  const RagPage({super.key});
  @override
  State<RagPage> createState() => _RagPageState();
}

class _RagPageState extends State<RagPage> {
  final _questionCtrl = TextEditingController();
  bool _busy = false;
  bool _building = false;
  String? _answer;
  String? _answerError;
  List<Map<String, dynamic>> _hits = [];
  final List<String> _buildLog = [];

  @override
  void dispose() {
    _questionCtrl.dispose();
    super.dispose();
  }

  Future<void> _query() async {
    final q = _questionCtrl.text.trim();
    if (q.isEmpty || _busy) return;
    setState(() {
      _busy = true;
      _answer = null;
      _answerError = null;
      _hits = [];
    });
    try {
      final result = await RagService.instance.query(q);
      if (!mounted) return;
      setState(() {
        _answer = result['answer'] as String?;
        _answerError = result['answerError'] as String?;
        _hits = (result['hits'] as List).cast<Map<String, dynamic>>();
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _answerError = '查詢失敗: $e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _build() async {
    if (_building) return;
    setState(() {
      _building = true;
      _buildLog.clear();
    });
    try {
      await RagService.instance.build((line) {
        if (mounted && _buildLog.length < 200) {
          setState(() => _buildLog.add(line));
        }
      });
    } catch (e) {
      if (mounted) setState(() => _buildLog.add('❌ $e'));
    } finally {
      if (mounted) setState(() => _building = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Text('Podcast RAG', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600)),
          const SizedBox(width: 8),
          const Text('語意搜尋逐字稿（Ollama + ChromaDB）',
              style: TextStyle(color: AppColors.textMuted, fontSize: 11)),
          const Spacer(),
          OutlinedButton.icon(
            onPressed: _building ? null : _build,
            icon: _building
                ? const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.storage_rounded, size: 14),
            label: Text(_building ? '重建中…' : '重建索引'),
          ),
        ]),
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: TextField(
              controller: _questionCtrl,
              enabled: !_busy,
              onSubmitted: (_) => _query(),
              decoration: InputDecoration(
                hintText: '問你的 podcast 內容，例如：游庭皓對台股的看法',
                prefixIcon: const Icon(Icons.search, size: 18),
                border: const OutlineInputBorder(),
                isDense: true,
              ),
              style: const TextStyle(fontSize: 13),
            ),
          ),
          const SizedBox(width: 8),
          ElevatedButton.icon(
            onPressed: _busy ? null : _query,
            icon: _busy
                ? const SizedBox(width: 12, height: 12, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.auto_awesome, size: 14),
            label: const Text('查詢'),
          ),
        ]),
        const SizedBox(height: 12),
        if (_building)
          Expanded(
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: AppColors.border),
              ),
              child: ListView(
                children: [
                  for (final line in _buildLog)
                    Text(line, style: const TextStyle(fontSize: 11, color: AppColors.textSecondary)),
                ],
              ),
            ),
          )
        else if (_busy)
          const Expanded(child: Center(child: CircularProgressIndicator()))
        else if (_answer != null || _answerError != null || _hits.isNotEmpty)
          Expanded(child: _buildResults())
        else
          const Expanded(
            child: Center(
              child: Text('輸入問題開始查詢。先確定 Ollama 在跑、且已執行過「重建索引」。',
                  style: TextStyle(color: AppColors.textMuted, fontSize: 12)),
            ),
          ),
      ]),
    );
  }

  Widget _buildResults() {
    return ListView(children: [
      if (_answer != null)
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(14),
          decoration: BoxDecoration(
            color: AppColors.surfaceLight,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: AppColors.border),
          ),
          child: Text(_answer!, style: const TextStyle(fontSize: 13, height: 1.5)),
        ),
      if (_answerError != null)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(_answerError!,
              style: const TextStyle(color: Colors.orangeAccent, fontSize: 12)),
        ),
      if (_hits.isNotEmpty) ...[
        const Padding(
          padding: EdgeInsets.only(top: 12, bottom: 4),
          child: Text('來源片段', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
        ),
        for (final h in _hits.take(8))
          Card(
            margin: const EdgeInsets.only(bottom: 6),
            color: AppColors.surfaceLight,
            child: Padding(
              padding: const EdgeInsets.all(10),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Row(children: [
                  Expanded(
                    child: Text(
                      '${h['show']}  ${h['date'] ?? ''}',
                      style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                    ),
                  ),
                  Text('相似度 ${(h['best_similarity'] as num?)?.toStringAsFixed(3) ?? ''}',
                      style: const TextStyle(color: AppColors.accent, fontSize: 11)),
                ]),
                const SizedBox(height: 4),
                Text(h['file'] ?? '',
                    style: const TextStyle(color: AppColors.textMuted, fontSize: 10)),
                const SizedBox(height: 4),
                for (final hit in (h['hits'] as List).take(2))
                  Text('• ${(hit as Map<String, dynamic>)['chunk']}',
                      style: const TextStyle(fontSize: 11, color: AppColors.textSecondary)),
              ]),
            ),
          ),
      ],
    ]);
  }
}
