import 'dart:ffi';
import 'dart:io';
import 'package:ffi/ffi.dart';
import 'package:flutter/material.dart';
import 'package:win32/win32.dart';
import 'app.dart';
import 'services/config_service.dart';
import 'services/groq_service.dart';
import 'services/i18n.dart';

int _foundHwnd = 0;

int _enumFindFlutter(int h, int _) {
  final len = GetWindowTextLength(h) + 1;
  final buf = calloc<Uint16>(len);
  GetWindowText(h, buf.cast<Utf16>(), len);
  final title = buf.cast<Utf16>().toDartString();
  calloc.free(buf);
  if (title.contains('Playlist') || title.contains('播放清單')) {
    _foundHwnd = h;
    return FALSE;
  }
  return TRUE;
}

void _bringToFront() {
  _foundHwnd = 0;
  final callback = Pointer.fromFunction<WNDENUMPROC>(_enumFindFlutter, FALSE);
  EnumWindows(callback, 0);
  if (_foundHwnd != 0) {
    if (IsIconic(_foundHwnd) != 0) ShowWindow(_foundHwnd, SW_RESTORE);
    SetForegroundWindow(_foundHwnd);
  }
}

RandomAccessFile? _lockFile;

void _ensureSingleInstance() {
  final lockPath = '${Directory.systemTemp.path}\\PlaylistAdmin.lock';
  try {
    _lockFile = File(lockPath).openSync(mode: FileMode.write);
    _lockFile!.lockSync();
  } catch (_) {
    _bringToFront();
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
