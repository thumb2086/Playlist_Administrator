import 'dart:io';
import 'metadata_reader.dart';
import 'chinese_converter.dart';

class LibraryIndex {
  Map<List<String>, List<String>> _filenameIndex = {};
  Map<List<String>, List<String>> _metadataIndex = {};
  Map<String, FileInfo> _fileInfoMap = {};
  int _mp3Count = 0;
  int _m4aCount = 0;
  bool _built = false;

  int get mp3Count => _mp3Count;
  int get m4aCount => _m4aCount;
  bool get isBuilt => _built;

  Future<void> build(String libraryPath, void Function(String) log) async {
    log('掃描音檔…');
    final allFiles = await _walkDir(libraryPath);
    final mp3s = <String>[];
    final m4as = <String>[];
    for (final f in allFiles) {
      final low = f.toLowerCase();
      if (low.endsWith('.mp3')) mp3s.add(f);
      else if (low.endsWith('.m4a')) m4as.add(f);
    }
    _mp3Count = mp3s.length;
    _m4aCount = m4as.length;
    _fileInfoMap = {};
    for (final f in allFiles) {
      final file = File(f);
      if (await file.exists()) {
        _fileInfoMap[f] = FileInfo(
          size: await file.length(),
          mtime: await file.lastModified(),
        );
      }
    }
    log('MP3: $_mp3Count, M4A: $_m4aCount');

    log('建立檔名索引…');
    _filenameIndex = _buildFilenameIndex(mp3s);

    log('讀取 metadata 索引…');
    _metadataIndex = await _buildMetadataIndex(mp3s, log);
    log('索引完成');
  }

  Future<List<String>> _walkDir(String path) async {
    final result = <String>[];
    final dir = Directory(path);
    if (!await dir.exists()) return result;
    try {
      await for (final entity in dir.list(recursive: true, followLinks: false)) {
        if (entity is File) {
          final low = entity.path.toLowerCase();
          if (low.endsWith('.mp3') || low.endsWith('.m4a') || low.endsWith('.flac')) {
            result.add(entity.path);
          }
        }
      }
    } catch (_) {}
    return result;
  }

  Map<List<String>, List<String>> _buildFilenameIndex(List<String> files) {
    final index = <List<String>, List<String>>{};
    for (final f in files) {
      final name = File(f).uri.pathSegments.last;
      final stem = name.replaceAll(RegExp(r'\.\w+$'), '');
      final tokens = _normalize(stem);
      if (tokens.isNotEmpty) {
        index.putIfAbsent(tokens, () => []).add(f);
      }
    }
    return index;
  }

  Future<Map<List<String>, List<String>>> _buildMetadataIndex(
      List<String> files, void Function(String) log) async {
    final index = <List<String>, List<String>>{};
    int count = 0;
    for (final f in files) {
      final meta = await MetadataReader.read(f);
      if (meta.title != null && meta.title!.isNotEmpty) {
        final tokens = _normalize(meta.title!);
        if (tokens.isNotEmpty) {
          index.putIfAbsent(tokens, () => []).add(f);
        }
      }
      count++;
      if (count % 500 == 0) log('  metadata 索引: $count/${files.length}');
    }
    return index;
  }

  List<String> _normalize(String text) {
    final t = ChineseConverter.instance.isLoaded
        ? ChineseConverter.instance.toSimplified(text.toLowerCase().trim())
        : text.toLowerCase().trim();
    final parts = t.split(RegExp(r'[\s\-_()\[\]【】,./:：，。、！？（）「」""''（）【】《》〈〉\u3000]'));
    return parts.where((p) => p.isNotEmpty).toList();
  }

  /// Find matching MP3 for a given M4A file using filename + metadata matching.
  String? findMp3ForM4a(String m4aPath, {bool useMtime = true}) {
    final basename = File(m4aPath).uri.pathSegments.last;
    final stem = basename.replaceAll(RegExp(r'\.\w+$'), '');
    final tokens = _normalize(stem);

    final m4aInfo = _fileInfoMap[m4aPath];

    // 1. Exact filename match
    final exact = _findInIndex(tokens, _filenameIndex);
    if (exact != null) {
      final mp3Info = _fileInfoMap[exact];
      if (!useMtime || (mp3Info != null && m4aInfo != null && mp3Info.mtime.compareTo(m4aInfo.mtime) >= 0)) {
        return exact;
      }
    }

    // 2. Subset filename match
    for (final entry in _filenameIndex.entries) {
      if (_isSubset(tokens, entry.key) || _isSubset(entry.key, tokens)) {
        for (final f in entry.value) {
          if (f.toLowerCase().endsWith('.mp3')) {
            final mp3Info = _fileInfoMap[f];
            if (!useMtime || (mp3Info != null && m4aInfo != null && mp3Info.mtime.compareTo(m4aInfo.mtime) >= 0)) {
              return f;
            }
          }
        }
      }
    }

    // 3. Metadata match
    return null;
  }

  String? _findInIndex(List<String> tokens, Map<List<String>, List<String>> index) {
    for (final entry in index.entries) {
      if (_listEq(entry.key, tokens)) {
        for (final f in entry.value) {
          if (f.toLowerCase().endsWith('.mp3') && _fileInfoMap.containsKey(f)) return f;
        }
      }
    }
    return null;
  }

  bool _listEq(List<String> a, List<String> b) {
    if (a.length != b.length) return false;
    for (int i = 0; i < a.length; i++) {
      if (a[i] != b[i]) return false;
    }
    return true;
  }

  bool _isSubset(List<String> small, List<String> big) {
    if (small.length > big.length) return false;
    return small.every((s) => big.any((b) => b.contains(s)));
  }
}

class FileInfo {
  final int size;
  final DateTime mtime;
  FileInfo({required this.size, required this.mtime});
}
