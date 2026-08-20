import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:playlist_admin/services/config_service.dart';
import 'package:playlist_admin/services/jam_service.dart';

/// 驗證「一起聽」房主伺服器 + 成員連線的完整協議（不開 GUI）。
void main() {
  test('jam host: 建立房間、成員加入、聊天、錯誤代碼', () async {
    TestWidgetsFlutterBinding.ensureInitialized();

    // 測試環境沒有原生 plugin，mock 掉 audioplayers 的 method channel。
    for (final channel in ['xyz.luan/audioplayers', 'xyz.luan/audioplayers.global']) {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(MethodChannel(channel), (call) async => null);
    }
    await ConfigService.instance.load();

    final jam = JamService.instance;

    await jam.startHost(name: '房主');
    expect(jam.mode, 'host');
    expect(jam.roomCode.length, 6);
    expect(jam.members.length, 1);
    expect(jam.hostAddress, contains(':'));
    expect(jam.isHost, true);

    // 成員 1：正確代碼加入
    final ws = await WebSocket.connect('ws://${jam.hostAddress}/jam/ws');
    final msgs = <Map<String, dynamic>>[];
    final done1 = Completer<void>();
    ws.listen((raw) {
      final m = jsonDecode(raw as String) as Map<String, dynamic>;
      msgs.add(m);
      if (m['type'] == 'welcome' && !done1.isCompleted) done1.complete();
    });
    ws.add(jsonEncode({'type': 'join', 'code': jam.roomCode, 'name': '小明'}));
    await done1.future.timeout(const Duration(seconds: 3));
    expect(msgs.any((m) => m['type'] == 'welcome'), true, reason: '收到 welcome');
    expect((msgs.first['state']['members'] as List).length, 2, reason: 'state 含 2 個成員');
    expect(jam.members.length, 2, reason: '房主端成員數 = 2');
    expect(jam.members.last['name'], '小明');

    // 成員 2：錯誤代碼被拒
    final ws2 = await WebSocket.connect('ws://${jam.hostAddress}/jam/ws');
    final errs = <String>[];
    ws2.listen((raw) => errs.add(raw as String));
    ws2.add(jsonEncode({'type': 'join', 'code': 'ZZZZZZ', 'name': '壞人'}));
    await Future.delayed(const Duration(milliseconds: 400));
    expect(errs.any((e) => e.contains('房間代碼錯誤')), true, reason: '錯誤代碼被拒');

    // 聊天廣播
    ws.add(jsonEncode({'type': 'chat', 'text': '哈囉大家'}));
    await Future.delayed(const Duration(milliseconds: 400));
    expect(jam.chat.any((c) => (c['text'] as String).contains('哈囉大家')), true,
        reason: '房主收到聊天訊息');
    expect(msgs.any((m) => m['type'] == 'chat_item'), true, reason: '成員收到聊天廣播');

    // 成員離開
    ws.add(jsonEncode({'type': 'leave'}));
    await Future.delayed(const Duration(milliseconds: 400));
    expect(jam.members.length, 1, reason: '成員離開後房主端剩 1 人');

    await ws2.close();
    await ws.close();
    await jam.leaveRoom();
    expect(jam.mode, 'idle');
  }, timeout: const Timeout(Duration(seconds: 20)));

  test('jam audio: Range 串流（手機拖進度用）', () async {
    TestWidgetsFlutterBinding.ensureInitialized();
    for (final channel in ['xyz.luan/audioplayers', 'xyz.luan/audioplayers.global']) {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(MethodChannel(channel), (call) async => null);
    }
    await ConfigService.instance.load();
    final jam = JamService.instance;

    final tmp = File('${Directory.systemTemp.path}/jam_range_test.mp3');
    await tmp.writeAsBytes(List<int>.generate(100000, (i) => i % 251));
    await jam.startHost(name: '房主');

    // flutter_test 會攔截所有 HTTP（一律回 400），這裡還原真實網路。
    HttpOverrides.global = null;
    final client = HttpClient();
    final req = await client.getUrl(Uri.parse(
        'http://127.0.0.1:${jam.port}/jam/audio?f=${Uri.encodeQueryComponent(tmp.path)}'));
    req.headers.set(HttpHeaders.rangeHeader, 'bytes=100-199');
    final resp = await req.close();
    expect(resp.statusCode, 206, reason: 'Range 請求回 206');
    final body = await resp.fold<List<int>>([], (a, b) => a..addAll(b));
    expect(body.length, 100, reason: '回傳 100 bytes');
    expect(resp.headers.value(HttpHeaders.contentRangeHeader), 'bytes 100-199/100000');
    client.close();

    await jam.leaveRoom();
    await tmp.delete();
  }, timeout: const Timeout(Duration(seconds: 20)));

  test('jam client: 成員端連線並接收完整狀態（假房主）', () async {
    TestWidgetsFlutterBinding.ensureInitialized();
    for (final channel in ['xyz.luan/audioplayers', 'xyz.luan/audioplayers.global']) {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(MethodChannel(channel), (call) async => null);
    }
    await ConfigService.instance.load();
    final jam = JamService.instance;

    // 假房主伺服器：模擬相同的 WebSocket 協議。
    final server = await HttpServer.bind(InternetAddress.anyIPv4, 0);
    server.listen((req) async {
      if (req.uri.path != '/jam/ws') {
        req.response.statusCode = 404;
        await req.response.close();
        return;
      }
      final ws = await WebSocketTransformer.upgrade(req);
      ws.listen((raw) {
        final m = jsonDecode(raw as String) as Map<String, dynamic>;
        if (m['type'] == 'join') {
          ws.add(jsonEncode({
            'type': 'welcome',
            'yourId': 'fake-1',
            'state': {
              'code': m['code'],
              'members': [
                {'id': 'fake-host', 'name': '房主', 'isHost': true},
                {'id': 'fake-1', 'name': m['name'], 'isHost': false},
              ],
              'queue': [],
              'current': null,
              'playing': false,
              'pos': 0,
              'ts': 0,
              'chat': [
                {'text': '歡迎光臨', 'ts': 0}
              ],
              'skipVotes': 0,
              'skipNeeded': 1,
              'hostAddress': '127.0.0.1:${server.port}',
            },
          }));
        } else if (m['type'] == 'chat') {
          ws.add(jsonEncode(
              {'type': 'chat_item', 'item': {'text': m['text'], 'ts': 0}}));
        }
      });
    });

    await jam.connect(
        address: '127.0.0.1:${server.port}', code: 'ABC123', name: '手機小明');
    expect(jam.mode, 'client', reason: '切換成成員模式');
    expect(jam.isHost, false);

    await Future.delayed(const Duration(milliseconds: 400));
    expect(jam.members.length, 2, reason: '收到 welcome 後成員視角看到 2 人');
    expect(jam.members.any((m) => m['name'] == '手機小明'), true);
    expect(jam.chat.any((c) => (c['text'] as String).contains('歡迎光臨')), true,
        reason: '收到房主的聊天紀錄');

    jam.sendChat('手機測試');
    await Future.delayed(const Duration(milliseconds: 400));
    expect(jam.chat.any((c) => (c['text'] as String).contains('手機測試')), true,
        reason: '成員送出聊天被假房主回傳');

    await jam.leaveRoom();
    expect(jam.mode, 'idle');
    await server.close(force: true);
  }, timeout: const Timeout(Duration(seconds: 20)));
}