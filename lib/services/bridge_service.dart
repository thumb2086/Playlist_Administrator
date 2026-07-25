import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart' show rootBundle;

class BridgeService {
  static final BridgeService _instance = BridgeService._();
  static BridgeService get instance => _instance;
  BridgeService._();

  String? _extractedPath;

  Future<String> get bridgePath async {
    if (_extractedPath != null) return _extractedPath!;

    final tmpDir = Directory.systemTemp.path;
    final targetDir = '$tmpDir\\playlist_admin_tools';
    final bridgeScript = '$targetDir\\flutter_download_bridge.py';

    if (!await File(bridgeScript).exists()) {
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
    }

    _extractedPath = bridgeScript;
    return bridgeScript;
  }
}
