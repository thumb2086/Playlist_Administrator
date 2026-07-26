import 'dart:io';
import 'package:flutter/material.dart';
import 'app.dart';
import 'services/config_service.dart';
import 'services/groq_service.dart';
import 'services/i18n.dart';

RandomAccessFile? _lockFile;

void _ensureSingleInstance() {
  final lockPath = '${Directory.systemTemp.path}\\PlaylistAdmin.lock';
  try {
    _lockFile = File(lockPath).openSync(mode: FileMode.write);
    _lockFile!.lockSync();
  } catch (_) {
    exit(0);
  }
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  _ensureSingleInstance();
  await ConfigService.instance.load();
  await GroqService.instance.loadFromEnv();
  if (GroqService.instance.apiKey != null && GroqService.instance.apiKey!.isNotEmpty) {
    ConfigService.instance.config.groqApiKey = GroqService.instance.apiKey!;
  } else if (ConfigService.instance.config.groqApiKey.isNotEmpty) {
    GroqService.instance.setApiKey(ConfigService.instance.config.groqApiKey);
  }
  I18N.instance.setLanguage(ConfigService.instance.config.language);
  runApp(const PlaylistAdminApp());
}
