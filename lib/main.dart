import 'package:flutter/material.dart';
import 'app.dart';
import 'services/config_service.dart';
import 'services/groq_service.dart';
import 'services/i18n.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await ConfigService.instance.load();
  await GroqService.instance.loadFromEnv();
  // Override config groqApiKey if .env provides one
  if (GroqService.instance.apiKey != null && GroqService.instance.apiKey!.isNotEmpty) {
    ConfigService.instance.config.groqApiKey = GroqService.instance.apiKey!;
  } else if (ConfigService.instance.config.groqApiKey.isNotEmpty) {
    GroqService.instance.setApiKey(ConfigService.instance.config.groqApiKey);
  }
  I18N.instance.setLanguage(ConfigService.instance.config.language);
  runApp(const PlaylistAdminApp());
}
