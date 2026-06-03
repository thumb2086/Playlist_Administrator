import 'package:flutter/material.dart';
import '../services/config_service.dart';
import '../services/spotube_controller.dart';

class SpotubePage extends StatefulWidget {
  const SpotubePage({super.key});
  @override
  State<SpotubePage> createState() => _SpotubePageState();
}

class _SpotubePageState extends State<SpotubePage> {
  final _logs = <String>[];
  final _scrollCtrl = ScrollController();
  bool _running = false;
  String? _status;

  @override
  void dispose() {
    _scrollCtrl.dispose();
    super.dispose();
  }

  void _log(String msg) {
    _logs.add(msg);
    setState(() {});
    Future.delayed(const Duration(milliseconds: 50), () {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  Future<void> _downloadAll() async {
    if (_running) return;
    setState(() { _running = true; _status = '下載中…'; });

    try {
      final ctrl = SpotubeController(
        libraryPath: ConfigService.instance.config.libraryPath,
        coords: ConfigService.instance.config.spotubeCoords,
      );

      if (!ctrl.isRunning()) {
        _log('❌ Spotube 未執行，請先啟動 Spotube');
        setState(() { _running = false; _status = '錯誤'; });
        return;
      }

      final names = ConfigService.instance.config.urlNames.values.toList();
      for (int i = 0; i < names.length; i++) {
        if (_running == false) break;
        _log('[$i/${names.length}] ${names[i]}');
        try {
          await ctrl.downloadPlaylist(names[i]);
          ConfigService.instance.config.lastUpdated[names[i]] =
              DateTime.now().toIso8601String().substring(0, 10);
          await ConfigService.instance.save();
          _log('  ✅ ${names[i]}');
        } catch (e) {
          _log('  ❌ ${names[i]}: $e');
        }
      }
      _log('下載完成');
      setState(() => _status = '完成');
    } catch (e) {
      _log('錯誤: $e');
      setState(() => _status = '錯誤');
    }
    setState(() => _running = false);
  }

  Future<void> _moveFiles() async {
    setState(() => _status = '搬移中…');
    try {
      final ctrl = SpotubeController(
        libraryPath: ConfigService.instance.config.libraryPath,
        coords: ConfigService.instance.config.spotubeCoords,
      );
      final moved = await ctrl.moveDownloads();
      _log('搬移完成: $moved 個檔案');
      setState(() => _status = '搬移完成: $moved');
    } catch (e) {
      _log('搬移失敗: $e');
      setState(() => _status = '錯誤');
    }
  }

  @override
  Widget build(BuildContext context) {
    final updated = ConfigService.instance.config.lastUpdated;
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Status bar
          Row(
            children: [
              Container(
                width: 10, height: 10,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: _running ? Colors.orange : (_status == '完成' ? const Color(0xFF1DB954) : Colors.grey),
                ),
              ),
              const SizedBox(width: 8),
              Text(_status ?? '就緒', style: TextStyle(color: Colors.grey[400], fontSize: 12)),
              const Spacer(),
              Text('${updated.length} 個已下載', style: TextStyle(color: Colors.grey[600], fontSize: 12)),
            ],
          ),
          const SizedBox(height: 12),
          // Action buttons
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _Btn('下載全部', Icons.download, _downloadAll, _running, const Color(0xFF1DB954)),
              _Btn('搬移 M4A', Icons.drive_file_move, _moveFiles, _running, const Color(0xFF2a2a2a)),
              _Btn('取消', Icons.stop, () => setState(() => _running = false), !_running, Colors.red[700]!),
              _Btn('重設記錄', Icons.delete_outline, () {
                ConfigService.instance.config.lastUpdated.clear();
                ConfigService.instance.save();
                setState(() {});
                _log('已重設下載記錄');
              }, false, const Color(0xFF2a2a2a)),
            ],
          ),
          const SizedBox(height: 12),
          // Download records
          Text('下載記錄', style: TextStyle(color: Colors.grey[400], fontSize: 12)),
          const SizedBox(height: 4),
          Expanded(
            flex: 2,
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFF1e1e1e),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: const Color(0xFF2a2a2a)),
              ),
              child: updated.isEmpty
                  ? const Center(child: Text('尚無下載記錄', style: TextStyle(color: Colors.grey)))
                  : ListView.builder(
                      itemCount: updated.length,
                      itemBuilder: (ctx, i) {
                        final e = updated.entries.elementAt(i);
                        return ListTile(
                          dense: true,
                          leading: const Icon(Icons.check_circle, color: Color(0xFF1DB954), size: 18),
                          title: Text(e.key, style: const TextStyle(fontSize: 13)),
                          subtitle: Text(e.value, style: TextStyle(color: Colors.grey[600], fontSize: 11)),
                        );
                      },
                    ),
            ),
          ),
          const SizedBox(height: 8),
          // Log
          Text('日誌', style: TextStyle(color: Colors.grey[400], fontSize: 12)),
          const SizedBox(height: 4),
          Expanded(
            flex: 3,
            child: Container(
              decoration: BoxDecoration(
                color: const Color(0xFF0d0d0d),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: const Color(0xFF2a2a2a)),
              ),
              child: ListView.builder(
                controller: _scrollCtrl,
                itemCount: _logs.length,
                itemBuilder: (ctx, i) => Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
                  child: Text(_logs[i],
                      style: const TextStyle(fontSize: 12, fontFamily: 'monospace', color: Color(0xFFb3b3b3))),
                ),
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
      icon: Icon(icon, size: 16),
      label: Text(label, style: const TextStyle(fontSize: 12)),
      style: ElevatedButton.styleFrom(
        backgroundColor: color,
        foregroundColor: Colors.white,
        disabledBackgroundColor: Colors.grey[800],
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      ),
    );
  }
}
