import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart' show rootBundle;

class BridgeService {
  static final BridgeService _instance = BridgeService._();
  static BridgeService get instance => _instance;
  BridgeService._();

  String? _extractedPath;
  Future<void>? _pendingExtract;

  Future<String> get bridgePath async {
    if (_extractedPath != null && await File(_extractedPath!).exists()) {
      return _extractedPath!;
    }
    if (_pendingExtract != null) {
      await _pendingExtract;
      return _extractedPath!;
    }
    return _pendingExtract = _resolve();
  }

  Future<String> _resolve() async {
    try {
      return await _extractFromAssets();
    } catch (_) {}

    try {
      final exeDir = File(Platform.resolvedExecutable).parent.path;
      final assetDir = '$exeDir\\data\\flutter_assets\\assets\\tools';
      if (await Directory(assetDir).exists()) {
        return await _copyFromDir(assetDir);
      }
    } catch (_) {}

    try {
      Directory? d = Directory(File(Platform.resolvedExecutable).parent.path);
      while (d != null) {
        final candidate = '${d.path}\\tools\\flutter_download_bridge.py';
        if (File(candidate).existsSync()) {
          return _extractedPath = candidate;
        }
        final parent = d.parent;
        d = parent.path == d.path ? null : parent;
      }
    } catch (_) {}

    final cwd = Directory.current.path;
    final cwdCandidate = '$cwd\\tools\\flutter_download_bridge.py';
    if (File(cwdCandidate).existsSync()) {
      return _extractedPath = cwdCandidate;
    }

    try {
      Directory? d = Directory(File(Platform.resolvedExecutable).parent.path);
      while (d != null) {
        if (File('${d.path}\\pubspec.yaml').existsSync()) {
          final candidate = '${d.path}\\tools\\flutter_download_bridge.py';
          if (File(candidate).existsSync()) {
            return _extractedPath = candidate;
          }
        }
        final parent = d.parent;
        d = parent.path == d.path ? null : parent;
      }
    } catch (_) {}

    throw Exception('找不到 bridge script');
  }

  Future<String> _extractFromAssets() async {
    await rootBundle.loadString('AssetManifest.json');
    final tmpDir = Directory.systemTemp.path;
    final targetDir = '$tmpDir\\playlist_admin_tools';
    final bridgeScript = '$targetDir\\flutter_download_bridge.py';

    if (await File(bridgeScript).exists()) {
      return _extractedPath = bridgeScript;
    }

    await Directory(targetDir).create(recursive: true);
    final manifest = await rootBundle.loadString('AssetManifest.json');
    final assets = (jsonDecode(manifest) as Map<String, dynamic>).keys
        .where((k) => k.startsWith('assets/tools/'));
    for (final asset in assets) {
      final relative = asset.replaceFirst('assets/tools/', '');
      if (relative.isEmpty) continue;
      final data = await rootBundle.load(asset);
      final file = File('$targetDir\\$relative');
      await file.parent.create(recursive: true);
      await file.writeAsBytes(data.buffer.asUint8List());
    }
    return _extractedPath = bridgeScript;
  }

  Future<String> _copyFromDir(String sourceDir) async {
    final tmpDir = Directory.systemTemp.path;
    final targetDir = '$tmpDir\\playlist_admin_tools';
    final bridgeScript = '$targetDir\\flutter_download_bridge.py';

    if (await File(bridgeScript).exists()) {
      return _extractedPath = bridgeScript;
    }

    await Directory(targetDir).create(recursive: true);
    await for (final f in Directory(sourceDir).list()) {
      if (f is File) {
        await f.copy('$targetDir\\${f.uri.pathSegments.last}');
      }
    }
    return _extractedPath = bridgeScript;
  }
}
