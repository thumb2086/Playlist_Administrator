import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:webview_windows/webview_windows.dart';
import '../services/spotify_session.dart';
import '../widgets/dark_theme.dart';

/// Spotify login via WebView2: navigates to accounts.spotify.com; when the
/// user finishes logging in and lands on the /status page, captures the
/// spotify.com cookies (including HttpOnly sp_dc) via CDP and stores them
/// into the session.
class SpotifyLoginDialog extends StatefulWidget {
  const SpotifyLoginDialog({super.key});
  @override
  State<SpotifyLoginDialog> createState() => _SpotifyLoginDialogState();
}

class _SpotifyLoginDialogState extends State<SpotifyLoginDialog> {
  final _controller = WebviewController();
  bool _loading = true;
  bool _captured = false;
  StreamSubscription<String>? _urlSub;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    try {
      await _controller.initialize();
      await _controller.setBackgroundColor(Colors.transparent);
      _urlSub = _controller.url.listen((url) {
        if (url.contains('/status') || url.contains('open.spotify.com')) {
          _captureCookies();
        }
      });
      await _controller.loadUrl('https://accounts.spotify.com/login');
      if (mounted) setState(() => _loading = false);
    } catch (e) {
      if (mounted) {
        setState(() => _loading = false);
        ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('無法啟動 WebView: $e')));
      }
    }
  }

  Future<void> _captureCookies() async {
    if (_captured) return;
    _captured = true;
    try {
      final jsonStr = await _controller.getCookiesRaw('https://spotify.com');
      final data = jsonDecode(jsonStr) as Map<String, dynamic>;
      final cookies = (data['cookies'] as List<dynamic>? ?? [])
          .cast<Map<String, dynamic>>();
      String? spDc;
      String? spT;
      for (final c in cookies) {
        if (c['name'] == 'sp_dc') spDc = c['value'] as String?;
        if (c['name'] == 'sp_t') spT = c['value'] as String?;
      }
      if (spDc == null || spDc.isEmpty) {
        _captured = false;
        return;
      }
      await SpotifySession.instance.setCookies(spDc: spDc, spT: spT);
      if (mounted) Navigator.of(context).pop(true);
    } catch (_) {
      _captured = false;
    }
  }

  @override
  void dispose() {
    _urlSub?.cancel();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: AppColors.card,
      title: const Text('Spotify 登入'),
      content: SizedBox(
        width: 520,
        height: 480,
        child: Column(children: [
          const Text('在下方視窗登入你的 Spotify 帳號，登入完成後會自動取得授權。',
              style: TextStyle(fontSize: 12, color: AppColors.textMuted)),
          const SizedBox(height: 10),
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: _loading
                  ? const Center(child: CircularProgressIndicator())
                  : Webview(
                      _controller,
                      permissionRequested: (url, kind, isUserInitiated) =>
                          WebviewPermissionDecision.allow,
                    ),
            ),
          ),
          const SizedBox(height: 10),
          Text('登入後頁面跳轉到 open.spotify.com 即完成（自動）。',
              style: TextStyle(fontSize: 10, color: AppColors.textMuted.withValues(alpha: 0.7))),
        ]),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('取消'),
        ),
      ],
    );
  }
}

/// Opens the login dialog. Returns true if logged in.
/// WebView2 只有 Windows 桌面版才有；其他平台直接提示。
Future<bool> showSpotifyLogin(BuildContext context) async {
  if (!kIsWeb && !Platform.isWindows) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
          content: Text('Spotify 登入僅支援 Windows 桌面版，手機上可加入房主的房間一起聽')),
    );
    return false;
  }
  final ok = await showDialog<bool>(
    context: context,
    builder: (_) => const SpotifyLoginDialog(),
  );
  return ok ?? false;
}