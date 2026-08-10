import 'package:flutter/services.dart';

/// Bridge to the native Windows SMTC controller (system media overlay,
/// media keys). Works only on Windows; no-ops elsewhere.
class SmtcService {
  static final SmtcService instance = SmtcService._();
  SmtcService._();

  static const MethodChannel _channel = MethodChannel('playlist_admin/smtc');

  VoidCallback? _onPlayPause;
  VoidCallback? _onNext;
  VoidCallback? _onPrevious;
  VoidCallback? _onStop;
  bool _attached = false;

  bool get isAttached => _attached;

  /// Register handlers driven by the OS media buttons.
  void attach({
    required VoidCallback onPlayPause,
    required VoidCallback onNext,
    required VoidCallback onPrevious,
    VoidCallback? onStop,
  }) {
    if (_attached) return;
    _attached = true;
    _onPlayPause = onPlayPause;
    _onNext = onNext;
    _onPrevious = onPrevious;
    _onStop = onStop;
    _channel.setMethodCallHandler((call) async {
      switch (call.method) {
        case 'onButton':
          final event = call.arguments as String?;
          switch (event) {
            case 'play_pause':
              _onPlayPause?.call();
              break;
            case 'next':
              _onNext?.call();
              break;
            case 'previous':
              _onPrevious?.call();
              break;
            case 'stop':
              _onStop?.call();
              break;
          }
          break;
      }
      return null;
    });
  }

  /// Push metadata + playback state to the Windows media overlay.
  Future<void> update({
    String? title,
    String? artist,
    String? album,
    bool playing = false,
  }) async {
    if (!_attached) return;
    try {
      await _channel.invokeMethod<void>('update', <String, dynamic>{
        'title': title ?? '',
        'artist': artist ?? '',
        'album': album ?? '',
        'playing': playing,
      });
    } catch (_) {}
  }
}