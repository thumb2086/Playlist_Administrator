import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:playlist_admin/services/library_index.dart';

void main() {
  test('0-byte own-stem MP3 forces re-conversion (returns null)', () async {
    final base = Directory.systemTemp.createTempSync('pa_test_');
    final lib = Directory('${base.path}/Music')..createSync();
    final m4aDir = Directory('${lib.path}/m4a')..createSync();
    final mp3Dir = Directory('${lib.path}/mp3')..createSync();

    File('${m4aDir.path}/Somebody Else - 高爾宣 OSN.m4a')
        .writeAsStringSync('M4A');
    File('${mp3Dir.path}/Somebody Else - 高爾宣 OSN.mp3')
        .writeAsStringSync(''); // 0-byte corrupt
    File('${mp3Dir.path}/Somebody Else - Diana Wang.mp3')
        .writeAsStringSync('MP3');
    File('${mp3Dir.path}/Somebody Else - Nejvex.mp3')
        .writeAsStringSync('MP3');

    final index = LibraryIndex();
    await index.build(lib.path, (l) {}, basePath: base.path);

    final result = await index.findMp3ForM4a(
        '${m4aDir.path}/Somebody Else - 高爾宣 OSN.m4a');
    // Own-stem corrupt MP3 exists: must NOT be skipped -> null
    expect(result, isNull);

    // A healthy M4A whose MP3 exists must return that MP3 (still works)
    File('${m4aDir.path}/Somebody Else - Nejvex.m4a')
        .writeAsStringSync('M4A');
    final healthy = await index.findMp3ForM4a(
        '${m4aDir.path}/Somebody Else - Nejvex.m4a',
        useMtime: false);
    expect(healthy, isNotNull);

    base.deleteSync(recursive: true);
  });
}