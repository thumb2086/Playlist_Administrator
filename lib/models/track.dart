class Track {
  final String title;
  final String? artist;
  final String? album;
  final String? filePath;
  final String? format;

  Track({
    required this.title,
    this.artist,
    this.album,
    this.filePath,
    this.format,
  });

  String get displayName => artist != null ? '$title - $artist' : title;
}
