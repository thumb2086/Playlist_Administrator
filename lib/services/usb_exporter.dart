import 'dart:io';
import 'config_service.dart';

class UsbExportResult {
  final int copied;
  final int total;
  final int missing;
  final String targetPath;
  UsbExportResult({required this.copied, required this.total, required this.missing, required this.targetPath});
}

class UsbExporter {
  final void Function(String) log;

  UsbExporter({required this.log});

  Future<UsbExportResult> exportPlaylists(
    List<String> playlistFiles, {
    String? targetDir,
    String quality = 'original', // 'original', 'mp3', 'flac'
  }) async {
    final cfg = ConfigService.instance.config;
    final exportPath = targetDir ?? cfg.exportPath;
    final libraryPath = cfg.libraryPath;

    // Clean and recreate export dir
    final exportDir = Directory(exportPath);
    if (await exportDir.exists()) {
      await exportDir.delete(recursive: true);
    }
    await exportDir.create(recursive: true);

    int total = 0;
    int copied = 0;
    int missing = 0;

    for (final plFile in playlistFiles) {
      final plName = File(plFile).uri.pathSegments.last.replaceAll(RegExp(r'\.m3u8?$'), '');
      final destFolder = Directory('$exportPath\\$plName');
      await destFolder.create();

      try {
        final lines = await File(plFile).readAsLines();
        int plCopied = 0;
        int plTotal = 0;

        for (final line in lines) {
          final trimmed = line.trim();
          if (trimmed.isEmpty || trimmed.startsWith('#')) continue;

          plTotal++;
          total++;

          // Resolve source file
          String src = trimmed;
          if (!File(src).existsSync()) {
            final fname = File(src).uri.pathSegments.last;
            src = '$libraryPath\\$fname';
          }
          if (!File(src).existsSync()) {
            log('  ⚠️ 找不到檔案: $trimmed');
            missing++;
            continue;
          }

          // Handle quality conversion
          String finalSrc = src;
          if (quality == 'mp3' || quality == 'flac') {
            final srcExt = src.toLowerCase().split('.').last;
            if (srcExt != quality) {
              final stem = File(src).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '');
              final convertedPath = '$exportPath\\temp_${stem}_$plName.$quality';
              final cmd = <String>[
                'ffmpeg', '-y', '-i', src,
                if (quality == 'mp3') ...['-codec:a', 'libmp3lame', '-qscale:a', '0'],
                if (quality == 'flac') ...['-codec:a', 'flac'],
                convertedPath,
              ];
              final r = await Process.run(cmd[0], cmd.sublist(1), runInShell: true);
              if (r.exitCode == 0) {
                finalSrc = convertedPath;
              } else {
                log('  ⚠️ 轉換失敗，使用原始檔案: ${File(src).uri.pathSegments.last}');
              }
            }
          }

          // Copy to destination
          final destName = File(finalSrc).uri.pathSegments.last;
          final destPath = '${destFolder.path}\\$destName';
          try {
            await File(finalSrc).copy(destPath);
            plCopied++;
            copied++;
          } catch (e) {
            log('  ❌ 複製失敗 ${File(src).uri.pathSegments.last}: $e');
          }

          // Clean temp file
          if (finalSrc != src && await File(finalSrc).exists()) {
            await File(finalSrc).delete();
          }
        }

        log('  📁 $plName: $plCopied/$plTotal 首已匯出');
      } catch (e) {
        log('  ❌ 處理 $plName 失敗: $e');
      }
    }

    log('\n✅ 匯出完成: $copied/$total 首 (缺少 $missing 首)');
    return UsbExportResult(copied: copied, total: total, missing: missing, targetPath: exportPath);
  }
}
