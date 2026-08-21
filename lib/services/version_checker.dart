import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../version.dart';
import 'config_service.dart';

class VersionInfo {
  final String latestVersion;
  final String htmlUrl;
  final String? downloadUrl;
  final String? releaseNotes;
  final bool hasUpdate;

  VersionInfo({
    required this.latestVersion,
    required this.htmlUrl,
    this.downloadUrl,
    this.releaseNotes,
    required this.hasUpdate,
  });
}

class VersionChecker {
  static const _owner = 'thumb2086';
  static const _repo = 'playlist-admin';
  static const _apiUrl = 'https://api.github.com/repos/$_owner/$_repo/releases';

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
    return true;
  }

  /// True if [latest] is newer than the version the user previously skipped.
  static bool isNewerThanSkipped(String latest) {
    final skipped = ConfigService.instance.config.skippedVersion;
    if (skipped.isEmpty) return true;
    return _isNewer(latest, skipped);
  }

  static void markSkipped(String version) {
    ConfigService.instance.config.skippedVersion = version;
    ConfigService.instance.save();
  }

  static Future<VersionInfo> checkForUpdate() async {
    try {
      final token = ConfigService.instance.config.githubToken;
      final headers = <String, String>{'User-Agent': 'playlist-admin/2.0'};
      if (token.isNotEmpty) headers['Authorization'] = 'Bearer $token';
      http.Response? resp;
      // Retry up to 3 times on rate limit (429) or server errors (5xx).
      for (int attempt = 0; attempt < 3; attempt++) {
        resp = await http.get(
          Uri.parse(_apiUrl),
          headers: headers,
        );
        if (resp.statusCode == 200) break;
        if (resp.statusCode == 429 || resp.statusCode >= 500) {
          await Future.delayed(Duration(seconds: 2 * (attempt + 1)));
          continue;
        }
        break; // 4xx (non-429) — don't retry
      }
      if (resp == null || resp.statusCode != 200) {
        return VersionInfo(latestVersion: currentVersion, htmlUrl: '', hasUpdate: false);
      }
      // /releases 回傳陣列，含 Pre-release。
      final List<dynamic> releases = jsonDecode(resp.body) as List<dynamic>;
      if (releases.isEmpty) {
        return VersionInfo(latestVersion: currentVersion, htmlUrl: '', hasUpdate: false);
      }
      // 根據設定過濾 Pre-release。
      final cfg = ConfigService.instance.config;
      final filtered = cfg.receiveBetaUpdates
          ? releases
          : releases.where((r) => (r['prerelease'] as bool?) != true).toList();
      if (filtered.isEmpty) {
        return VersionInfo(latestVersion: currentVersion, htmlUrl: '', hasUpdate: false);
      }
      final data = filtered.first as Map<String, dynamic>;
      final latestTag = (data['tag_name'] as String?) ?? '';
      final htmlUrl = (data['html_url'] as String?) ?? '';
      final body = (data['body'] as String?) ?? '';
      String? downloadUrl;
      final assets = data['assets'] as List<dynamic>?;
      if (assets != null) {
        for (final asset in assets) {
          final name = (asset['name'] as String? ?? '').toLowerCase();
          final ok =
              (name.startsWith('playlist-admin-setup') || name.startsWith('playlistadministrator-setup')) &&
              name.endsWith('.exe');
          if (ok) {
            downloadUrl = asset['browser_download_url'] as String?;
            break;
          }
        }
      }
      return VersionInfo(
        latestVersion: latestTag, htmlUrl: htmlUrl, downloadUrl: downloadUrl,
        releaseNotes: body.isNotEmpty ? body : null,
        hasUpdate: _isNewer(latestTag, currentVersion),
      );
    } catch (_) {
      return VersionInfo(latestVersion: currentVersion, htmlUrl: '', hasUpdate: false);
    }
  }

  /// Download update to temp path, reporting progress 0.0~1.0.
  static Future<String?> downloadUpdate(String url, {void Function(double)? onProgress}) async {
    try {
      final client = http.Client();
      final request = http.Request('GET', Uri.parse(url));
      final response = await client.send(request);
      if (response.statusCode != 200) return null;

      final total = response.contentLength ?? -1;
      if (total > 200 * 1024 * 1024) return null; // 200MB 上限防呆
      final completer = Completer<String?>();
      final tmp = '${Directory.systemTemp.path}\\PlaylistAdmin_Setup_${DateTime.now().microsecondsSinceEpoch}.exe';
      final sink = File(tmp).openWrite();
      int written = 0;
      response.stream.listen(
        (chunk) {
          sink.add(chunk);
          written += chunk.length;
          if (total > 0) onProgress?.call(written / total);
        },
        onDone: () {
          sink.flush().then((_) => sink.close()).then((_) {
            if (written > 0 && (total < 0 || written >= total)) {
              completer.complete(tmp);
            } else {
              try { File(tmp).deleteSync(); } catch (_) {}
              completer.complete(null);
            }
          });
        },
        onError: (e) {
          try { sink.close(); File(tmp).deleteSync(); } catch (_) {}
          completer.complete(null);
        },
        cancelOnError: false,
      );
      return await completer.future;
    } catch (_) {
      return null;
    }
  }
}
