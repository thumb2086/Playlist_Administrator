import 'dart:async';
import 'dart:io';

import 'package:flutter_discord_rpc/flutter_discord_rpc.dart';

/// Discord Rich Presence bridge（仿 Spotube 的 discord_provider.dart 邏輯）。
/// 需先在 config 設定 discord_application_id（Discord Developer Portal 申請）
/// 與 discord_presence_enabled = true。
class DiscordRpcService {
  static final DiscordRpcService instance = DiscordRpcService._();
  DiscordRpcService._();

  bool _initialized = false;
  bool _enabled = false;
  bool _connected = false;
  RPCActivity? _pending;

  bool get usable => _initialized && _enabled;

  Future<void> attach({
    required bool enabled,
    required String applicationId,
    void Function()? onReady,
  }) async {
    if (Platform.isWindows == false) return;
    if (enabled == _enabled && _initialized) {
      if (onReady != null && _connected) onReady();
      return;
    }

    _enabled = enabled;

    if (_enabled && applicationId.isNotEmpty) {
      if (!_initialized) {
        try {
          await FlutterDiscordRPC.initialize(applicationId);
          _initialized = true;
        } catch (_) {
          return;
        }
      }
      if (!_connected) {
        unawaited(
          FlutterDiscordRPC.instance.connect(autoRetry: true).then((_) {
            _connected = true;
            if (onReady != null) onReady();
            _pump();
          }).catchError((_) {
            _connected = false;
          }),
        );
      }
    } else if (!_enabled) {
      if (_initialized && FlutterDiscordRPC.instance.isConnected) {
        await FlutterDiscordRPC.instance.clearActivity();
        await FlutterDiscordRPC.instance.disconnect();
        _connected = false;
      }
    }
  }

  /// 推送播放狀態到 Discord（details=歌名, state=藝人, listening）。
  Future<void> update({
    required String title,
    required String artist,
    String? album,
    String? artworkUrl,
    bool playing = false,
    Duration? position,
  }) async {
    if (Platform.isWindows == false) return;
    if (title.isEmpty) return;
    final activity = RPCActivity(
      details: title,
      state: artist,
      assets: RPCAssets(
        largeImage: artworkUrl?.isNotEmpty == true
            ? artworkUrl!
            : "playlist-admin-logo",
        largeText: album ?? '',
      ),
      timestamps: RPCTimestamps(
        start: playing
            ? DateTime.now().millisecondsSinceEpoch -
                (position?.inMilliseconds ?? 0)
            : null,
      ),
      activityType: ActivityType.listening,
    );
    _pending = activity;
    if (!usable || !_connected) return;
    if (!FlutterDiscordRPC.instance.isConnected) return;
    try {
      await FlutterDiscordRPC.instance.setActivity(activity: activity);
    } catch (_) {}
  }

  /// 連線完成後把最後一次狀態補送（避免連線前播放被吞掉）。
  void _pump() {
    if (!usable || !_connected || _pending == null) return;
    if (!FlutterDiscordRPC.instance.isConnected) return;
    try {
      FlutterDiscordRPC.instance.setActivity(activity: _pending!);
    } catch (_) {}
  }

  Future<void> clear() async {
    _pending = null;
    if (!usable) return;
    try {
      if (FlutterDiscordRPC.instance.isConnected) {
        await FlutterDiscordRPC.instance.clearActivity();
      }
    } catch (_) {}
  }

  Future<void> dispose() async {
    if (!_initialized) return;
    try {
      await FlutterDiscordRPC.instance.clearActivity();
      await FlutterDiscordRPC.instance.disconnect();
      await FlutterDiscordRPC.instance.dispose();
    } catch (_) {}
    _initialized = false;
    _connected = false;
  }
}