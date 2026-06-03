import 'package:flutter/material.dart';
import 'app.dart';
import 'services/config_service.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await ConfigService.instance.load();
  runApp(const PlaylistAdminApp());
}
