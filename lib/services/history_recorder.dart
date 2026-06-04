import 'dart:convert';
import 'dart:io';
import 'config_service.dart';
import 'playlist_parser.dart';

class Snapshot {
  final DateTime time;
  final int mp3;
  final int m4a;
  final int flac;
  final double sizeGb;
  final Map<String, int> playlistTotals;  // name -> total tracks
  final Map<String, int> playlistMatched; // name -> matched tracks

  Snapshot({
    required this.time,
    required this.mp3,
    required this.m4a,
    required this.flac,
    required this.sizeGb,
    required this.playlistTotals,
    required this.playlistMatched,
  });

  Map<String, dynamic> toJson() => {
    'time': time.toIso8601String(),
    'mp3': mp3, 'm4a': m4a, 'flac': flac,
    'sizeGb': sizeGb,
    'playlistTotals': playlistTotals,
    'playlistMatched': playlistMatched,
  };

  factory Snapshot.fromJson(Map<String, dynamic> j) => Snapshot(
    time: DateTime.parse(j['time'] as String),
    mp3: j['mp3'] as int, m4a: j['m4a'] as int, flac: j['flac'] as int,
    sizeGb: (j['sizeGb'] as num).toDouble(),
    playlistTotals: (j['playlistTotals'] as Map<String, dynamic>).map((k, v) => MapEntry(k, v as int)),
    playlistMatched: (j['playlistMatched'] as Map<String, dynamic>).map((k, v) => MapEntry(k, v as int)),
  );
}

class HistoryRecorder {
  static String get _path {
    final base = Platform.environment['LOCALAPPDATA'] ?? '';
    return '$base\\Playlist Administrator\\data\\history.json';
  }

  static List<Snapshot> load() {
    try {
      final f = File(_path);
      if (!f.existsSync()) return [];
      final data = jsonDecode(f.readAsStringSync()) as List<dynamic>;
      return data.map((e) => Snapshot.fromJson(e as Map<String, dynamic>)).toList();
    } catch (_) {
      return [];
    }
  }

  static void save(List<Snapshot> snapshots) {
    try {
      final f = File(_path);
      f.parent.createSync(recursive: true);
      f.writeAsStringSync(jsonEncode(snapshots.map((s) => s.toJson()).toList()), flush: true);
    } catch (_) {}
  }

  static Future<Snapshot> collect() async {
    final cfg = ConfigService.instance.config;
    final libDir = Directory(cfg.libraryPath);
    int mp3 = 0, m4a = 0, flac = 0;
    double size = 0;

    if (await libDir.exists()) {
      await for (final e in libDir.list(recursive: true, followLinks: false)) {
        if (e is File) {
          final low = e.path.toLowerCase();
          size += await e.length() / (1024 * 1024 * 1024);
          if (low.endsWith('.mp3')) mp3++;
          else if (low.endsWith('.m4a')) m4a++;
          else if (low.endsWith('.flac')) flac++;
        }
      }
    }

    // Also scan mp3/m4a/flac subdirs of basePath
    final baseDir = Directory(cfg.basePath);
    if (baseDir.path.toLowerCase() != libDir.path.toLowerCase() && await baseDir.exists()) {
      for (final sub in ['mp3', 'm4a', 'flac']) {
        final subDir = Directory('${cfg.basePath}\\$sub');
        if (await subDir.exists()) {
          await for (final e in subDir.list(recursive: true, followLinks: false)) {
            if (e is File) {
              final low = e.path.toLowerCase();
              size += await e.length() / (1024 * 1024 * 1024);
              if (low.endsWith('.mp3')) mp3++;
              else if (low.endsWith('.m4a')) m4a++;
              else if (low.endsWith('.flac')) flac++;
            }
          }
        }
      }
    }

    // Playlist stats
    final plDir = Directory(cfg.playlistsPath);
    final playlistTotals = <String, int>{};
    final playlistMatched = <String, int>{};
    if (await plDir.exists()) {
      await for (final e in plDir.list()) {
        if (e is File && e.path.toLowerCase().endsWith('.m3u8')) {
          final baseName = File(e.path).uri.pathSegments.last;
          if (PlaylistParser.isInternalPlaylist(baseName)) continue;
          try {
            final entries = PlaylistParser.parseTrackEntries(e.path);
            final plName = baseName.replaceAll('.m3u8', '');
            playlistTotals[plName] = entries.length;
            // Count matched: check if file exists in library
            int matched = 0;
            for (final entry in entries) {
              final stem = File(entry).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '').toLowerCase();
              // Search in libDir recursively
              bool found = false;
              await for (final f in libDir.list(recursive: true, followLinks: false)) {
                if (f is File) {
                  final fStem = File(f.path).uri.pathSegments.last.replaceAll(RegExp(r'\.\w+$'), '').toLowerCase();
                  if (fStem == stem) { found = true; break; }
                }
              }
              if (found) matched++;
            }
            playlistMatched[plName] = matched;
          } catch (_) {}
        }
      }
    }

    return Snapshot(
      time: DateTime.now(),
      mp3: mp3, m4a: m4a, flac: flac, sizeGb: size,
      playlistTotals: playlistTotals,
      playlistMatched: playlistMatched,
    );
  }

  static Future<void> record() async {
    final history = load();
    final snap = await collect();
    // Keep max 100 snapshots, remove oldest if over
    history.add(snap);
    if (history.length > 100) history.removeAt(0);
    save(history);
  }
}
