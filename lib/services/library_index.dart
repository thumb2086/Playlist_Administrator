import 'dart:convert';
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

  // Static cache: reuse across pipeline steps within the same process lifetime
  static LibraryIndex? _cache;
  static String? _cacheKey;
  // Disk cache fingerprint: set of "path|mtime" strings
  static Set<String>? _cachedFingerprint;
  static String _fingerprintPath = '';

  int get mp3Count => _mp3Count;
  int get m4aCount => _m4aCount;
  bool get isBuilt => _built;

  static void invalidateCache() { _cache = null; _cacheKey = null; _cachedFingerprint = null; }

  static Set<String> _buildFingerprint(List<String> files) {
    final fp = <String>{};
    for (final f in files) {
      final file = File(f);
      try {
        fp.add('$f|${file.lastModifiedSync().millisecondsSinceEpoch}');
      } catch (_) {
        fp.add('$f|0');
      }
    }
    return fp;
  }

  Future<void> build(String libraryPath, void Function(String) log) async {
    // Check static in-memory cache first
    if (_cache != null && _cacheKey == _resolvePath(libraryPath)) {
      _copyFrom(_cache!);
      log('MP3: $_mp3Count, M4A: $_m4aCount (記憶體快取)');
      return;
    }

    log('掃描音檔…');
    final allFiles = await _walkDir(libraryPath);
    final mp3s = <String>[];
    final m4as = <String>[];
    for (final f in allFiles) {
      final low = f.toLowerCase();
      if (low.endsWith('.mp3')) { mp3s.add(f); }
      else if (low.endsWith('.m4a')) { m4as.add(f); }
    }

    final currentFp = _buildFingerprint(allFiles);
    // Check disk cache: if fingerprint unchanged, skip the expensive metadata scan
    if (_cachedFingerprint != null && _fingerprintPath == libraryPath &&
        _cachedFingerprint!.length == currentFp.length &&
        _cachedFingerprint!.containsAll(currentFp)) {
      log('MP3: ${mp3s.length}, M4A: ${m4as.length} (磁碟快取)');
      _mp3Count = mp3s.length;
      _m4aCount = m4as.length;
      // Rebuild file info and filename index (fast, no ffprobe)
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
      _filenameIndex = _buildFilenameIndex(mp3s);
      _metadataIndex = {};
      _saveToCache(libraryPath);
      return;
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

    _saveToCache(libraryPath);
  }

  void _saveToCache(String libraryPath) {
    // Save in-memory static cache
    _cache = LibraryIndex();
    _cache!._copyFrom(this);
    _cacheKey = _resolvePath(libraryPath);
    // Save fingerprint for disk cache
    _cachedFingerprint = _buildFingerprint(_fileInfoMap.keys.toList());
    _fingerprintPath = libraryPath;
  }

  String _resolvePath(String p) {
    try { return Directory(p).resolveSymbolicLinksSync(); }
    catch (_) { return p; }
  }

  void _copyFrom(LibraryIndex other) {
    _filenameIndex = other._filenameIndex;
    _metadataIndex = other._metadataIndex;
    _fileInfoMap = other._fileInfoMap;
    _mp3Count = other._mp3Count;
    _m4aCount = other._m4aCount;
    _built = true;
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
    const batchSize = 20;
    for (int i = 0; i < files.length; i += batchSize) {
      final batch = files.skip(i).take(batchSize).toList();
      final metas = await Future.wait(batch.map((f) => MetadataReader.read(f)));
      for (int j = 0; j < batch.length; j++) {
        final meta = metas[j];
        if (meta.title != null && meta.title!.isNotEmpty) {
          final tokens = _normalize(meta.title!);
          if (tokens.isNotEmpty) {
            index.putIfAbsent(tokens, () => []).add(batch[j]);
          }
        }
      }
      count += batch.length;
      if (count % 500 == 0 || count >= files.length) log('  metadata 索引: $count/${files.length}');
    }
    return index;
  }

  static const Map<String, String> artistAliases = {
    'claire kuo': '郭靜', 'jolin': '蔡依林', 'jolin tsai': '蔡依林',
    'crowd lu': '盧廣仲', 'pets tseng': '曾沛慈', 'evangeline wong': '王艷薇',
    'sabrina': '胡恂舞', 'sabrina hu': '胡恂舞', 'eric chou': '周興哲',
    'shi shi': '孫盛希', 'boon hui lu': '文慧如', 'vicky chen': '陳忻玥',
    'feng ze': '邱鋒澤', 'ivy': '艾薇', 'genblue': '幻藍小熊',
    'lbi': '利比', 'erin': '連穎', 'eleanor': '李芷婷',
    'ann bai': '白安', 'diana wang': '王詩安', 'ethan': '陳威全',
    'chih siou': '持修', 'show luo': '羅志祥',
  };

  static const _noisePatterns = [
    r'全新單曲', r'單曲', r'官方完整版', r'官方', r'完整版',
    r'高清', r'動態歌詞版', r'歌詞版', r'官方版', r'全新',
    r'music video', r'official video', r'official music video',
    r'video', r'loop', r'lyrics',
  ];

  List<String> _normalize(String text) {
    var t = text.toLowerCase().trim();

    // Remove spaces between CJK chars
    t = t.replaceAllMapped(
      RegExp(r'(?<=[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff])\s+(?=[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff])'),
      (_) => '',
    );

    // Convert to Simplified Chinese
    if (ChineseConverter.instance.isLoaded) {
      t = ChineseConverter.instance.toSimplified(t);
    }

    // Apply artist aliases
    for (final e in artistAliases.entries) {
      t = t.replaceAllMapped(
        RegExp('\\b${RegExp.escape(e.key)}\\b', caseSensitive: false),
        (_) => ChineseConverter.instance.isLoaded
            ? ChineseConverter.instance.toSimplified(e.value)
            : e.value.toLowerCase(),
      );
    }

    // Remove "E " prefix artifact (common in Spotify scrapes)
    t = t.replaceAll(RegExp(r'(?:^|(?<=[^a-z0-9]))e(?=[a-z\u4e00-\u9fff\u3040-\u30ff])'), '');

    // Remove noise phrases
    for (final p in _noisePatterns) {
      t = t.replaceAll(RegExp(p, caseSensitive: false), ' ');
    }

    // Standardize separators
    t = t.replaceAll(RegExp(r'\s*(feat|ft|vs)\.?\s*|\s*[&,x]\s*'), ' ');

    // Remove bracket content with keywords
    t = t.replaceAll(
      RegExp(r"[\(\[【（［][^\)\]】）］]*(?:live|remix|mv|official|lyrics?\s*video|music\s*video)[^\)\]】）］]*[\)\]】）］]",
          caseSensitive: false),
      ' ',
    );

    // Add space between Latin and CJK
    t = t.replaceAllMapped(RegExp(r'([a-z])([\u4e00-\u9fff])'), (m) => '${m[1]} ${m[2]}');
    t = t.replaceAllMapped(RegExp(r'([\u4e00-\u9fff])([a-z])'), (m) => '${m[1]} ${m[2]}');

    final parts = t.split(RegExp(r'[\s\-_()\[\]【】,./:：，。、！？（）「」""''（）【】《》〈〉\u3000]'));
    return parts.where((p) => p.isNotEmpty).toList();
  }

  String? findMp3ForM4a(String m4aPath, {bool useMtime = true}) {
    final basename = File(m4aPath).uri.pathSegments.last;
    final stem = basename.replaceAll(RegExp(r'\.\w+$'), '');
    final tokens = _normalize(stem);

    final m4aInfo = _fileInfoMap[m4aPath];

    final exact = _findInIndex(tokens, _filenameIndex);
    if (exact != null) {
      final mp3Info = _fileInfoMap[exact];
      if (!useMtime || (mp3Info != null && m4aInfo != null && mp3Info.mtime.compareTo(m4aInfo.mtime) >= 0)) {
        return exact;
      }
    }

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

    final meta = _metadataIndex.keys.firstWhere(
      (k) => _isSubset(tokens, k) || _isSubset(k, tokens),
      orElse: () => [],
    );
    if (meta.isNotEmpty) {
      for (final f in _metadataIndex[meta]!) {
        if (f.toLowerCase().endsWith('.mp3') && _fileInfoMap.containsKey(f)) return f;
      }
    }
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

  bool isSongInPlaylists(String songName, List<String> playlistSongs) {
    final tokens = _normalize(songName);
    if (tokens.isEmpty) return false;
    for (final ps in playlistSongs) {
      final psTokens = _normalize(ps);
      if (_listEq(tokens, psTokens)) return true;
      if (_isSubset(tokens, psTokens) || _isSubset(psTokens, tokens)) return true;
    }
    return false;
  }
}

class FileInfo {
  final int size;
  final DateTime mtime;
  FileInfo({required this.size, required this.mtime});
}
