import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../services/config_service.dart';
import '../services/i18n.dart';
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
  String _status = '';

  @override
  void initState() {
    super.initState();
    _status = t('spotube.status_ready');
    I18N.instance.addListener(() { if (mounted) setState(() {}); });
  }

  @override
  void dispose() { _scrollCtrl.dispose(); super.dispose(); }

  void _log(String msg) { _logs.add(msg); if (mounted) setState(() {}); _autoScroll(); }
  void _autoScroll() {
    Future.delayed(const Duration(milliseconds: 50), () {
      if (_scrollCtrl.hasClients) _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent, duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
    });
  }

  SpotubeController? _ctrl;

  void _cancelDownload() {
    if (_ctrl != null) {
      _ctrl!.abort();
      _ctrl = null;
    }
    setState(() { _running = false; _status = t('spotube.status_cancelled'); });
    _log('⏹️ ${t('spotube.cancelled')}');
  }

  Future<void> _downloadAll() async {
    if (_running) return;
    setState(() { _running = true; _status = t('spotube.status_downloading'); });
    try {
      final ctrl = SpotubeController(
        libraryPath: ConfigService.instance.config.libraryPath,
        coords: ConfigService.instance.config.spotubeCoords,
      );
      _ctrl = ctrl;
      if (!ctrl.isRunning()) {
        _log('❌ ${t('spotube.not_running')}');
        setState(() { _running = false; _status = t('common.error'); });
        return;
      }

      final names = ConfigService.instance.config.urlNames.values.toList();
      await ctrl.downloadAll(names);
      for (final name in names) {
        if (ctrl.isAborted) break;
        ConfigService.instance.config.lastUpdated[name] = DateTime.now().toIso8601String().substring(0, 10);
      }
      await ConfigService.instance.save();

      _log(ctrl.isAborted ? t('spotube.cancelled') : t('spotube.download_complete'));
      setState(() => _status = ctrl.isAborted ? t('spotube.status_cancelled') : t('common.done'));
    } catch (e) { _log('${t('common.error')}: $e'); setState(() => _status = t('common.error')); }
    _ctrl = null;
    setState(() => _running = false);
  }

  Future<void> _moveFiles() async {
    setState(() => _status = t('spotube.status_moving'));
    try {
      final ctrl = SpotubeController(libraryPath: ConfigService.instance.config.libraryPath);
      final moved = await ctrl.moveDownloads();
      _log(t('spotube.move_complete', [moved])); setState(() => _status = t('spotube.status_moved'));
    } catch (e) { _log('${t('spotube.move_failed')}: $e'); setState(() => _status = t('common.error')); }
  }

  @override
  Widget build(BuildContext context) {
    final downloaded = ConfigService.instance.config.lastUpdated;
    return CallbackShortcuts(
      bindings: {
        if (_running)
          const SingleActivator(LogicalKeyboardKey.escape): _cancelDownload,
      },
      child: Focus(
        autofocus: true,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: AppColors.card, borderRadius: BorderRadius.circular(14), border: Border.all(color: AppColors.border)),
          child: Column(children: [
            Row(children: [
              Container(width: 10, height: 10,
                decoration: BoxDecoration(shape: BoxShape.circle,
                    color: _running ? Colors.orange : (_status == t('common.done') ? AppColors.accent : AppColors.textMuted)),
              ),
              const SizedBox(width: 8),
              Text(_status, style: TextStyle(color: _running ? Colors.orange : AppColors.textSecondary, fontSize: 13, fontWeight: FontWeight.w500)),
              const Spacer(),
              Text(t('spotube.count_downloaded', [downloaded.length]), style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
            ]),
            const SizedBox(height: 14),
            Wrap(spacing: 8, runSpacing: 8, children: [
              _SButton(t('spotube.download_all'), Icons.download_rounded, _downloadAll, _running, isPrimary: true),
              _SButton(t('spotube.move_m4a'), Icons.drive_file_move_rounded, _moveFiles, _running),
              _SButton(t('spotube.cancel'), Icons.stop_rounded, _cancelDownload, !_running, color: AppColors.error),
              _SButton(t('spotube.reset_records'), Icons.delete_outline_rounded, () {
                ConfigService.instance.config.lastUpdated.clear();
                ConfigService.instance.save(); setState(() {}); _log(t('spotube.records_reset'));
              }, false),
            ]),
          ]),
        ),
        const SizedBox(height: 14),
        Text(t('spotube.download_records'), style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        Expanded(flex: 2, child: Container(
          decoration: BoxDecoration(color: AppColors.card, borderRadius: BorderRadius.circular(12), border: Border.all(color: AppColors.border)),
          clipBehavior: Clip.antiAlias,
          child: downloaded.isEmpty
              ? Center(child: Text(t('spotube.no_records'), style: const TextStyle(color: AppColors.textMuted)))
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
        Text(t('spotube.log'), style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
        const SizedBox(height: 8),
        Expanded(flex: 3, child: Container(
          decoration: BoxDecoration(color: const Color(0xFF080808), borderRadius: BorderRadius.circular(12), border: Border.all(color: AppColors.border)),
          clipBehavior: Clip.antiAlias,
          child: _logs.isEmpty
              ? Center(child: Text(t('spotube.log_placeholder'), style: const TextStyle(color: AppColors.textMuted, fontSize: 12)))
              : ListView.builder(controller: _scrollCtrl, padding: const EdgeInsets.all(10),
                  itemCount: _logs.length, itemBuilder: (ctx, i) => Padding(
                    padding: const EdgeInsets.symmetric(vertical: 1),
                    child: Text(_logs[i], style: const TextStyle(fontSize: 11, fontFamily: 'Consolas', color: AppColors.textMuted, height: 1.4)),
                  )),
        )),
        const SizedBox(height: 16),
          ]),
        ),
      ),
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
