import 'dart:convert';
import 'package:http/http.dart' as http;
import '../version.dart';
import 'config_service.dart';

class VersionInfo {
  final String latestVersion;
  final String htmlUrl;
  final String? releaseNotes;
  final bool hasUpdate;

  VersionInfo({
    required this.latestVersion,
    required this.htmlUrl,
    this.releaseNotes,
    required this.hasUpdate,
  });
}

class VersionChecker {
  static const _owner = 'thumb2086';
  static const _repo = 'Playlist_Administrator';
  static const _apiUrl = 'https://api.github.com/repos/$_owner/$_repo/releases/latest';

  static String get currentVersion => appVersion.startsWith('v') ? appVersion : 'v$appVersion';

  static List<int> _parseVersion(String v) {
    final cleaned = v.replaceAll(RegExp(r'[^\d.]'), '');
    final parts = cleaned.split('.');
    return parts.map((p) => int.tryParse(p) ?? 0).toList();
  }

  static bool _isNewer(String latest, String current) {
    final l = _parseVersion(latest);
    final c = _parseVersion(current);
    for (int i = 0; i < 3; i++) {
      final lv = i < l.length ? l[i] : 0;
      final cv = i < c.length ? c[i] : 0;
      if (lv > cv) return true;
      if (lv < cv) return false;
    }
    return false;
  }

  static bool shouldCheck() {
    final cfg = ConfigService.instance.config;
    if (!cfg.autoUpdateCheck) return false;

    final skipped = cfg.skippedVersion;
    if (skipped.isNotEmpty) {
      if (_isNewer(skipped, currentVersion)) return false;
    }

    return true;
  }

  static void markSkipped(String version) {
    ConfigService.instance.config.skippedVersion = version;
    ConfigService.instance.save();
  }

  static Future<VersionInfo> checkForUpdate() async {
    try {
      final resp = await http.get(
        Uri.parse(_apiUrl),
        headers: {'User-Agent': 'PlaylistAdministrator/2.0'},
      );

      if (resp.statusCode != 200) {
        return VersionInfo(latestVersion: currentVersion, htmlUrl: '', hasUpdate: false);
      }

      final data = jsonDecode(resp.body) as Map<String, dynamic>;
      final latestTag = (data['tag_name'] as String?) ?? '';
      final htmlUrl = (data['html_url'] as String?) ?? '';
      final body = (data['body'] as String?) ?? '';

      final hasUpdate = _isNewer(latestTag, currentVersion);

      return VersionInfo(
        latestVersion: latestTag,
        htmlUrl: htmlUrl,
        releaseNotes: body.isNotEmpty ? body : null,
        hasUpdate: hasUpdate,
      );
    } catch (_) {
      return VersionInfo(latestVersion: currentVersion, htmlUrl: '', hasUpdate: false);
    }
  }
}
