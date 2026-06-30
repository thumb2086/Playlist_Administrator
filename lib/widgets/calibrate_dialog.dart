import 'dart:ffi';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:ffi/ffi.dart';
import 'package:win32/win32.dart';
import '../services/i18n.dart';
import '../services/config_service.dart';
import '../widgets/dark_theme.dart';

class CalibrateDialog extends StatefulWidget {
  const CalibrateDialog({super.key});
  @override
  State<CalibrateDialog> createState() => _CalibrateDialogState();
}

class _CalibrateDialogState extends State<CalibrateDialog> {
  int _step = 0;
  final _results = <String, List<int>>{};
  final _focusNode = FocusNode();

  static const _targets = [
    ('sidebar_library', 'Sidebar Library 圖示'),
    ('library_filter', '搜尋/篩選欄位'),
    ('first_playlist_card', '第一個播放清單卡片'),
    ('three_dot_menu', '播放清單頁面的三點選單'),
    ('confirm_button', '確認對話框按鈕'),
    ('skip_detect', '偵測點（白色按鈕/文字處）'),
    ('skip', 'Skip 按鈕'),
    ('skip_all', 'Skip All 按鈕'),
  ];

  List<int> _clientOrigin() {
    final callback = Pointer.fromFunction<WNDENUMPROC>(_enumFindSpotube, FALSE);
    _spotubeHwnd = null;
    EnumWindows(callback, 0);
    if (_spotubeHwnd == null) return [0, 0];
    final rect = calloc<RECT>();
    GetWindowRect(_spotubeHwnd!, rect);
    final origin = [rect.ref.left, rect.ref.top];
    calloc.free(rect);
    return origin;
  }

  static int? _spotubeHwnd;
  static int _enumFindSpotube(int h, int param) {
    final len = GetWindowTextLength(h) + 1;
    final buf = calloc<Uint16>(len);
    GetWindowText(h, buf.cast<Utf16>(), len);
    final title = buf.cast<Utf16>().toDartString();
    calloc.free(buf);
    if (title.toLowerCase().contains('spotube')) {
      _spotubeHwnd = h;
      return FALSE;
    }
    return TRUE;
  }

  void _record() {
    final origin = _clientOrigin();
    if (_spotubeHwnd == null) {
      _showError('找不到 Spotube 視窗，請先啟動 Spotube');
      return;
    }
    final pos = calloc<POINT>();
    GetCursorPos(pos);
    final dx = pos.ref.x - origin[0];
    final dy = pos.ref.y - origin[1];
    _results[_targets[_step].$1] = [dx, dy];
    calloc.free(pos);

    final next = _step + 1;
    if (next < _targets.length) {
      setState(() => _step = next);
    } else {
      _saveAndDone();
    }
  }

  void _saveAndDone() {
    final origin = _clientOrigin();
    final pos = calloc<POINT>();
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.card,
        content: const Text('請點擊三點選單，然後將滑鼠移到「Download All」上，按 Enter'),
        actions: [TextButton(onPressed: () {
          GetCursorPos(pos);
          final base = _results['three_dot_menu']!;
          final dx = pos.ref.x - (base[0] + origin[0]);
          final dy = pos.ref.y - (base[1] + origin[1]);
          _results['download_all_offset'] = [dx, dy];
          calloc.free(pos);
          _finish();
        }, child: const Text('確定'))],
      ),
    );
  }

  void _finish() {
    ConfigService.instance.config.spotubeCoords = _results;
    ConfigService.instance.save();
    if (mounted) Navigator.of(context).pop(true);
  }

  void _showError(String msg) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: AppColors.card,
        title: const Text('錯誤'),
        content: Text(msg),
        actions: [TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('確定'))],
      ),
    );
  }

  @override
  void initState() {
    super.initState();
    _focusNode.requestFocus();
  }

  @override
  void dispose() {
    _focusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final target = _targets[_step];
    return KeyboardListener(
      focusNode: _focusNode,
      onKeyEvent: (event) {
        if (event is KeyDownEvent && event.logicalKey == LogicalKeyboardKey.enter) {
          _record();
        }
      },
      child: AlertDialog(
        backgroundColor: AppColors.card,
        title: Text('校準座標 (${_step + 1}/${_targets.length + 1})'),
        content: Column(mainAxisSize: MainAxisSize.min, children: [
          Text('將滑鼠移到「${target.$2}」上'),
          Text('然後按 Enter 記錄', style: TextStyle(color: AppColors.textMuted, fontSize: 12)),
          const SizedBox(height: 12),
          LinearProgressIndicator(value: (_step + 1) / (_targets.length + 1)),
          const SizedBox(height: 8),
          Text('(${_results.length} 個已記錄)', style: TextStyle(color: AppColors.textMuted, fontSize: 11)),
        ]),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('取消')),
        ],
      ),
    );
  }
}
