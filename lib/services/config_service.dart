import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import '../models/config_model.dart';

class ConfigService extends ChangeNotifier {
  ConfigService._();
  static final ConfigService instance = ConfigService._();

  late AppConfig config;
  String? _configPath;

  String get _appDataDir {
    final localAppData = Platform.environment['LOCALAPPDATA'] ?? 
        '${Platform.environment['USERPROFILE'] ?? 'C:\\Users\\Default'}\\AppData\\Local';
    return '$localAppData\\Playlist Administrator\\data';
  }

  Future<void> load() async {
    final localDir = Directory(_appDataDir);
    final localFile = File('${localDir.path}\\config.json');

    if (await localFile.exists()) {
      try {
        final data = jsonDecode(await localFile.readAsString()) as Map<String, dynamic>;
        final basePath = data['base_path'] as String?;
        if (basePath != null && basePath.isNotEmpty) {
          final mainFile = File('$basePath\\config.json');
          if (await mainFile.exists()) {
            _configPath = mainFile.path;
            config = AppConfig.fromJson(jsonDecode(await mainFile.readAsString()) as Map<String, dynamic>);
            config.basePath = basePath;
            return;
          }
        }
      } catch (_) {}
    }

    config = AppConfig();
    _configPath = null;
    notifyListeners();
  }

  Future<void> save() async {
    final cfg = config;
    final basePath = cfg.basePath;

    String savePath;
    if (_configPath != null) {
      savePath = _configPath!;
    } else if (basePath.isNotEmpty) {
      await Directory(basePath).create(recursive: true);
      savePath = '$basePath\\config.json';
      _configPath = savePath;

      final pointerDir = Directory(_appDataDir);
      await pointerDir.create(recursive: true);
      final pointerFile = File('${pointerDir.path}\\config.json');
      await pointerFile.writeAsString(jsonEncode({
        'base_path': basePath,
        'language': cfg.language,
      }));
    } else {
      return;
    }

    await File(savePath).writeAsString(jsonEncode(cfg.toJson()));
    notifyListeners();
  }
}
