import 'dart:convert';
import 'dart:ffi';
import 'dart:io' hide sleep;
import 'package:ffi/ffi.dart';
import 'package:win32/win32.dart';

int _enumFindSpotube(int hwnd, int param) {
  final len = GetWindowTextLength(hwnd) + 1;
  final buffer = calloc<Uint16>(len);
  GetWindowText(hwnd, buffer.cast<Utf16>(), len);
  final title = buffer.cast<Utf16>().toDartString();
  calloc.free(buffer);
  if (title.toLowerCase().contains('spotube')) {
    _spotubeHwnd = hwnd;
    return FALSE;
  }
  return TRUE;
}

int? _spotubeHwnd;

class SpotubeController {
  int? _prevHwnd;
  final Map<String, List<int>> _coords;
  final String libraryPath;
  final String? exePath;
  bool _aborted = false;
  static const _stateFile = 'spotube_download_state.json';
  static Map<String, String> _loadState() {
    try {
      final f = File('${Platform.environment['LOCALAPPDATA'] ?? ''}\\Playlist Administrator\\data\\$_stateFile');
      if (f.existsSync()) return Map<String, String>.from(jsonDecode(f.readAsStringSync()) as Map);
    } catch (_) {}
    return {};
  }
  static void _saveState(Map<String, String> state) {
    try {
      final f = File('${Platform.environment['LOCALAPPDATA'] ?? ''}\\Playlist Administrator\\data\\$_stateFile');
      f.parent.createSync(recursive: true);
      f.writeAsStringSync(jsonEncode(state), flush: true);
    } catch (_) {}
  }

  static const _defaultCoords = {
    'sidebar_library': [30, 280],
    'library_filter': [200, 100],
    'first_playlist_card': [100, 240],
    'three_dot_menu': [1300, 140],
    'download_all_offset': [-30, 30],
    'confirm_button': [960, 600],
    'skip_detect': [960, 600],
    'skip': [960, 600],
    'skip_all': [960, 600],
  };

  SpotubeController({required this.libraryPath, Map<String, List<int>>? coords, this.exePath})
      : _coords = coords ?? {};

  void abort() { _aborted = true; }
  bool get isAborted => _aborted;

  Future<bool> launch() async {
    if (isRunning()) return true;
    if (exePath == null || exePath!.isEmpty) return false;
    final exe = File(exePath!);
    if (!await exe.exists()) return false;
    try {
      Process.start(exe.path, [], runInShell: true);
      for (int i = 0; i < 30; i++) {
        await Future.delayed(const Duration(seconds: 1));
        if (isRunning()) return true;
      }
    } catch (_) {}
    return false;
  }

  static bool isDownloaded(String name) {
    final state = _loadState();
    return state.containsKey(name);
  }

  static void markDownloaded(String name) {
    final state = _loadState();
    state[name] = DateTime.now().toIso8601String();
    _saveState(state);
  }

  static void resetAllDownloads() {
    _saveState({});
  }

  List<int> _coord(String key) => _coords[key] ?? (_defaultCoords[key] ?? [0, 0]);

  List<int> _absolute(String key) {
    final c = _coord(key);
    final origin = _clientOrigin();
    return [origin[0] + c[0], origin[1] + c[1]];
  }

  int? get hwnd {
    _spotubeHwnd = null;
    final callback = Pointer.fromFunction<WNDENUMPROC>(_enumFindSpotube, FALSE);
    EnumWindows(callback, 0);
    return _spotubeHwnd;
  }

  bool isRunning() => hwnd != null;

  List<int> _clientOrigin() {
    final h = hwnd;
    if (h == null) return [0, 0];
    final rect = calloc<RECT>();
    GetWindowRect(h, rect);
    final origin = [rect.ref.left, rect.ref.top];
    calloc.free(rect);
    return origin;
  }

  void activate() {
    _prevHwnd = GetForegroundWindow();
    final h = hwnd;
    if (h == null) throw Exception('Spotube not found');
    if (IsIconic(h) != 0) ShowWindow(h, SW_RESTORE);
    SetForegroundWindow(h);
    _aWait(300);
  }

  void restorePrevious() {
    if (_prevHwnd != null && IsWindow(_prevHwnd!) != 0) {
      SetForegroundWindow(_prevHwnd!);
    }
    _prevHwnd = null;
  }

  void maximize() {
    final h = hwnd;
    if (h != null) ShowWindow(h, SW_MAXIMIZE);
  }

  void minimize() {
    final h = hwnd;
    if (h != null) ShowWindow(h, SW_MINIMIZE);
  }

  void click(int x, int y) {
    SetCursorPos(x, y);
    _aWait(50);
    _sendClick(x, y);
    _aWait(200);
  }

  void _sendClick(int x, int y) {
    final input = calloc<INPUT>(1);
    input.ref.type = INPUT_MOUSE;
    input.ref.mi.dwFlags = MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_LEFTUP;
    input.ref.mi.dx = x;
    input.ref.mi.dy = y;
    SendInput(1, input, sizeOf<INPUT>());
    calloc.free(input);
  }

  void doubleClick(int x, int y) {
    click(x, y);
    _aWait(100);
    click(x, y);
    _aWait(300);
  }

  void sendChars(String text) {
    for (final ch in text.codeUnits) {
      if (_aborted) return;
      final h = hwnd;
      if (h != null) {
        SendMessage(h, WM_CHAR, ch, 0);
        SendMessage(h, WM_KEYUP, ch, 0);
      }
      _aWait(30);
    }
  }

  void sendBackspaces(int count) {
    for (int i = 0; i < count; i++) {
      if (_aborted) return;
      final h = hwnd;
      if (h != null) {
        SendMessage(h, WM_KEYDOWN, VK_BACK, 0);
        SendMessage(h, WM_CHAR, 0x08, 0);
        SendMessage(h, WM_KEYUP, VK_BACK, 0);
      }
      _aWait(20);
    }
  }

  void sendSelectAll() {
    final h = hwnd;
    if (h != null) {
      SendMessage(h, WM_KEYDOWN, VK_LCONTROL, 0);
      SendMessage(h, WM_KEYDOWN, 0x41, 0); // 'A'
      SendMessage(h, WM_KEYUP, 0x41, 0);
      SendMessage(h, WM_KEYUP, VK_LCONTROL, 0);
    }
    _aWait(100);
  }

  void sendEscape() {
    final h = hwnd;
    if (h != null) {
      SendMessage(h, WM_KEYDOWN, VK_ESCAPE, 0);
      SendMessage(h, WM_KEYUP, VK_ESCAPE, 0);
    }
    _aWait(100);
  }

  int pixelBrightness(int x, int y) {
    final dc = GetDC(0);
    final pixel = GetPixel(dc, x, y);
    ReleaseDC(0, dc);
    final r = pixel & 0xFF;
    final g = (pixel >> 8) & 0xFF;
    final b = (pixel >> 16) & 0xFF;
    return (r + g + b) ~/ 3;
  }

  void clickSidebarLibrary() {
    final pos = _absolute('sidebar_library');
    click(pos[0], pos[1]);
  }

  void filterPlaylists(String name) {
    final pos = _absolute('library_filter');
    click(pos[0], pos[1]);
    _aWait(200);
    sendSelectAll();
    _aWait(100);
    sendChars(name);
  }

  void clickFirstPlaylist() {
    final pos = _absolute('first_playlist_card');
    doubleClick(pos[0], pos[1]);
  }

  void clickThreeDot() {
    final pos = _absolute('three_dot_menu');
    click(pos[0], pos[1]);
  }

  void clickDownloadAll() {
    final base = _absolute('three_dot_menu');
    final offset = _coord('download_all_offset');
    click(base[0] + offset[0], base[1] + offset[1]);
  }

  void clickConfirm() {
    final pos = _absolute('confirm_button');
    click(pos[0], pos[1]);
  }

  void clickSkip() {
    final pos = _absolute('skip');
    click(pos[0], pos[1]);
  }

  void clickSkipAll() {
    final pos = _absolute('skip_all');
    click(pos[0], pos[1]);
  }

  bool hasSkipDialog() {
    final pos = _absolute('skip_detect');
    return pixelBrightness(pos[0], pos[1]) > 200;
  }

  bool _checkAborted() {
    if (_aborted) {
      sendEscape();
      restorePrevious();
      return true;
    }
    return false;
  }

  Future<void> downloadPlaylist(String name) async {
    if (_checkAborted()) return;
    if (!isRunning()) throw Exception('Spotube is not running');
    maximize();
    activate();
    if (_checkAborted()) return;
    clickSidebarLibrary();
    await _wait(800);
    if (_checkAborted()) return;
    filterPlaylists(name);
    await _wait(1500);
    if (_checkAborted()) return;
    clickFirstPlaylist();
    await _wait(2000);
    if (_checkAborted()) return;
    clickThreeDot();
    await _wait(800);
    if (_checkAborted()) return;
    clickDownloadAll();
    await _wait(800);
    if (_checkAborted()) return;
    clickConfirm();
    await _wait(2000);
    if (_checkAborted()) return;
    if (hasSkipDialog()) {
      clickSkip();
      await _wait(300);
      clickSkipAll();
    }
    minimize();
    restorePrevious();
  }

  Future<int> moveDownloads() async {
    final userProfile = Platform.environment['USERPROFILE'] ?? 'C:\\Users\\Default';
    final src = '$userProfile\\Downloads\\Spotube';
    final dst = '$libraryPath\\m4a';
    final srcDir = Directory(src);
    if (!await srcDir.exists()) return 0;
    await Directory(dst).create(recursive: true);
    int moved = 0;
    await for (final entity in srcDir.list(recursive: true)) {
      if (_aborted) break;
      if (entity is File && RegExp(r'\.(m4a|mp3|flac|wav|webm)$', caseSensitive: false).hasMatch(entity.path)) {
        final name = entity.uri.pathSegments.last;
        final target = File('$dst\\$name');
        if (!await target.exists()) {
          await entity.rename(target.path);
          moved++;
        }
      }
    }
    return moved;
  }
}

void _aWait(int ms) {
  final stopwatch = Stopwatch()..start();
  while (stopwatch.elapsedMilliseconds < ms) {}
}

Future<void> _wait(int ms) => Future.delayed(Duration(milliseconds: ms));
