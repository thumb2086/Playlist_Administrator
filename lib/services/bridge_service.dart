import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart' show rootBundle;

class BridgeService {
  static final BridgeService _instance = BridgeService._();
  static BridgeService get instance => _instance;
  BridgeService._();

  Future<String> get bridgePath async {
    // Try 1: extract from Flutter assets (GUI mode)
    try {
      await rootBundle.loadString('AssetManifest.json');
      return await _extractFromAssets();
    } catch (_) {}

    // Try 2: exe-relative data/flutter_assets/assets/tools/ (release build)
    try {
      final exeDir = File(Platform.resolvedExecutable).parent.path;
      final assetDir = '$exeDir\\data\\flutter_assets\\assets\\tools';
      if (await Directory(assetDir).exists()) {
        return await _copyFromDir(assetDir);
      }
    } catch (_) {}

    // Try 3: walk up from exe (dev layout)
    try {
      Directory? d = Directory(File(Platform.resolvedExecutable).parent.path);
      while (d != null) {
        final candidate = '${d.path}\\tools\\flutter_download_bridge.py';
        if (File(candidate).existsSync()) return candidate;
        final parent = d.parent;
        d = parent.path == d.path ? null : parent;
      }
    } catch (_) {}

    // Try 4: current directory
    final cwd = Directory.current.path;
    final cwdCandidate = '$cwd\\tools\\flutter_download_bridge.py';
    if (File(cwdCandidate).existsSync()) return cwdCandidate;

    throw Exception('找不到 bridge script');
  }

  Future<String> _extractFromAssets() async {
    final tmpDir = Directory.systemTemp.path;
    final targetDir = '$tmpDir\\playlist_admin_tools';
    // Always re-extract to get latest files from embedded assets
    if (await Directory(targetDir).exists()) {
      await Directory(targetDir).delete(recursive: true);
    }
    final bridgeScript = '$targetDir\\flutter_download_bridge.py';
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
    return bridgeScript;
  }

  Future<String> _copyFromDir(String sourceDir) async {
    final tmpDir = Directory.systemTemp.path;
    final targetDir = '$tmpDir\\playlist_admin_tools';
    if (await Directory(targetDir).exists()) {
      await Directory(targetDir).delete(recursive: true);
    }
    final bridgeScript = '$targetDir\\flutter_download_bridge.py';
    await Directory(targetDir).create(recursive: true);
    await for (final f in Directory(sourceDir).list()) {
      if (f is File) {
        await f.copy('$targetDir\\${f.uri.pathSegments.last}');
      }
    }
    return bridgeScript;
  }
}
