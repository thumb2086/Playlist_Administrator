class PodcastSearchResult {
  final String title;
  final String author;
  final String feedUrl;
  final String? artworkUrl;
  final String? description;

  const PodcastSearchResult({
    required this.title,
    required this.author,
    required this.feedUrl,
    this.artworkUrl,
    this.description,
  });

  factory PodcastSearchResult.fromAppleJson(Map<String, dynamic> json) =>
      PodcastSearchResult(
        title: json['collectionName'] as String? ?? '',
        author: json['artistName'] as String? ?? '',
        feedUrl: json['feedUrl'] as String? ?? '',
        artworkUrl: json['artworkUrl600'] as String? ??
            json['artworkUrl100'] as String?,
        description:
            (json['description'] as String? ?? '').replaceAll(RegExp(r'<[^>]*>'), ''),
      );
}
