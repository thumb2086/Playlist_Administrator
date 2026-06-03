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
  Map<String, String> urlNames;
  Map<String, String> searchNames;
  Map<String, List<int>> spotubeCoords;
  Map<String, String> lastUpdated;

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
    Map<String, String>? urlNames,
    Map<String, String>? searchNames,
    Map<String, List<int>>? spotubeCoords,
    Map<String, String>? lastUpdated,
  })  : urlNames = urlNames ?? {},
        searchNames = searchNames ?? {},
        spotubeCoords = spotubeCoords ?? {},
        lastUpdated = lastUpdated ?? {};

  List<PlaylistConfig> get playlists =>
      urlNames.entries.map((e) => PlaylistConfig(url: e.key, name: e.value)).toList();

  String get libraryPath => '$basePath${Platform.pathSeparator}Music';
  String get playlistsPath => '$basePath${Platform.pathSeparator}Playlists';
  String get exportPath => '$basePath${Platform.pathSeparator}USB_Output';
  String get m4aPath => '$basePath${Platform.pathSeparator}m4a';
  String get mp3Path => '$basePath${Platform.pathSeparator}mp3';
  String get lyricsPath => '$libraryPath${Platform.pathSeparator}Lyrics';

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
        urlNames: (json['url_names'] as Map<String, dynamic>?)?.map((k, v) => MapEntry(k, v as String)) ?? {},
        searchNames: (json['search_names'] as Map<String, dynamic>?)?.map((k, v) => MapEntry(k, v as String)) ?? {},
        spotubeCoords: (json['spotube_coords'] as Map<String, dynamic>?)?.map(
                (k, v) => MapEntry(k, (v as List<dynamic>).cast<int>())) ?? {},
        lastUpdated: (json['last_updated'] as Map<String, dynamic>?)?.map((k, v) => MapEntry(k, v as String)) ?? {},
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
        'url_names': urlNames,
        'search_names': searchNames,
        'spotube_coords': spotubeCoords.map((k, v) => MapEntry(k, v)),
        'last_updated': lastUpdated,
      };
}
