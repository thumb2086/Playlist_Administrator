import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:flutter/foundation.dart';
import '../services/config_service.dart';
import '../services/player_controller.dart';
import '../services/spotify_session.dart';
import '../services/spotify_gql_client.dart';
import '../services/stream_server.dart';

/// 「一起聽」— 免註冊的免費 Spotify Jam。
///
/// 任何裝置都可以當房主（Host）：開房間 → 本機開 WebSocket + HTTP 音訊
/// 伺服器，大家透過同一個 Wi-Fi 加入。成員從房主串流歌曲、共享同一個
/// 佇列、即時同步播放進度、投票跳歌、聊天。
///
/// - Host 模式：dart:io 自架伺服器，用本機 PlayerController 播放，
///   把歌曲解析成本機檔案（local）或串流（stream）URL 給成員。
/// - Client 模式：連到房主，收到狀態快照後用 PlayerController 播放
///   房主提供的 URL，並每幾秒做 drift 校正。
class JamService extends ChangeNotifier {
  JamService._();
  static final JamService instance = JamService._();

  // ---------- 公開狀態 ----------
  String mode = 'idle'; // 'idle' | 'host' | 'client'
  String roomCode = '';
  String myId = '';
  String myName = '';
  String hostAddress = ''; // 房主的 ip:port
  bool get isHost => mode == 'host';

  final List<Map<String, dynamic>> members = [];
  final List<Map<String, dynamic>> queue = [];
  Map<String, dynamic>? current;
  bool playing = false;
  int positionMs = 0;
  int ts = 0; // 伺服器時間戳（ms），配合 positionMs 做 drift 校正
  final List<Map<String, dynamic>> chat = [];
  int skipVotes = 0;
  int skipNeeded = 0;

  String lastError = '';
  String statusText = '';

  // 成員本機記錄自己的投票（host 只廣播總票數）
  final Map<String, int> _myVotes = {};

  // 給 UI 用來存當下搜尋結果（client 模式由 host 回傳）
  List<Map<String, dynamic>> searchResults = [];
  bool searching = false;
  String searchError = '';
  int _searchReqId = 0;
  final Map<int, Completer<List<Map<String, dynamic>>>> _searchCompleters = {};

  // ---------- Host 內部 ----------
  HttpServer? _server;
  int _port = 0;
  String _lanIp = '127.0.0.1';
  final Map<String, WebSocket> _clients = {}; // memberId -> ws
  final Map<String, String> _clientNames = {};
  Timer? _hostBcastTimer;
  List<File>? _libraryIndex;
  final Map<String, int> _trackVotes = {}; // trackId -> {memberId: vote}
  final Map<String, Map<String, int>> _voteMap = {};
  bool _hostEndedHandled = false;

  // ---------- Client 內部 ----------
  WebSocket? _ws;
  Timer? _driftTimer;
  String _lastUrl = '';

  String get port => _port.toString();
  String get inviteText => hostAddress;
  int get memberCount => members.length;

  // ===================================================================
  //  生命週期
  // ===================================================================

  /// 房主：建立房間並開始伺服器。
  Future<void> startHost({String name = '我'}) async {
    await leaveRoom();
    mode = 'idle';
    myName = name;
    roomCode = _genCode();
    _lanIp = await _lanIpv4();
    lastError = '';
    statusText = '啟動房間…';

    try {
      // 讓 StreamServer 先開好（成員串流用），綁 anyIPv4。
      await StreamServer.instance.start();
      StreamServer.instance.publicBase =
          'http://$_lanIp:${StreamServer.instance.port}';

      _server = await HttpServer.bind(InternetAddress.anyIPv4, 0);
      _port = _server!.port;
      _server!.listen(_onHttpRequest);

      // 房主自己就是第一個成員。
      _clients.clear();
      _clientNames.clear();
      myId = 'host-${DateTime.now().millisecondsSinceEpoch.toRadixString(16)}';
      _resetRoomState();
      members.add({'id': myId, 'name': myName, 'isHost': true});

      hostAddress = '$_lanIp:$_port';
      mode = 'host';
      PlayerController.instance.jamFollowMode = false;
      // jam 房間的佇列由本服務掌管；清掉本機舊佇列避免 onPlayerComplete 誤切歌。
      PlayerController.instance.clearQueue();

      // 建立音樂庫索引（找本機檔案用）。
      _buildLibraryIndex();

      // 監聽房主的播放完成 → 自動下一首。
      _hostEndedHandled = false;
      PlayerController.instance.player.stream.completed.listen((_) {
        if (mode != 'host' || _hostEndedHandled) return;
        _hostEndedHandled = true;
        Timer(const Duration(milliseconds: 300), () {
          _hostEndedHandled = false;
          if (mode == 'host') _hostNext();
        });
      });

      // 每秒廣播播放進度。
      _hostBcastTimer?.cancel();
      _hostBcastTimer = Timer.periodic(const Duration(seconds: 1), (_) {
        if (mode != 'host') return;
        final pc = PlayerController.instance;
        if (!pc.isPlaying) return;
        _broadcast({
          'type': 'playback',
          'playing': true,
          'pos': pc.position.inMilliseconds,
          'ts': DateTime.now().millisecondsSinceEpoch,
        });
        positionMs = pc.position.inMilliseconds;
        ts = DateTime.now().millisecondsSinceEpoch;
      });

      statusText = '';
      notifyListeners();
    } catch (e) {
      lastError = '啟動失敗: $e';
      statusText = lastError;
      notifyListeners();
      rethrow;
    }
  }

  /// 成員：連到房主。
  Future<void> connect({required String address, required String code, String name = '我'}) async {
    await leaveRoom();
    myName = name;
    mode = 'idle';
    lastError = '';
    statusText = '連線中…';

    final host = address.trim();
    if (!host.contains(':')) {
      lastError = '請輸入房主的 IP:埠口，例如 192.168.1.5:12345';
      statusText = lastError;
      notifyListeners();
      return;
    }

    try {
      final ws = await WebSocket.connect('ws://$host/jam/ws').timeout(
          const Duration(seconds: 8));
      _ws = ws;
      mode = 'client';
      hostAddress = host;
      PlayerController.instance.jamFollowMode = true;
      PlayerController.instance.clearQueue();
      ws.listen(_onClientMessage,
          onDone: _onClientClosed, onError: (e) => _onClientClosed());

      ws.add(jsonEncode({'type': 'join', 'code': code.trim().toUpperCase(), 'name': name}));
      statusText = '';
      notifyListeners();
    } catch (e) {
      mode = 'idle';
      PlayerController.instance.jamFollowMode = false;
      lastError = '連線失敗: $e';
      statusText = lastError;
      notifyListeners();
    }
  }

  /// 離開房間（host 或 client 通用）。
  Future<void> leaveRoom() async {
    _hostBcastTimer?.cancel();
    _hostBcastTimer = null;
    _driftTimer?.cancel();
    _driftTimer = null;
    if (mode == 'client') {
      try { _ws?.add(jsonEncode({'type': 'leave'})); } catch (_) {}
      try { await _ws?.close(); } catch (_) {}
    }
    if (mode == 'host') {
      try {
        _broadcast({'type': 'room_closed'});
        for (final ws in _clients.values) {
          try { await ws.close(); } catch (_) {}
        }
      } catch (_) {}
    }
    _ws = null;
    _server = null;
    _clients.clear();
    _clientNames.clear();
    _resetRoomState();
    mode = 'idle';
    _myVotes.clear();
    searchResults = [];
    searchError = '';
    searching = false;
    PlayerController.instance.jamFollowMode = false;
    _lastUrl = '';
    notifyListeners();
  }

  void _resetRoomState() {
    members.clear();
    queue.clear();
    current = null;
    playing = false;
    positionMs = 0;
    ts = 0;
    chat.clear();
    skipVotes = 0;
    skipNeeded = 0;
    _trackVotes.clear();
    _voteMap.clear();
  }

  // ===================================================================
  //  Host：HTTP + WebSocket 伺服器
  // ===================================================================

  Future<void> _onHttpRequest(HttpRequest req) async {
    final path = req.uri.path;
    try {
      if (path == '/jam/ws') {
        final ws = await WebSocketTransformer.upgrade(req);
        _handleClientSocket(ws);
      } else if (path == '/jam/audio') {
        final f = req.uri.queryParameters['f'];
        if (f == null || f.isEmpty) {
          req.response.statusCode = HttpStatus.badRequest;
          await req.response.close();
          return;
        }
        await _serveAudioFile(req, f);
      } else {
        req.response.statusCode = HttpStatus.notFound;
        await req.response.close();
      }
    } catch (_) {
      try {
        req.response.statusCode = HttpStatus.internalServerError;
        await req.response.close();
      } catch (_) {}
    }
  }

  Future<void> _handleClientSocket(WebSocket ws) async {
    String? memberId;
    late StreamSubscription<dynamic> sub;
    sub = ws.listen((raw) async {
      Map<String, dynamic>? msg;
      try {
        msg = jsonDecode(raw as String) as Map<String, dynamic>;
      } catch (_) {
        return;
      }
      final type = msg['type'] as String?;

      if (type == 'join') {
        final name = (msg['name'] as String? ?? '你').toString();
        final code = (msg['code'] as String? ?? '').toString().toUpperCase();
        if (code != roomCode) {
          _send(ws, {'type': 'error', 'message': '房間代碼錯誤'});
          return;
        }
        if (_clients.length >= 30) {
          _send(ws, {'type': 'error', 'message': '房間已滿'});
          return;
        }
        final mid = 'm-${DateTime.now().millisecondsSinceEpoch.toRadixString(16)}-${Random().nextInt(9999)}';
        memberId = mid;
        _clients[mid] = ws;
        _clientNames[mid] = name;
        members.add({'id': mid, 'name': name, 'isHost': false});
        _send(ws, {'type': 'welcome', 'yourId': mid, 'state': _stateJson()});
        _broadcast({'type': 'member_joined', 'member': {'id': mid, 'name': name, 'isHost': false}});
        _broadcastSkipCount();
        return;
      }

      if (memberId == null) return;

      switch (type) {
        case 'add':
          _hostAddTrack(msg['track'], memberId!);
          break;
        case 'remove':
          if (memberId != myId) return;
          _hostRemoveTrack(msg['trackId']);
          break;
        case 'vote':
          _hostVote(msg['trackId'], memberId!, msg['delta']);
          break;
        case 'skip':
          _hostSkip(memberId!);
          break;
        case 'play':
          _hostPlayPause(true);
          break;
        case 'pause':
          _hostPlayPause(false);
          break;
        case 'seek':
          _hostSeek(msg['pos']);
          break;
        case 'next':
          if (memberId == myId) _hostNext();
          break;
        case 'prev':
          if (memberId == myId) _hostPrev();
          break;
        case 'chat':
          _hostChat(memberId!, msg['text']);
          break;
        case 'search':
          _hostSearch(memberId!, msg['q'], msg['reqId']);
          break;
        case 'leave':
          if (memberId != null) _removeClient(memberId!);
          sub.cancel();
          break;
      }
    }, onDone: () {
      if (memberId != null) _removeClient(memberId!);
    }, onError: (_) {
      if (memberId != null) _removeClient(memberId!);
    });
  }

  void _send(WebSocket ws, Map<String, dynamic> msg) {
    try {
      ws.add(jsonEncode(msg));
    } catch (_) {}
  }

  void _broadcast(Map<String, dynamic> msg) {
    final data = jsonEncode(msg);
    for (final ws in _clients.values) {
      try {
        ws.add(data);
      } catch (_) {}
    }
  }

  void _removeClient(String memberId) {
    if (!_clients.containsKey(memberId)) return;
    _clients.remove(memberId);
    _clientNames.remove(memberId);
    members.removeWhere((m) => m['id'] == memberId);
    _voteMap.removeWhere((_, v) => v.remove(memberId) != null);
    _broadcast({'type': 'member_left', 'memberId': memberId});
    _broadcastSkipCount();
    _syncQueueVotes();
  }

  // ---------- Host 歌曲處理 ----------

  void _hostAddTrack(dynamic raw, String memberId) {
    final t = raw as Map<String, dynamic>?;
    if (t == null) return;
    final title = (t['title'] ?? '未知歌曲').toString().trim();
    if (title.isEmpty) return;
    final artist = (t['artist'] ?? '').toString();
    final query = '$title - $artist';
    final localPath = _findLibraryFile(query);

    final track = <String, dynamic>{
      'id': 't-${DateTime.now().millisecondsSinceEpoch.toRadixString(16)}${Random().nextInt(9999)}',
      'title': title,
      'artist': artist,
      'coverUrl': t['coverUrl'],
      'isrc': t['isrc'],
      'kind': localPath != null ? 'local' : 'stream',
      'ref': localPath ?? query,
      'addedBy': _clientNames[memberId] ?? '你',
      'votes': 0,
    };
    queue.add(track);
    _voteMap[track['id']] = {};
    _broadcastQueue();
    if (current == null) {
      _hostPlayIndex(0);
    } else {
      _broadcastChat('➕ ${track['addedBy']} 加入了「$title」');
    }
  }

  void _hostRemoveTrack(String? trackId) {
    if (trackId == null) return;
    final idx = queue.indexWhere((t) => t['id'] == trackId);
    if (idx < 0) return;
    queue.removeAt(idx);
    _voteMap.remove(trackId);
    _broadcastQueue();
  }

  void _hostVote(String? trackId, String memberId, dynamic delta) {
    if (trackId == null) return;
    final track = queue.firstWhere((t) => t['id'] == trackId, orElse: () => const {});
    if (track.isEmpty) return;
    final votes = _voteMap[trackId] ??= {};
    final d = (delta == 1 || delta == -1) ? delta as int : 0;
    if (votes[memberId] == d) {
      votes.remove(memberId);
    } else {
      votes[memberId] = d;
    }
    track['votes'] = votes.values.fold<int>(0, (a, b) => a + b);
    _broadcastQueue();
  }

  void _syncQueueVotes() {
    for (final t in queue) {
      final votes = _voteMap[t['id']] ?? {};
      t['votes'] = votes.values.fold<int>(0, (a, b) => a + b);
    }
    _broadcastQueue();
  }

  void _hostSkip(String memberId) {
    if (current == null) return;
    final needed = max(1, (members.length / 2).ceil());
    final cur = current!;
    if (cur['_skip'] == true) {
      cur['_skip'] = false;
      skipVotes--;
    } else {
      cur['_skip'] = true;
      skipVotes++;
    }
    _broadcastSkipCount();
    if (skipVotes >= needed) {
      _broadcastChat('⏭️ 大家決定跳過，下一首！');
      _hostNext();
    }
  }

  void _broadcastSkipCount() {
    skipNeeded = max(1, (members.length / 2).ceil());
    _broadcast({'type': 'skip_count', 'count': skipVotes, 'needed': skipNeeded});
  }

  void _hostPlayPause(bool play) {
    if (current == null) return;
    final pc = PlayerController.instance;
    if (play) {
      pc.resume();
    } else {
      pc.pause();
    }
  }

  void _hostSeek(dynamic pos) {
    if (current == null) return;
    final ms = (pos is num) ? pos.toInt() : 0;
    PlayerController.instance.seek(Duration(milliseconds: ms));
  }

  void _hostPlayIndex(int index) {
    if (index < 0 || index >= queue.length) return;
    current = queue[index];
    current!['_skip'] = false;
    skipVotes = 0;
    _broadcastSkipCount();
    playing = true;
    positionMs = 0;
    ts = DateTime.now().millisecondsSinceEpoch;
    _broadcast({
      'type': 'track_change',
      'current': _memberTrackJson(current!),
      'playing': true,
      'pos': 0,
      'ts': ts,
    });
    _hostActuallyPlay(current!);
  }

  void _hostActuallyPlay(Map<String, dynamic> track) {
    final pc = PlayerController.instance;
    final title = track['title'] as String;
    final artist = track['artist'] as String? ?? '';
    final cover = track['coverUrl'] as String?;
    if (track['kind'] == 'local') {
      pc.playFile(track['ref'] as String,
          title: title, artist: artist, coverUrl: cover);
    } else {
      pc.playStream(track['ref'] as String,
          title: title, artist: artist, isrc: track['isrc'] as String?,
          coverUrl: cover);
    }
  }

  void _hostNext() {
    if (queue.isEmpty) {
      current = null;
      playing = false;
      positionMs = 0;
      ts = DateTime.now().millisecondsSinceEpoch;
      _broadcast({'type': 'track_change', 'current': null, 'playing': false, 'pos': 0, 'ts': ts});
      PlayerController.instance.stop();
      return;
    }
    final idx = queue.indexWhere((t) => t['id'] == current?['id']);
    _hostPlayIndex(idx >= 0 ? (idx + 1) % queue.length : 0);
  }

  void _hostPrev() {
    if (queue.isEmpty) return;
    final idx = queue.indexWhere((t) => t['id'] == current?['id']);
    _hostPlayIndex(idx > 0 ? idx - 1 : queue.length - 1);
  }

  // ---------- Host 搜尋 ----------

  Future<void> _hostSearch(String memberId, dynamic q, dynamic reqId) async {
    final query = (q as String? ?? '').trim();
    if (query.isEmpty) return;
    if (!SpotifySession.instance.isLoggedIn) {
      _send(_clients[memberId]!, {
        'type': 'search_error',
        'reqId': reqId,
        'message': '房主尚未登入 Spotify，請在房主端「搜尋」頁登入',
      });
      return;
    }
    try {
      final data = await SpotifyGqlClient().searchTracks(query, limit: 20);
      final items = _parseSearchItems(data);
      _send(_clients[memberId]!, {'type': 'search_results', 'reqId': reqId, 'items': items});
    } catch (e) {
      _send(_clients[memberId]!, {'type': 'search_error', 'reqId': reqId, 'message': '搜尋失敗: $e'});
    }
  }

  List<Map<String, dynamic>> _parseSearchItems(Map<String, dynamic> data) {
    final out = <Map<String, dynamic>>[];
    try {
      final search = (data['data'] as Map?)?['searchV2'] as Map<String, dynamic>?;
      final tracks = search?['tracksV2'] as Map<String, dynamic>?;
      final items = tracks?['items'] as List<dynamic>? ?? [];
      for (final it in items) {
        final track = (it as Map<String, dynamic>)['item'] as Map<String, dynamic>?;
        if (track == null) continue;
        final album = track['albumOfTrack'] as Map<String, dynamic>?;
        final name = (track['name'] ?? '') as String? ?? '';
        if (name.isEmpty) continue;
        final uri = (track['uri'] ?? '') as String? ?? '';
        final artists = (track['artists'] as List<dynamic>? ?? [])
            .map((a) => ((a as Map<String, dynamic>)['profile'] as Map?)?['name'] as String? ?? '')
            .where((s) => s.isNotEmpty)
            .toList();
        final durationMs = ((track['trackDuration'] as Map<String, dynamic>?)?['totalMilliseconds'] as num?)?.toInt() ?? 0;
        final cover = album != null
            ? SpotifyTrackItem.coverFromSources(album['coverArt']?['sources'])
            : null;
        out.add({
          'uri': uri,
          'name': name,
          'artists': artists,
          'album': (album?['name'] as String?) ?? '',
          'durationMs': durationMs,
          'coverUrl': cover,
        });
      }
    } catch (_) {}
    return out;
  }

  // ---------- Host 聊天 ----------

  void _hostChat(String memberId, dynamic text) {
    final t = (text as String? ?? '').trim();
    if (t.isEmpty) return;
    final name = _clientNames[memberId] ?? '某人';
    _broadcastChat('$name：$t');
  }

  void _broadcastChat(String text) {
    final item = {'text': text, 'ts': DateTime.now().millisecondsSinceEpoch};
    chat.add(item);
    if (chat.length > 100) chat.removeAt(0);
    _broadcast({'type': 'chat_item', 'item': item});
    notifyListeners();
  }

  // ---------- 序列化 ----------

  Map<String, dynamic> _stateJson() {
    return {
      'code': roomCode,
      'members': List<Map<String, dynamic>>.from(members),
      'queue': queue.map((t) => _memberTrackJson(t)).toList(),
      'current': current != null ? _memberTrackJson(current!) : null,
      'playing': playing,
      'pos': positionMs,
      'ts': ts,
      'chat': List<Map<String, dynamic>>.from(chat),
      'skipVotes': skipVotes,
      'skipNeeded': skipNeeded,
      'hostAddress': hostAddress,
    };
  }

  Map<String, dynamic> _memberTrackJson(Map<String, dynamic> t) {
    final out = Map<String, dynamic>.from(t);
    out.remove('_skip');
    out.remove('ref');
    if (t['kind'] == 'local') {
      out['url'] =
          'http://$_lanIp:$_port/jam/audio?f=${Uri.encodeQueryComponent(t['ref'] as String)}';
    } else {
      final streamPort = StreamServer.instance.port;
      out['url'] =
          'http://$_lanIp:$streamPort/stream/${Uri.encodeComponent(t['ref'] as String)}';
    }
    return out;
  }

  void _broadcastQueue() {
    _broadcast({'type': 'queue_update', 'queue': queue.map((t) => _memberTrackJson(t)).toList()});
    notifyListeners();
  }

  // ===================================================================
  //  Host：音訊檔串流（支援 Range，手機可拖進度）
  // ===================================================================

  Future<void> _serveAudioFile(HttpRequest req, String encodedPath) async {
    final path = encodedPath;
    final file = File(path);
    if (!await file.exists()) {
      req.response.statusCode = HttpStatus.notFound;
      await req.response.close();
      return;
    }
    final total = await file.length();
    final range = req.headers.value(HttpHeaders.rangeHeader);
    int start = 0;
    int end = total - 1;
    if (range != null && range.startsWith('bytes=')) {
      final parts = range.substring(6).split('-');
      start = parts[0].isNotEmpty ? (int.tryParse(parts[0]) ?? 0) : 0;
      if (parts.length > 1 && parts[1].isNotEmpty) {
        end = int.tryParse(parts[1]) ?? end;
      }
      if (end >= total) end = total - 1;
      req.response.statusCode = HttpStatus.partialContent;
      req.response.headers.set(HttpHeaders.acceptRangesHeader, 'bytes');
      req.response.headers.set(HttpHeaders.contentRangeHeader, 'bytes $start-$end/$total');
      req.response.headers.contentLength = end - start + 1;
    } else {
      req.response.statusCode = HttpStatus.ok;
      req.response.headers.set(HttpHeaders.acceptRangesHeader, 'bytes');
      req.response.headers.contentLength = total;
    }
    final lower = path.toLowerCase();
    if (lower.endsWith('.m4a') || lower.endsWith('.mp4')) {
      req.response.headers.contentType = ContentType('audio', 'mp4');
    } else if (lower.endsWith('.wav')) {
      req.response.headers.contentType = ContentType('audio', 'wav');
    } else if (lower.endsWith('.flac')) {
      req.response.headers.contentType = ContentType('audio', 'flac');
    } else {
      req.response.headers.contentType = ContentType('audio', 'mpeg');
    }
    final raf = await file.open();
    await raf.setPosition(start);
    final remaining = end - start + 1;
    var sent = 0;
    try {
      while (sent < remaining) {
        final len = min(65536, remaining - sent);
        final buf = await raf.read(len);
        if (buf.isEmpty) break;
        req.response.add(buf);
        sent += buf.length;
      }
      await req.response.close();
    } finally {
      await raf.close();
    }
  }

  // ===================================================================
  //  Client：連線處理
  // ===================================================================

  void _onClientMessage(dynamic raw) {
    final msg = jsonDecode(raw as String) as Map<String, dynamic>;
    final type = msg['type'] as String?;
    switch (type) {
      case 'welcome':
        myId = msg['yourId'] as String;
        _applyState(msg['state']);
        _startDriftSync();
        break;
      case 'state':
        _applyState(msg);
        break;
      case 'queue_update':
        _applyQueue(msg['queue']);
        break;
      case 'track_change':
        _applyTrackChange(msg);
        break;
      case 'playback':
        playing = msg['playing'] as bool? ?? false;
        positionMs = msg['pos'] as int? ?? 0;
        ts = msg['ts'] as int? ?? 0;
        _mirrorPlayPause();
        notifyListeners();
        break;
      case 'member_joined':
        members.add(msg['member']);
        notifyListeners();
        break;
      case 'member_left':
        final leftId = msg['memberId'];
        members.removeWhere((m) => m['id'] == leftId);
        notifyListeners();
        break;
      case 'chat_item':
        chat.add(msg['item']);
        if (chat.length > 100) chat.removeAt(0);
        notifyListeners();
        break;
      case 'skip_count':
        skipVotes = msg['count'] as int? ?? 0;
        skipNeeded = msg['needed'] as int? ?? 0;
        notifyListeners();
        break;
      case 'search_results':
        searching = false;
        final completer = _searchCompleters.remove(msg['reqId'] as int?);
        if (completer != null) {
          completer.complete((msg['items'] as List? ?? []).cast<Map<String, dynamic>>());
        }
        searchResults = (msg['items'] as List? ?? []).cast<Map<String, dynamic>>();
        notifyListeners();
        break;
      case 'search_error':
        searching = false;
        searchError = msg['message'] as String? ?? '搜尋失敗';
        notifyListeners();
        break;
      case 'error':
        lastError = msg['message'] as String? ?? '錯誤';
        notifyListeners();
        break;
      case 'room_closed':
        lastError = '房主關閉了房間';
        leaveRoom();
        break;
    }
  }

  void _onClientClosed() {
    if (mode != 'client') return;
    mode = 'idle';
    _ws = null;
    PlayerController.instance.jamFollowMode = false;
    lastError = '與房主的連線已中斷';
    notifyListeners();
  }

  void _applyState(dynamic state) {
    if (state == null) return;
    final s = state as Map<String, dynamic>;
    members
      ..clear()
      ..addAll((s['members'] as List? ?? []).cast<Map<String, dynamic>>());
    _applyQueue(s['queue']);
    chat
      ..clear()
      ..addAll((s['chat'] as List? ?? []).cast<Map<String, dynamic>>());
    skipVotes = s['skipVotes'] as int? ?? 0;
    skipNeeded = s['skipNeeded'] as int? ?? 0;
    hostAddress = s['hostAddress'] as String? ?? hostAddress;
    roomCode = s['code'] as String? ?? roomCode;
    _applyTrackChange({
      'current': s['current'],
      'playing': s['playing'],
      'pos': s['pos'],
      'ts': s['ts'],
    }, initial: true);
    notifyListeners();
  }

  void _applyQueue(dynamic q) {
    if (q == null) return;
    queue
      ..clear()
      ..addAll((q as List).cast<Map<String, dynamic>>());
    notifyListeners();
  }

  void _applyTrackChange(Map<String, dynamic> msg, {bool initial = false}) {
    final t = msg['current'] as Map<String, dynamic>?;
    current = t;
    playing = msg['playing'] as bool? ?? false;
    positionMs = msg['pos'] as int? ?? 0;
    ts = msg['ts'] as int? ?? 0;

    if (t == null) {
      PlayerController.instance.stop();
      notifyListeners();
      return;
    }

    final url = t['url'] as String? ?? '';
    if (url.isNotEmpty && url != _lastUrl) {
      _lastUrl = url;
      PlayerController.instance.playJamUrl(url,
          title: t['title'] as String,
          artist: t['artist'] as String? ?? '',
          coverUrl: t['coverUrl'] as String?);
    } else if (url.isNotEmpty && url == _lastUrl) {
      _mirrorPlayPause();
      _driftCorrect();
    } else {
      _mirrorPlayPause();
    }
    notifyListeners();
  }

  void _mirrorPlayPause() {
    final pc = PlayerController.instance;
    if (playing) {
      if (!pc.isPlaying) pc.resume();
    } else {
      if (pc.isPlaying) pc.pause();
    }
  }

  void _startDriftSync() {
    _driftTimer?.cancel();
    _driftTimer = Timer.periodic(const Duration(seconds: 4), (_) {
      if (mode != 'client' || !playing || current == null) return;
      _driftCorrect();
    });
  }

  void _driftCorrect() {
    final pc = PlayerController.instance;
    if (pc.title.isEmpty) return; // 還沒有載入任何歌曲
    final elapsed = DateTime.now().millisecondsSinceEpoch - ts;
    final expected = positionMs + elapsed;
    final actual = pc.position.inMilliseconds;
    if ((expected - actual).abs() > 1500) {
      pc.jamSeekLocal(Duration(milliseconds: expected));
    }
  }

  // ===================================================================
  //  Client：指令（由 PlayerController 或 JamPage 轉發）
  // ===================================================================

  void _sendCmd(Map<String, dynamic> msg) {
    if (mode != 'client' || _ws == null) return;
    try {
      _ws!.add(jsonEncode(msg));
    } catch (_) {}
  }

  void togglePlay() {
    if (isHost) {
      final pc = PlayerController.instance;
      pc.isPlaying ? pc.pause() : pc.resume();
      return;
    }
    _sendCmd({'type': playing ? 'pause' : 'play'});
  }

  void seek(Duration pos) {
    if (isHost) {
      PlayerController.instance.seek(pos);
      return;
    }
    _sendCmd({'type': 'seek', 'pos': pos.inMilliseconds});
  }

  void next() {
    if (isHost) {
      _hostNext();
      return;
    }
    _sendCmd({'type': 'next'});
  }

  void previous() {
    if (isHost) {
      _hostPrev();
      return;
    }
    _sendCmd({'type': 'prev'});
  }

  void addTrackFromSearch(Map<String, dynamic> item, {bool clientRequested = false}) {
    // 搜尋結果欄位是 name/artists(list)，統一整併成 host 期待的 title/artist。
    final normalized = <String, dynamic>{
      'title': item['name'],
      'artist': (item['artists'] as List? ?? []).join(', '),
      'coverUrl': item['coverUrl'],
      'isrc': item['isrc'],
    };
    if (isHost) {
      _hostAddTrack(normalized, myId);
      return;
    }
    _sendCmd({'type': 'add', 'track': normalized});
  }

  void vote(String? trackId, int delta) {
    if (trackId == null || trackId.isEmpty) return;
    final cur = _myVotes[trackId] ?? 0;
    final newDelta = cur == delta ? 0 : delta;
    _myVotes[trackId] = newDelta;
    if (isHost) {
      _hostVote(trackId, myId, newDelta);
      return;
    }
    _sendCmd({'type': 'vote', 'trackId': trackId, 'delta': newDelta});
    notifyListeners();
  }

  void removeTrack(String trackId) {
    if (isHost) {
      _hostRemoveTrack(trackId);
      return;
    }
    _sendCmd({'type': 'remove', 'trackId': trackId});
  }

  int myVote(String trackId) => _myVotes[trackId] ?? 0;

  void skipVote() {
    if (isHost) {
      _hostSkip(myId);
      return;
    }
    _sendCmd({'type': 'skip'});
  }

  bool mySkip = false;
  void toggleSkip() {
    mySkip = !mySkip;
    skipVote();
    notifyListeners();
  }

  void sendChat(String text) {
    final t = text.trim();
    if (t.isEmpty) return;
    if (isHost) {
      _hostChat(myId, '$myName：$t');
      return;
    }
    _sendCmd({'type': 'chat', 'text': t});
  }

  /// 搜尋（client 透過 host 代查；host 本機查）。
  Future<List<Map<String, dynamic>>> search(String query) async {
    final q = query.trim();
    if (q.isEmpty) return [];
    searching = true;
    searchError = '';
    searchResults = [];
    notifyListeners();
    try {
      if (isHost) {
        if (!SpotifySession.instance.isLoggedIn) {
          searchError = '尚未登入 Spotify，請先到「搜尋」頁登入';
          searching = false;
          notifyListeners();
          return [];
        }
        final data = await SpotifyGqlClient().searchTracks(q, limit: 20);
        searchResults = _parseSearchItems(data);
        searching = false;
        notifyListeners();
        return searchResults;
      }
      final reqId = ++_searchReqId;
      final completer = Completer<List<Map<String, dynamic>>>();
      _searchCompleters[reqId] = completer;
      _sendCmd({'type': 'search', 'q': q, 'reqId': reqId});
      final results = await completer.future
          .timeout(const Duration(seconds: 20), onTimeout: () => <Map<String, dynamic>>[]);
      searchResults = results;
      searching = false;
      notifyListeners();
      return results;
    } catch (_) {
      searching = false;
      searchError = '搜尋失敗';
      notifyListeners();
      return [];
    }
  }

  // ===================================================================
  //  工具
  // ===================================================================

  Future<String> _lanIpv4() async {
    try {
      final interfaces = await NetworkInterface.list(
          type: InternetAddressType.IPv4, includeLoopback: false);
      for (final ni in interfaces) {
        for (final a in ni.addresses) {
          if (!a.isLoopback && !a.isLinkLocal) return a.address;
        }
      }
    } catch (_) {}
    return '127.0.0.1';
  }

  String _genCode() {
    const chars = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
    final rand = Random();
    return List.generate(6, (_) => chars[rand.nextInt(chars.length)]).join();
  }

  void _buildLibraryIndex() {
    if (_libraryIndex != null) return;
    final cfg = ConfigService.instance.config;
    final roots = <String>{
      cfg.musicPath,
      cfg.basePath,
      '${cfg.basePath}${Platform.pathSeparator}mp3',
      '${cfg.basePath}${Platform.pathSeparator}m4a',
      '${cfg.basePath}${Platform.pathSeparator}native',
    };
    final files = <File>[];
    for (final root in roots) {
      final d = Directory(root);
      if (!d.existsSync()) continue;
      try {
        for (final e in d.listSync(recursive: true)) {
          if (e is File) {
            final lower = e.path.toLowerCase();
            if (lower.endsWith('.mp3') ||
                lower.endsWith('.m4a') ||
                lower.endsWith('.flac') ||
                lower.endsWith('.wav')) {
              files.add(e);
            }
          }
        }
      } catch (_) {}
    }
    _libraryIndex = files;
  }

  String? _findLibraryFile(String query) {
    _buildLibraryIndex();
    final lower = query.toLowerCase();
    for (final f in _libraryIndex ?? const <File>[]) {
      final stem = f.uri.pathSegments.last
          .replaceAll(RegExp(r'\.\w+$'), '')
          .toLowerCase();
      if (stem == lower || stem.contains(lower) || lower.contains(stem)) {
        return f.path;
      }
    }
    return null;
  }
}