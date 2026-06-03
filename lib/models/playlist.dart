class PlaylistConfig {
  final String url;
  final String name;

  PlaylistConfig({required this.url, required this.name});

  factory PlaylistConfig.fromJson(MapEntry<String, dynamic> entry) =>
      PlaylistConfig(url: entry.key, name: entry.value as String);

  Map<String, dynamic> toJson() => {url: name};
}

class PlaylistStatus {
  final String name;
  final int totalTracks;
  final int matchedTracks;
  final String? lastUpdated;
  final bool isDownloaded;

  PlaylistStatus({
    required this.name,
    this.totalTracks = 0,
    this.matchedTracks = 0,
    this.lastUpdated,
    this.isDownloaded = false,
  });

  double get completeness => totalTracks > 0 ? matchedTracks / totalTracks : 0;
}
