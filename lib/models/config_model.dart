import 'dart:io';
import '../models/playlist.dart';

class AppConfig {
  String basePath;
  String language;
  String audioFormat;
  int maxThreads;
  bool debugMode;
  bool enableMetadataEnrichment;
  bool spotubeExactMatch;
  bool spotubeConvertMatchedOnly;
  String ffmpegPath;
  String spotubeExePath;
  String spotubeDownloadPath;
  String spotubeFolderName;
  String lyricsFolderName;
  bool autoUpdateCheck;
  bool enableRetroactiveLyrics;
  bool retryFailedLyrics;
  bool retryFailedFlac;
  bool autoSyncOnAdd;
  String theme;
  String skippedVersion;
  bool setupCompleted;
  Map<String, String> urlNames;
  Map<String, String> searchNames;
  Map<String, List<int>> spotubeCoords;
  Map<String, String> lastUpdated;
  Map<String, double> lyricsOffsets;

  AppConfig({
    this.basePath = '',
    this.language = 'zh-TW',
    this.audioFormat = 'mp3',
    this.maxThreads = 4,
    this.debugMode = false,
    this.enableMetadataEnrichment = false,
    this.spotubeExactMatch = true,
    this.spotubeConvertMatchedOnly = false,
    this.ffmpegPath = 'bin/ffmpeg.exe',
    this.spotubeExePath = '',
    this.spotubeDownloadPath = '',
    this.spotubeFolderName = 'spotube',
    this.lyricsFolderName = 'Lyrics',
    this.autoUpdateCheck = true,
    this.enableRetroactiveLyrics = false,
    this.retryFailedLyrics = false,
    this.retryFailedFlac = false,
    this.autoSyncOnAdd = false,
    this.theme = 'dark',
    this.skippedVersion = '',
    this.setupCompleted = false,
    Map<String, String>? urlNames,
    Map<String, String>? searchNames,
    Map<String, List<int>>? spotubeCoords,
    Map<String, String>? lastUpdated,
    Map<String, double>? lyricsOffsets,
  })  : urlNames = urlNames ?? {},
        searchNames = searchNames ?? {},
        spotubeCoords = spotubeCoords ?? {},
        lastUpdated = lastUpdated ?? {},
        lyricsOffsets = lyricsOffsets ?? {};

  List<PlaylistConfig> get playlists =>
      urlNames.entries.map((e) => PlaylistConfig(url: e.key, name: e.value)).toList();

  String get libraryPath {
    final music = '$basePath${Platform.pathSeparator}Music';
    if (Directory(music).existsSync()) return music;
    return basePath;
  }
  String get playlistsPath => '$basePath${Platform.pathSeparator}Playlists';
  String get exportPath => '$basePath${Platform.pathSeparator}USB_Output';
  String get m4aPath {
    final p = '$libraryPath${Platform.pathSeparator}m4a';
    if (!Directory(p).existsSync() && Directory('$basePath${Platform.pathSeparator}m4a').existsSync()) {
      return '$basePath${Platform.pathSeparator}m4a';
    }
    return p;
  }
  String get mp3Path {
    final p = '$libraryPath${Platform.pathSeparator}mp3';
    if (!Directory(p).existsSync() && Directory('$basePath${Platform.pathSeparator}mp3').existsSync()) {
      return '$basePath${Platform.pathSeparator}mp3';
    }
    return p;
  }
  String get lyricsPath => '$libraryPath${Platform.pathSeparator}$lyricsFolderName';

  factory AppConfig.fromJson(Map<String, dynamic> json) => AppConfig(
        basePath: json['base_path'] as String? ?? '',
        language: json['language'] as String? ?? 'zh-TW',
        audioFormat: json['audio_format'] as String? ?? 'mp3',
        maxThreads: json['max_threads'] as int? ?? 4,
        debugMode: json['debug_mode'] as bool? ?? false,
        enableMetadataEnrichment: json['enable_metadata_enrichment'] as bool? ?? false,
        spotubeExactMatch: json['spotube_exact_match'] as bool? ?? true,
        spotubeConvertMatchedOnly: json['spotube_convert_matched_only'] as bool? ?? false,
        ffmpegPath: json['ffmpeg_path'] as String? ?? 'bin/ffmpeg.exe',
        spotubeExePath: json['spotube_exe_path'] as String? ?? '',
        spotubeDownloadPath: json['spotube_download_path'] as String? ?? '',
        spotubeFolderName: json['spotube_folder_name'] as String? ?? 'spotube',
        lyricsFolderName: json['lyrics_folder_name'] as String? ?? 'Lyrics',
        autoUpdateCheck: json['auto_update_check'] as bool? ?? true,
        enableRetroactiveLyrics: json['enable_retroactive_lyrics'] as bool? ?? false,
        retryFailedLyrics: json['retry_failed_lyrics'] as bool? ?? false,
        retryFailedFlac: json['retry_failed_flac'] as bool? ?? false,
        autoSyncOnAdd: json['auto_sync_on_add'] as bool? ?? false,
        theme: json['theme'] as String? ?? 'dark',
        skippedVersion: json['skipped_version'] as String? ?? '',
        setupCompleted: json['setup_completed'] as bool? ?? false,
        urlNames: (json['url_names'] as Map<String, dynamic>?)?.map((k, v) => MapEntry(k, v as String)) ?? {},
        searchNames: (json['search_names'] as Map<String, dynamic>?)?.map((k, v) => MapEntry(k, v as String)) ?? {},
        spotubeCoords: (json['spotube_coords'] as Map<String, dynamic>?)?.map(
                (k, v) => MapEntry(k, (v as List<dynamic>).cast<int>())) ?? {},
        lastUpdated: (json['last_updated'] as Map<String, dynamic>?)?.map((k, v) => MapEntry(k, v as String)) ?? {},
        lyricsOffsets: (json['lyrics_offsets'] as Map<String, dynamic>?)?.map((k, v) => MapEntry(k, (v as num).toDouble())) ?? {},
      );

  Map<String, dynamic> toJson() => {
        'base_path': basePath,
        'language': language,
        'audio_format': audioFormat,
        'max_threads': maxThreads,
        'debug_mode': debugMode,
        'enable_metadata_enrichment': enableMetadataEnrichment,
        'spotube_exact_match': spotubeExactMatch,
        'spotube_convert_matched_only': spotubeConvertMatchedOnly,
        'ffmpeg_path': ffmpegPath,
        'spotube_exe_path': spotubeExePath,
        'spotube_download_path': spotubeDownloadPath,
        'spotube_folder_name': spotubeFolderName,
        'lyrics_folder_name': lyricsFolderName,
        'auto_update_check': autoUpdateCheck,
        'enable_retroactive_lyrics': enableRetroactiveLyrics,
        'retry_failed_lyrics': retryFailedLyrics,
        'retry_failed_flac': retryFailedFlac,
        'auto_sync_on_add': autoSyncOnAdd,
        'theme': theme,
        'skipped_version': skippedVersion,
        'setup_completed': setupCompleted,
        'url_names': urlNames,
        'search_names': searchNames,
        'spotube_coords': spotubeCoords.map((k, v) => MapEntry(k, v)),
        'last_updated': lastUpdated,
        'lyrics_offsets': lyricsOffsets,
      };
}
