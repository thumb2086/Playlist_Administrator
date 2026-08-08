import 'dart:io';

/// App 資料目錄統一為 `%LOCALAPPDATA%\playlist-admin\data`。
/// 首次執行會自動把舊的 `%LOCALAPPDATA%\Playlist Administrator\data`
/// 整個複製過來（config / history / caches / state 全保留）。
class AppDataDir {
  static const _newName = 'playlist-admin';
  static const _legacyName = 'Playlist Administrator';
  static bool _migrated = false;

  static String get _base =>
      Platform.environment['LOCALAPPDATA'] ??
      '${Platform.environment['USERPROFILE'] ?? 'C:\\Users\\Default'}\\AppData\\Local';

  static String get dir => '$_base\\$_newName\\data';
  static String get legacyDir => '$_base\\$_legacyName\\data';

  /// 遷移舊資料（僅搬一次；新目錄已有東西就不動）。
  static Future<void> ensureMigrated() async {
    if (_migrated) return;
    _migrated = true;
    final d = Directory(dir);
    final l = Directory(legacyDir);
    if (d.existsSync() || !l.existsSync()) return;
    try {
      await _copyTree(l, d);
    } catch (_) {}
  }

  static Future<void> _copyTree(Directory src, Directory dst) async {
    await dst.create(recursive: true);
    await for (final e in src.list()) {
      final target = File('${dst.path}\\${e.uri.pathSegments.last}');
      if (e is File) {
        await e.copy(target.path);
      } else if (e is Directory) {
        await _copyTree(e, Directory('${dst.path}\\${e.uri.pathSegments.last}'));
      }
    }
  }
}