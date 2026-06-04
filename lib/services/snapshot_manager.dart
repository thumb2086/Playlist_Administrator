import 'dart:convert';
import 'dart:io';
import 'config_service.dart';

class SnapshotManager {
  static const _cacheFile = 'snapshot_cache.json';
  static const _removedPlaylist = '_Removed Songs.m3u8';

  static String get _cachePath =>
      '${ConfigService.instance.config.basePath}\\$_cacheFile';

  static Map<String, dynamic> _loadCache() {
    try {
      final f = File(_cachePath);
      if (!f.existsSync()) return {'playlists': {}, 'version': '1.0'};
      final data = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
      if (data.containsKey('playlists')) return data;
      return {'playlists': {}, 'version': '1.0'};
    } catch (_) {
      return {'playlists': {}, 'version': '1.0'};
    }
  }

  static void _saveCache(Map<String, dynamic> cache) {
    try {
      File(_cachePath).writeAsStringSync(jsonEncode(cache), flush: true);
    } catch (_) {}
  }

  static List<String> detectRemovedSongs(String playlistName, List<String> currentTracks) {
    final cache = _loadCache();
    final playlists = cache['playlists'] as Map<String, dynamic>;
    final old = playlists[playlistName];
    if (old == null) return [];

    final oldTracks = (old['tracks'] as List<dynamic>?)?.cast<String>() ?? [];
    final oldSet = oldTracks.toSet();
    final currentSet = currentTracks.toSet();
    return oldSet.difference(currentSet).toList();
  }

  static void updateSnapshot(String playlistName, List<String> tracks) {
    final cache = _loadCache();
    final playlists = cache['playlists'] as Map<String, dynamic>;
    playlists[playlistName] = {
      'tracks': tracks,
      'last_updated': DateTime.now().toIso8601String(),
    };
    _saveCache(cache);
  }

  static int appendRemovedSongs(List<String> removedTracks) {
    // Removed songs are tracked in snapshot_cache.json via updateSnapshot.
    // No separate m3u8 file needed — it would duplicate _Unsorted.m3u8.
    if (removedTracks.isEmpty) return 0;
    return removedTracks.length;
  }

  static int processPlaylist(String playlistName, List<String> currentTracks) {
    final removed = detectRemovedSongs(playlistName, currentTracks);
    int count = 0;
    if (removed.isNotEmpty) {
      count = appendRemovedSongs(removed);
    }
    updateSnapshot(playlistName, currentTracks);
    return count;
  }
}
