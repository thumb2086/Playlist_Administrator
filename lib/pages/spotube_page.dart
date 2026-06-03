import 'dart:async';
import 'package:flutter/material.dart';
import '../services/config_service.dart';
import '../services/spotube_controller.dart';
import '../widgets/dark_theme.dart';

class SpotubePage extends StatefulWidget {
  const SpotubePage({super.key});
  @override
  State<SpotubePage> createState() => _SpotubePageState();
}

class _SpotubePageState extends State<SpotubePage> {
  final _logs = <String>[];
  final _scrollCtrl = ScrollController();
  bool _running = false;
  String _status = '就緒';

  @override
  void dispose() { _scrollCtrl.dispose(); super.dispose(); }

  void _log(String msg) { _logs.add(msg); if (mounted) setState(() {}); _autoScroll(); }
  void _autoScroll() {
    Future.delayed(const Duration(milliseconds: 50), () {
      if (_scrollCtrl.hasClients) _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent, duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
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
      if (!ctrl.isRunning()) { _log('❌ Spotube 未執行'); setState(() { _running = false; _status = '錯誤'; }); return; }

      final names = ConfigService.instance.config.urlNames.values.toList();
      for (int i = 0; i < names.length; i++) {
        if (!_running) break;
        _log('[$i/${names.length}] ${names[i]}');
        try {
          await ctrl.downloadPlaylist(names[i]);
          ConfigService.instance.config.lastUpdated[names[i]] = DateTime.now().toIso8601String().substring(0, 10);
          await ConfigService.instance.save();
          _log('  ✅ ${names[i]}');
        } catch (e) { _log('  ❌ ${names[i]}: $e'); }
      }
      _log('下載完成'); setState(() => _status = '完成');
    } catch (e) { _log('錯誤: $e'); setState(() => _status = '錯誤'); }
    setState(() => _running = false);
  }

  Future<void> _moveFiles() async {
    setState(() => _status = '搬移中…');
    try {
      final ctrl = SpotubeController(libraryPath: ConfigService.instance.config.libraryPath);
      final moved = await ctrl.moveDownloads();
      _log('搬移完成: $moved 個檔案'); setState(() => _status = '搬移完成: $moved');
    } catch (e) { _log('搬移失敗: $e'); setState(() => _status = '錯誤'); }
  }

  @override
  Widget build(BuildContext context) {
    final downloaded = ConfigService.instance.config.lastUpdated;
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        // Status + controls
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: AppColors.card, borderRadius: BorderRadius.circular(14), border: Border.all(color: AppColors.border)),
          child: Column(children: [
            Row(children: [
              Container(width: 10, height: 10,
                decoration: BoxDecoration(shape: BoxShape.circle,
                    color: _running ? Colors.orange : (_status == '完成' ? AppColors.accent : AppColors.textMuted)),
              ),
              const SizedBox(width: 8),
              Text(_status, style: TextStyle(color: _running ? Colors.orange : AppColors.textSecondary, fontSize: 13, fontWeight: FontWeight.w500)),
              const Spacer(),
              Text('${downloaded.length} 個已下載', style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
            ]),
            const SizedBox(height: 14),
            Wrap(spacing: 8, runSpacing: 8, children: [
              _SButton('下載全部', Icons.download_rounded, _downloadAll, _running, isPrimary: true),
              _SButton('搬移 M4A', Icons.drive_file_move_rounded, _moveFiles, _running),
              _SButton('取消', Icons.stop_rounded, () => setState(() => _running = false), !_running, color: AppColors.error),
              _SButton('重設記錄', Icons.delete_outline_rounded, () {
                ConfigService.instance.config.lastUpdated.clear();
                ConfigService.instance.save(); setState(() {}); _log('已重設下載記錄');
              }, false),
            ]),
          ]),
        ),
        const SizedBox(height: 14),
        // Records
        const Text('下載記錄', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        Expanded(flex: 2, child: Container(
          decoration: BoxDecoration(color: AppColors.card, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppColors.border)),
          clipBehavior: Clip.antiAlias,
          child: downloaded.isEmpty
              ? const Center(child: Text('尚無下載記錄', style: TextStyle(color: AppColors.textMuted)))
              : ListView.builder(itemCount: downloaded.length, itemBuilder: (ctx, i) {
                  final e = downloaded.entries.elementAt(i);
                  return ListTile(dense: true,
                    leading: const Icon(Icons.check_circle, color: AppColors.accent, size: 18),
                    title: Text(e.key, style: const TextStyle(fontSize: 13)),
                    subtitle: Text(e.value, style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
                  );
                }),
        )),
        const SizedBox(height: 8),
        // Log
        const Text('日誌', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        Expanded(flex: 3, child: Container(
          decoration: BoxDecoration(color: const Color(0xFF080808), borderRadius: BorderRadius.circular(12), border: Border.all(color: AppColors.border)),
          clipBehavior: Clip.antiAlias,
          child: _logs.isEmpty
              ? const Center(child: Text('日誌將顯示在這裡', style: TextStyle(color: AppColors.textMuted, fontSize: 12)))
              : ListView.builder(controller: _scrollCtrl, padding: const EdgeInsets.all(10),
                  itemCount: _logs.length, itemBuilder: (ctx, i) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 1),
                    child: Text(_logs[i], style: const TextStyle(fontSize: 11, fontFamily: 'Consolas', color: AppColors.textMuted, height: 1.4)),
                  )),
        )),
        const SizedBox(height: 16),
      ]),
    );
  }
}

class _SButton extends StatelessWidget {
  final String label; final IconData icon; final VoidCallback onPressed;
  final bool disabled; final bool isPrimary; final Color? color;
  const _SButton(this.label, this.icon, this.onPressed, this.disabled, {this.isPrimary = false, this.color});

  @override
  Widget build(BuildContext context) {
    return ElevatedButton.icon(
      onPressed: disabled ? null : onPressed,
      icon: Icon(icon, size: 15),
      label: Text(label, style: const TextStyle(fontSize: 12)),
      style: ElevatedButton.styleFrom(
        backgroundColor: color ?? (isPrimary ? AppColors.accent : AppColors.surfaceLight),
        foregroundColor: isPrimary ? Colors.black : AppColors.text,
        disabledBackgroundColor: AppColors.surfaceLight.withValues(alpha: 0.5),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      ),
    );
  }
}
