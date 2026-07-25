import 'dart:io';
import 'package:flutter/material.dart';
import '../services/i18n.dart';
import '../services/version_checker.dart';
import 'dark_theme.dart';

class UpdateDialog extends StatefulWidget {
  final VersionInfo info;
  const UpdateDialog({super.key, required this.info});

  @override
  State<UpdateDialog> createState() => _UpdateDialogState();
}

class _UpdateDialogState extends State<UpdateDialog> {
  bool _downloading = false;
  double _progress = 0;
  String? _savedPath;

  Future<void> _startDownload() async {
    final url = widget.info.downloadUrl;
    if (url == null) return;
    setState(() { _downloading = true; _progress = 0; });
    final path = await VersionChecker.downloadUpdate(url,
      onProgress: (p) { if (mounted) setState(() => _progress = p); },
    );
    if (path != null && mounted) {
      setState(() { _savedPath = path; _downloading = false; _progress = 1; });
    } else if (mounted) {
      setState(() => _downloading = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('下載失敗，請稍後重試'), backgroundColor: AppColors.error),
      );
    }
  }

  void _launchInstaller() {
    if (_savedPath != null && File(_savedPath!).existsSync()) {
      Process.start(_savedPath!, []).ignore();
      Navigator.of(context).pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: AppColors.card,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: Column(children: [
        Icon(_savedPath != null ? Icons.check_circle : Icons.new_releases_rounded,
            color: _savedPath != null ? AppColors.accent : AppColors.accent, size: 40),
        const SizedBox(height: 8),
        Text(
          _savedPath != null ? '下載完成！' : '🎉 新版本可用！\nNew Version Available!',
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
        ),
      ]),
      content: SizedBox(
        width: 380,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            const Text('目前版本: ', style: TextStyle(color: AppColors.textSecondary, fontSize: 12)),
            Text(t('app.version'), style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
          ]),
          const SizedBox(height: 4),
          Row(children: [
            const Text('最新版本: ', style: TextStyle(color: AppColors.accent, fontSize: 12)),
            Text(widget.info.latestVersion, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppColors.accent)),
          ]),
          if (_downloading) ...[
            const SizedBox(height: 14),
            ClipRRect(borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(value: _progress, backgroundColor: AppColors.surfaceLight,
                  valueColor: const AlwaysStoppedAnimation(AppColors.accent), minHeight: 6)),
            const SizedBox(height: 6),
            Text('${(_progress * 100).toStringAsFixed(0)}%', style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
          ],
          if (widget.info.releaseNotes != null && widget.info.releaseNotes!.isNotEmpty && _savedPath == null) ...[
            const SizedBox(height: 12),
            const Text('更新內容', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            Container(
              height: 120, padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(color: AppColors.surfaceLight, borderRadius: BorderRadius.circular(8)),
              child: SingleChildScrollView(
                child: Text(widget.info.releaseNotes!, style: const TextStyle(fontSize: 11, color: AppColors.textSecondary, height: 1.4)),
              ),
            ),
          ],
        ]),
      ),
      actions: [
        if (_savedPath == null) ...[
          TextButton(
            onPressed: () { VersionChecker.markSkipped(widget.info.latestVersion); Navigator.of(context).pop(); },
            child: Text(t('common.skip'), style: const TextStyle(color: AppColors.textMuted)),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('稍後提醒', style: TextStyle(color: AppColors.textSecondary)),
          ),
          Container(
            decoration: BoxDecoration(gradient: const LinearGradient(colors: [AppColors.accent, Color(0xFF169C46)]), borderRadius: BorderRadius.circular(8)),
            child: ElevatedButton(
              onPressed: _downloading ? null : _startDownload,
              style: ElevatedButton.styleFrom(backgroundColor: Colors.transparent, shadowColor: Colors.transparent, foregroundColor: Colors.black),
              child: Text(_downloading ? '下載中…' : '下載更新', style: const TextStyle(fontWeight: FontWeight.bold)),
            ),
          ),
        ] else ...[
          Container(
            decoration: BoxDecoration(gradient: const LinearGradient(colors: [AppColors.accent, Color(0xFF169C46)]), borderRadius: BorderRadius.circular(8)),
            child: ElevatedButton(
              onPressed: _launchInstaller,
              style: ElevatedButton.styleFrom(backgroundColor: Colors.transparent, shadowColor: Colors.transparent, foregroundColor: Colors.black),
              child: const Text('執行安裝', style: TextStyle(fontWeight: FontWeight.bold)),
            ),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('稍後安裝', style: TextStyle(color: AppColors.textSecondary)),
          ),
        ],
      ],
    );
  }
}
