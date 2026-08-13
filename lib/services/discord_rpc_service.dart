import 'dart:async';
import 'dart:io';

import 'package:flutter_discord_rpc/flutter_discord_rpc.dart';

import 'log_manager.dart';

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
    LogManager.instance.info(
        'DiscordRPC attach enabled=$enabled appId=${applicationId.isNotEmpty ? 'ok' : 'EMPTY'}');

    if (_enabled && applicationId.isNotEmpty) {
      if (!_initialized) {
        try {
          await FlutterDiscordRPC.initialize(applicationId);
          _initialized = true;
          LogManager.instance.info('DiscordRPC initialize OK');
        } catch (e) {
          LogManager.instance.error('DiscordRPC initialize FAILED: $e');
          return;
        }
      }
      if (!_connected) {
        unawaited(
          FlutterDiscordRPC.instance.connect(autoRetry: true).then((_) {
            _connected = true;
            LogManager.instance.info('DiscordRPC connected');
            if (onReady != null) onReady();
            _pump();
          }).catchError((e) {
            _connected = false;
            LogManager.instance.error('DiscordRPC connect FAILED: $e');
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
    Duration? duration,
  }) async {
    if (Platform.isWindows == false) return;
    if (title.isEmpty) return;
    final elapsedMs = position?.inMilliseconds ?? 0;
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    // 播放與暫停都送 start：播放時從現在起算（累計），
    // 暫停時 start = now - 已播 → Discord 顯示的秒數凍結在暫停位置（Spotify 行為）。
    final start = (nowMs - elapsedMs) ~/ 1000;
    final end = duration != null ? (nowMs - elapsedMs + duration.inMilliseconds) ~/ 1000 : null;
    final activity = RPCActivity(
      details: title,
      state: artist,
      assets: RPCAssets(
        largeImage: artworkUrl?.isNotEmpty == true
            ? artworkUrl!
            : "playlist-admin-logo",
        largeText: album ?? '',
      ),
      timestamps: RPCTimestamps(start: start, end: end),
      activityType: ActivityType.listening,
    );
    _pending = activity;
    if (!usable || !_connected) {
      LogManager.instance.info(
          'DiscordRPC update skipped (usable=$usable connected=$_connected) title=$title');
      return;
    }
    if (!FlutterDiscordRPC.instance.isConnected) return;
    try {
      await FlutterDiscordRPC.instance.setActivity(activity: activity);
      LogManager.instance.info('DiscordRPC activity pushed: $title - $artist');
    } catch (e) {
      LogManager.instance.error('DiscordRPC setActivity FAILED: $e');
    }
  }

  /// 連線完成後把最後一次狀態補送（避免連線前播放被吞掉）。
  void _pump() {
    if (!usable || !_connected || _pending == null) return;
    if (!FlutterDiscordRPC.instance.isConnected) return;
    LogManager.instance.info('DiscordRPC connect retry -> push pending');
    try {
      FlutterDiscordRPC.instance.setActivity(activity: _pending!);
    } catch (e) {
      LogManager.instance.error('DiscordRPC pump FAILED: $e');
    }
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