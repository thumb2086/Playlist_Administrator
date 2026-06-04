import 'package:flutter/material.dart';
import '../services/i18n.dart';
import '../services/version_checker.dart';
import 'dark_theme.dart';

class UpdateDialog extends StatelessWidget {
  final VersionInfo info;
  const UpdateDialog({super.key, required this.info});

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: AppColors.card,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: const Column(children: [
        Icon(Icons.new_releases_rounded, color: AppColors.accent, size: 40),
        SizedBox(height: 8),
        Text('🎉 新版本可用！\nNew Version Available!',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
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
            Text(info.latestVersion, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: AppColors.accent)),
          ]),
          if (info.releaseNotes != null && info.releaseNotes!.isNotEmpty) ...[
            const SizedBox(height: 12),
            const Text('更新內容', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
            const SizedBox(height: 4),
            Container(
              height: 120,
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: AppColors.surfaceLight,
                borderRadius: BorderRadius.circular(8),
              ),
              child: SingleChildScrollView(
                child: Text(info.releaseNotes!, style: const TextStyle(fontSize: 11, color: AppColors.textSecondary, height: 1.4)),
              ),
            ),
          ],
        ]),
      ),
      actions: [
        TextButton(
          onPressed: () {
            VersionChecker.markSkipped(info.latestVersion);
            Navigator.of(context).pop();
          },
          child: Text(t('common.skip'), style: const TextStyle(color: AppColors.textMuted)),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('稍後提醒', style: TextStyle(color: AppColors.textSecondary)),
        ),
        Container(
          decoration: BoxDecoration(
            gradient: const LinearGradient(colors: [AppColors.accent, Color(0xFF169C46)]),
            borderRadius: BorderRadius.circular(8),
          ),
          child: ElevatedButton(
            onPressed: () => Navigator.of(context).pop(),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.transparent, shadowColor: Colors.transparent,
              foregroundColor: Colors.black,
            ),
            child: const Text('下載更新', style: TextStyle(fontWeight: FontWeight.bold)),
          ),
        ),
      ],
    );
  }
}
