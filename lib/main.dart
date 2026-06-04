import 'package:flutter/material.dart';
import 'app.dart';
import 'services/config_service.dart';
import 'services/i18n.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await ConfigService.instance.load();
  I18N.instance.setLanguage(ConfigService.instance.config.language);
  runApp(const PlaylistAdminApp());
}
