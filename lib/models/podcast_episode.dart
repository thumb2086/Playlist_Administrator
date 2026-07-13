class PodcastEpisode {
  final String title;
  final String audioUrl;
  final String? pubDate;
  final String? duration;
  final String? description;

  const PodcastEpisode({
    required this.title,
    required this.audioUrl,
    this.pubDate,
    this.duration,
    this.description,
  });

  factory PodcastEpisode.fromJson(Map<String, dynamic> json) => PodcastEpisode(
        title: json['title'] as String? ?? '',
        audioUrl: json['audio_url'] as String? ?? '',
        pubDate: json['pub_date'] as String?,
        duration: json['duration'] as String?,
        description: json['description'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'title': title,
        'audio_url': audioUrl,
        'pub_date': pubDate,
        'duration': duration,
        'description': description,
      };
}
