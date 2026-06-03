import 'dart:convert';
import 'dart:io';
import '../models/config_model.dart';

class ConfigService {
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
    }

    config = AppConfig();
  }

  Future<void> save() async {
    if (_configPath == null) return;
    final file = File(_configPath!);
    await file.writeAsString(jsonEncode(config.toJson()));
  }
}
