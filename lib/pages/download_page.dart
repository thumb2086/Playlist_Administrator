import 'dart:io';
import 'package:flutter/material.dart';
import '../services/config_service.dart';
import '../services/i18n.dart';
import '../services/download_service.dart';
import '../services/podcast_service.dart';
import '../services/groq_service.dart';
import '../models/podcast_episode.dart';
import '../models/podcast_search_result.dart';
import '../widgets/dark_theme.dart';

class DownloadPage extends StatefulWidget {
  const DownloadPage({super.key});
  @override
  State<DownloadPage> createState() => _DownloadPageState();
}

class _DownloadPageState extends State<DownloadPage> {
  int _tabIndex = 0;

  @override
  void initState() {
    super.initState();
    I18N.instance.addListener(() { if (mounted) setState(() {}); });
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.all(4),
            decoration: BoxDecoration(
              color: AppColors.surfaceLight,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Row(
              children: [
                _tabButton(0, Icons.podcasts, t('download.tab_podcast')),
                _tabButton(1, Icons.music_note, t('download.tab_song')),
                _tabButton(2, Icons.transcribe, t('download.tab_stt')),
              ],
            ),
          ),
          const SizedBox(height: 12),
          Expanded(
            child: IndexedStack(
              index: _tabIndex,
              children: const [
                _PodcastTab(),
                _SongDownloadTab(),
                _GroqSttTab(),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _tabButton(int index, IconData icon, String label) {
    final selected = _tabIndex == index;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() => _tabIndex = index),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8),
          decoration: BoxDecoration(
            color: selected ? AppColors.card : Colors.transparent,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Icon(icon, size: 16, color: selected ? AppColors.accent : AppColors.textMuted),
              const SizedBox(width: 6),
              Text(label, style: TextStyle(
                fontSize: 12,
                fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
                color: selected ? AppColors.text : AppColors.textMuted,
              )),
            ],
          ),
        ),
      ),
    );
  }
}

class _DownloadJob {
  String title;
  double progress;
  bool done;
  bool skipped;
  bool failed;
  _DownloadJob({required this.title, this.progress = 0, this.done = false, this.skipped = false, this.failed = false});
}

class _PodcastTab extends StatefulWidget {
  const _PodcastTab();
  @override
  State<_PodcastTab> createState() => _PodcastTabState();
}

class _PodcastTabState extends State<_PodcastTab> {
  final _searchCtrl = TextEditingController();
  final _urlCtrl = TextEditingController();
  final _logs = <String>[];
  final _scrollCtrl = ScrollController();
  List<PodcastSearchResult> _searchResults = [];
  List<PodcastEpisode> _episodes = [];
  String _podcastTitle = '';
  String _currentRssUrl = '';
  bool _loading = false;
  bool _searching = false;
  bool _showUrlInput = false;
  final Set<int> _selected = {};
  int _maxEpisodes = 100;
  final List<_DownloadJob> _jobs = [];
  bool _cancelRequested = false;
  bool _pauseRequested = false;

  Map<String, String> get _history => ConfigService.instance.config.podcastHistory;

  void _saveHistory(String title, String url) {
    final cfg = ConfigService.instance.config;
    cfg.podcastHistory[title] = url;
    while (cfg.podcastHistory.length > 30) { cfg.podcastHistory.remove(cfg.podcastHistory.keys.first); }
    ConfigService.instance.save();
  }

  @override
  void dispose() { _searchCtrl.dispose(); _urlCtrl.dispose(); _scrollCtrl.dispose(); super.dispose(); }

  void _log(String msg) {
    _logs.add(msg);
    if (mounted) setState(() {});
    Future.delayed(const Duration(milliseconds: 50), () {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(_scrollCtrl.position.maxScrollExtent, duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
      }
    });
  }

  Future<void> _searchPodcasts() async {
    final query = _searchCtrl.text.trim();
    if (query.isEmpty) return;
    setState(() { _searching = true; _searchResults = []; _episodes = []; _podcastTitle = ''; _currentRssUrl = ''; _selected.clear(); });
    try {
      final results = await PodcastService.instance.searchPodcasts(query);
      setState(() { _searchResults = results; _searching = false; });
      _log('✅ 找到 ${results.length} 個節目');
    } catch (e) { _log('❌ 搜尋失敗: $e'); setState(() => _searching = false); }
  }

  Future<void> _selectPodcast(PodcastSearchResult pod) async {
    setState(() { _loading = true; _episodes = []; _podcastTitle = ''; _currentRssUrl = pod.feedUrl; _selected.clear(); });
    try {
      final result = await PodcastService.instance.fetchEpisodes(pod.feedUrl);
      setState(() { _podcastTitle = result.title; _episodes = result.episodes; _maxEpisodes = result.episodes.length; _loading = false; _searchCtrl.text = pod.title; _searchResults = []; });
      _saveHistory(pod.title, pod.feedUrl);
      _log('✅ ${result.title}: ${result.episodes.length} 集');
    } catch (e) { _log('❌ 讀取節目失敗: $e'); setState(() => _loading = false); }
  }

  void _loadFromHistory(String title) {
    final url = _history[title];
    if (url == null) return;
    _searchCtrl.text = title;
    _urlCtrl.text = url;
    _fetchByUrl();
  }

  Future<void> _fetchByUrl() async {
    final url = _urlCtrl.text.trim();
    if (url.isEmpty) return;
    setState(() { _loading = true; _episodes = []; _podcastTitle = ''; _currentRssUrl = url; _selected.clear(); });
    try {
      final result = await PodcastService.instance.fetchEpisodes(url);
      setState(() { _podcastTitle = result.title; _episodes = result.episodes; _maxEpisodes = result.episodes.length; _loading = false; });
      _saveHistory(result.title, url);
      _log('✅ 找到 ${result.episodes.length} 集');
    } catch (e) { _log('❌ 讀取 RSS 失敗: $e'); setState(() => _loading = false); }
  }

  List<PodcastEpisode> get _displayEpisodes => _episodes.take(_maxEpisodes).toList();

  bool _isDownloaded(int index) {
    if (index >= _episodes.length) return false;
    final ep = _episodes[index];
    return PodcastService.instance.isEpisodeDownloaded(ep.title, ep.audioUrl, podcastName: _podcastTitle);
  }

  bool get _hasActiveJobs => _jobs.any((j) => !j.done && !j.failed);

  Future<void> _downloadEpisode(int index) async {
    if (_currentRssUrl.isEmpty) return;
    if (_isDownloaded(index)) { _log('⏭️ 已存在: ${_episodes[index].title}'); return; }
    final job = _DownloadJob(title: _episodes[index].title);
    setState(() { _jobs.add(job); });
    try {
      final downloaded = await PodcastService.instance.downloadEpisode(_currentRssUrl, index, (p) { if (mounted) setState(() => job.progress = p); }, podcastName: _podcastTitle);
      job.done = true; job.skipped = !downloaded;
      _log(downloaded ? '✅ ${_episodes[index].title}' : '⏭️ 已存在: ${_episodes[index].title}');
    } catch (e) { job.failed = true; _log('❌ ${_episodes[index].title}: $e'); }
    if (mounted) setState(() {});
  }

  Future<void> _downloadSelected() async {
    if (_selected.isEmpty || _currentRssUrl.isEmpty) return;
    final indices = _selected.toList()..sort();
    _selected.clear();
    for (final idx in indices) {
      if (_isDownloaded(idx)) { _log('⏭️ 已存在: ${_episodes[idx].title}'); continue; }
      final job = _DownloadJob(title: _episodes[idx].title);
      setState(() { _jobs.add(job); });
      _downloadSingleInBg(idx, job);
      await Future.delayed(const Duration(milliseconds: 100));
    }
  }

  Future<void> _downloadSingleInBg(int idx, _DownloadJob job) async {
    try {
      final downloaded = await PodcastService.instance.downloadEpisode(_currentRssUrl, idx, (p) { if (mounted) setState(() => job.progress = p); }, podcastName: _podcastTitle);
      job.done = true; job.skipped = !downloaded;
      _log(downloaded ? '✅ ${_episodes[idx].title}' : '⏭️ 已存在: ${_episodes[idx].title}');
    } catch (e) { job.failed = true; _log('❌ ${_episodes[idx].title}: $e'); }
    if (mounted) setState(() {});
  }

  void _cancelAllDownloads() {
    _cancelRequested = true;
    for (final j in _jobs) { if (!j.done && !j.failed) { j.failed = true; _log('⏹️ 已取消: ${j.title}'); } }
    setState(() {});
  }

  void _pauseDownloads() {
    if (_pauseRequested) { _pauseRequested = false; _log('▶️ 繼續'); }
    else { _pauseRequested = true; _log('⏸️ 暫停中，等待目前檔案完成...'); }
    setState(() {});
  }

  void _clearCompletedJobs() { _jobs.removeWhere((j) => j.done || j.failed); setState(() {}); }

  void _toggleSelect(int index) { setState(() { if (_selected.contains(index)) _selected.remove(index); else _selected.add(index); }); }

  void _selectAll() {
    final displayed = _displayEpisodes;
    final displayedIndices = displayed.map((e) => _episodes.indexOf(e)).toSet();
    setState(() { if (_selected.containsAll(displayedIndices)) _selected.removeAll(displayedIndices); else _selected.addAll(displayedIndices); });
  }

  @override
  Widget build(BuildContext context) {
    final activeJobs = _jobs.where((j) => !j.done && !j.failed).toList();
    final activeCount = activeJobs.length;
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(color: AppColors.card, borderRadius: BorderRadius.circular(14), border: Border.all(color: AppColors.border)),
          child: Column(
            children: [
              if (_history.isNotEmpty) ...[
                SizedBox(
                  height: 32,
                  child: Row(
                    children: [
                      Icon(Icons.history, size: 14, color: AppColors.textMuted),
                      const SizedBox(width: 6),
                      Expanded(
                        child: DropdownButtonHideUnderline(
                          child: DropdownButton<String>(
                            value: null,
                            hint: Text(t('download.podcast_history_hint'), style: const TextStyle(fontSize: 11, color: AppColors.textMuted)),
                            isExpanded: true,
                            style: const TextStyle(fontSize: 12, color: AppColors.text),
                            items: _history.entries.map((e) => DropdownMenuItem(value: e.key, child: Text(e.key, overflow: TextOverflow.ellipsis))).toList(),
                            onChanged: (v) { if (v != null) _loadFromHistory(v); },
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
              ],
              Row(
                children: [
                  Expanded(child: TextField(controller: _searchCtrl,
                    decoration: InputDecoration(hintText: t('download.podcast_search_hint'), prefixIcon: const Icon(Icons.search, size: 18), border: const OutlineInputBorder()),
                    style: const TextStyle(fontSize: 13), onSubmitted: (_) => _searchPodcasts())),
                  const SizedBox(width: 10),
                  _ActionBtn(t('download.search'), Icons.search, _searchPodcasts, _searching, isPrimary: true),
                ],
              ),
              const SizedBox(height: 6),
              GestureDetector(
                onTap: () => setState(() => _showUrlInput = !_showUrlInput),
                child: Row(children: [
                  Icon(Icons.link, size: 12, color: AppColors.textMuted),
                  const SizedBox(width: 4),
                  Text(_showUrlInput ? t('download.hide_url_input') : t('download.use_rss_url'), style: const TextStyle(color: AppColors.accent, fontSize: 11)),
                ]),
              ),
              if (_showUrlInput) ...[
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(child: TextField(controller: _urlCtrl,
                      decoration: InputDecoration(hintText: t('download.podcast_hint'), prefixIcon: const Icon(Icons.rss_feed, size: 18), border: const OutlineInputBorder()),
                      style: const TextStyle(fontSize: 13), onSubmitted: (_) => _fetchByUrl())),
                    const SizedBox(width: 10),
                    _ActionBtn(t('download.fetch'), Icons.download, _fetchByUrl, _loading),
                  ],
                ),
              ],
            ],
          ),
        ),
        if (_searchResults.isNotEmpty && _episodes.isEmpty)
          Expanded(flex: 5, child: ListView.builder(
            itemCount: _searchResults.length,
            itemBuilder: (ctx, i) {
              final pod = _searchResults[i];
              return Container(
                margin: const EdgeInsets.only(bottom: 6),
                decoration: BoxDecoration(color: AppColors.card, borderRadius: BorderRadius.circular(10), border: Border.all(color: AppColors.border)),
                child: ListTile(
                  dense: true,
                  leading: Container(width: 40, height: 40, decoration: BoxDecoration(color: AppColors.surfaceLight, borderRadius: BorderRadius.circular(8)),
                      child: const Icon(Icons.podcasts, size: 20, color: AppColors.textMuted)),
                  title: Text(pod.title, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500), maxLines: 1, overflow: TextOverflow.ellipsis),
                  subtitle: Text(pod.author, style: const TextStyle(fontSize: 10, color: AppColors.textMuted)),
                  trailing: const Icon(Icons.chevron_right, size: 16, color: AppColors.textMuted),
                  onTap: () => _selectPodcast(pod),
                ),
              );
            },
          )),
        if (_podcastTitle.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                Expanded(child: Text(_podcastTitle, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700))),
                if (_episodes.isNotEmpty) ...[
                  SizedBox(height: 28, child: DropdownButton<int>(
                    value: _maxEpisodes, underline: const SizedBox(),
                    items: [
                      ...[50, 100, 200, 500].map((n) => DropdownMenuItem(value: n, child: Text('$n', style: const TextStyle(fontSize: 11)))),
                      DropdownMenuItem(value: _episodes.length, child: const Text('全部', style: TextStyle(fontSize: 11))),
                    ],
                    onChanged: (v) { if (v != null) setState(() => _maxEpisodes = v); },
                  )),
                  TextButton.icon(
                    onPressed: _selectAll,
                    icon: Icon(_selected.length == _displayEpisodes.length ? Icons.deselect : Icons.select_all, size: 14),
                    label: Text(_selected.length == _displayEpisodes.length ? t('download.deselect_all') : t('download.select_all'), style: const TextStyle(fontSize: 11)),
                  ),
                  if (_selected.isNotEmpty)
                    _ActionBtn('${t('download.dl_selected')} (${_selected.length})', Icons.download, _downloadSelected, false, isPrimary: true),
                ],
              ]),
              Text('${_episodes.length} 集  · 顯示 ${_displayEpisodes.length} 集', style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
            ]),
          ),
        if (_episodes.isNotEmpty)
          Expanded(flex: 3, child: ListView.builder(
            itemCount: _displayEpisodes.length,
            itemBuilder: (ctx, i) {
              final ep = _displayEpisodes[i];
              final origIndex = _episodes.indexOf(ep);
              final alreadyDl = _isDownloaded(origIndex);
              final selected = _selected.contains(origIndex);
              final isActive = activeJobs.any((j) => j.title == ep.title);
              final job = _jobs.where((j) => j.title == ep.title).lastOrNull;
              return Container(
                margin: const EdgeInsets.only(bottom: 6),
                decoration: BoxDecoration(
                  color: AppColors.card, borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: selected ? AppColors.accent.withValues(alpha: 0.4) : (alreadyDl ? AppColors.accent.withValues(alpha: 0.15) : AppColors.border)),
                ),
                child: ListTile(
                  dense: true,
                  leading: isActive
                      ? Container(width: 32, height: 32, decoration: BoxDecoration(color: AppColors.accentDim, borderRadius: BorderRadius.circular(8)),
                          child: SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, value: job!.progress)))
                      : GestureDetector(
                          onTap: () => _toggleSelect(origIndex),
                          child: Container(width: 32, height: 32,
                            decoration: BoxDecoration(color: alreadyDl ? AppColors.accentDim : (selected ? AppColors.accentDim : AppColors.surfaceLight),
                                borderRadius: BorderRadius.circular(8),
                                border: selected ? Border.all(color: AppColors.accent, width: 2) : null),
                            child: Icon(alreadyDl ? Icons.check_circle : (selected ? Icons.check : Icons.headphones),
                                size: 16, color: alreadyDl ? AppColors.accent : (selected ? AppColors.accent : AppColors.textMuted)),
                          ),
                        ),
                  title: Row(children: [
                    Expanded(child: Text(ep.title, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500), maxLines: 2, overflow: TextOverflow.ellipsis)),
                    if (alreadyDl) Container(padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
                        decoration: BoxDecoration(color: AppColors.accentDim, borderRadius: BorderRadius.circular(4)),
                        child: const Text('✓', style: TextStyle(color: AppColors.accent, fontSize: 9))),
                  ]),
                  subtitle: ep.pubDate != null ? Text(ep.pubDate!, style: const TextStyle(fontSize: 10, color: AppColors.textMuted)) : null,
                  trailing: isActive
                      ? Text('${(job!.progress * 100).toStringAsFixed(0)}%', style: const TextStyle(color: AppColors.accent, fontSize: 10))
                      : (alreadyDl ? const Icon(Icons.check_circle, size: 16, color: AppColors.accent)
                          : IconButton(icon: const Icon(Icons.download, size: 18), color: AppColors.accent, onPressed: () => _downloadEpisode(origIndex))),
                  onTap: () => _toggleSelect(origIndex),
                ),
              );
            },
          )),
        if (_episodes.isEmpty && _searchResults.isEmpty)
          Expanded(flex: 3, child: Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(Icons.podcasts, size: 48, color: AppColors.textMuted.withValues(alpha: 0.3)),
            const SizedBox(height: 8),
            Text(t('download.podcast_search_empty'), style: const TextStyle(color: AppColors.textMuted, fontSize: 13)),
          ]))),
        if (activeCount > 0) ...[
          const SizedBox(height: 6),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: _jobs.fold(0.0, (sum, j) => sum + j.progress) / (_jobs.length > 0 ? _jobs.length : 1),
              backgroundColor: AppColors.surfaceLight,
              valueColor: const AlwaysStoppedAnimation(AppColors.accent),
              minHeight: 8,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            '${_jobs.where((j) => j.done || j.failed).length}/${_jobs.length}  正在下載: ${activeJobs.firstOrNull?.title ?? ''}',
            style: const TextStyle(color: AppColors.textMuted, fontSize: 11),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
        if (activeCount > 0 || _jobs.where((j) => j.done || j.failed).length > 0) ...[
          const SizedBox(height: 6),
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(color: AppColors.card, borderRadius: BorderRadius.circular(10), border: Border.all(color: AppColors.border)),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                const Icon(Icons.download, size: 14, color: AppColors.accent),
                const SizedBox(width: 6),
                Text('下載佇列 (${_jobs.length})', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                const Spacer(),
                if (activeCount > 0)
                  SizedBox(height: 24, child: ElevatedButton.icon(
                    onPressed: _cancelAllDownloads, icon: const Icon(Icons.stop_rounded, size: 12),
                    label: const Text('取消全部', style: TextStyle(fontSize: 10)),
                    style: ElevatedButton.styleFrom(backgroundColor: AppColors.error, foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(horizontal: 8), visualDensity: VisualDensity.compact))),
                if (activeCount == 0) TextButton(onPressed: _clearCompletedJobs, child: const Text('清除已完成', style: TextStyle(fontSize: 10))),
              ]),
              const SizedBox(height: 6),
              ..._jobs.reversed.take(10).map((j) {
                final icon = j.failed ? '❌' : (j.done ? (j.skipped ? '⏭️' : '✅') : '⬇️');
                return Padding(padding: const EdgeInsets.symmetric(vertical: 1), child: Row(children: [
                  Text(icon, style: const TextStyle(fontSize: 10)),
                  const SizedBox(width: 4),
                  Expanded(child: Text(j.title, style: const TextStyle(fontSize: 10), maxLines: 1, overflow: TextOverflow.ellipsis)),
                  if (!j.done && !j.failed) SizedBox(width: 40, child: LinearProgressIndicator(value: j.progress, backgroundColor: AppColors.surfaceLight, minHeight: 4)),
                ]));
              }),
            ]),
          ),
        ],
        if (_episodes.isNotEmpty || _searchResults.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(t('download.log'), style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
          const SizedBox(height: 4),
          Expanded(flex: 2, child: Container(
            decoration: BoxDecoration(color: const Color(0xFF080808), borderRadius: BorderRadius.circular(10), border: Border.all(color: AppColors.border)),
            clipBehavior: Clip.antiAlias,
            child: _logs.isEmpty
                ? Center(child: Text(t('download.log_empty'), style: const TextStyle(color: AppColors.textMuted, fontSize: 11)))
                : ListView.builder(controller: _scrollCtrl, padding: const EdgeInsets.all(8), itemCount: _logs.length,
                    itemBuilder: (ctx, i) => Padding(padding: const EdgeInsets.symmetric(vertical: 1),
                      child: Text(_logs[i], style: const TextStyle(fontSize: 12, fontFamily: 'Consolas', color: AppColors.textMuted, height: 1.4)))),
          )),
        ],
        const SizedBox(height: 12),
      ],
    );
  }
}

class _SongDownloadTab extends StatefulWidget {
  const _SongDownloadTab();
  @override
  State<_SongDownloadTab> createState() => _SongDownloadTabState();
}

class _SongDownloadTabState extends State<_SongDownloadTab> {
  final _queryCtrl = TextEditingController();
  final _logs = <String>[];
  final _scrollCtrl = ScrollController();
  String _format = 'mp3';
  bool _running = false;
  double _progress = 0;

  @override
  void dispose() { _queryCtrl.dispose(); _scrollCtrl.dispose(); super.dispose(); }

  void _log(String msg) {
    _logs.add(msg); if (mounted) setState(() {});
    Future.delayed(const Duration(milliseconds: 50), () {
      if (_scrollCtrl.hasClients) _scrollCtrl.animateTo(_scrollCtrl.position.maxScrollExtent, duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
    });
  }

  Future<void> _startDownload() async {
    final query = _queryCtrl.text.trim();
    if (query.isEmpty) return;
    setState(() { _running = true; _progress = 0; _logs.clear(); });
    final cfg = ConfigService.instance.config;
    try {
      await DownloadService.instance.downloadSong(songName: query, libraryPath: cfg.libraryPath, format: _format,
        onLog: _log, onProgress: (p) { if (mounted) setState(() => _progress = p); });
    } catch (e) { _log('❌ $e'); }
    setState(() => _running = false);
  }

  Future<void> _startYtDownload() async {
    final url = _queryCtrl.text.trim();
    if (url.isEmpty) return;
    setState(() { _running = true; _progress = 0; _logs.clear(); });
    final cfg = ConfigService.instance.config;
    final outPath = '${cfg.libraryPath}\\${DateTime.now().millisecondsSinceEpoch}.$_format';
    try {
      await DownloadService.instance.downloadYouTube(url: url, outputPath: outPath, format: _format,
        onLog: _log, onProgress: (p) { if (mounted) setState(() => _progress = p); });
    } catch (e) { _log('❌ $e'); }
    setState(() => _running = false);
  }

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(color: AppColors.card, borderRadius: BorderRadius.circular(14), border: Border.all(color: AppColors.border)),
        child: Column(children: [
          Row(children: [
            Expanded(child: TextField(controller: _queryCtrl,
              decoration: InputDecoration(hintText: t('download.song_hint'), prefixIcon: const Icon(Icons.search, size: 18), border: const OutlineInputBorder()),
              style: const TextStyle(fontSize: 13))),
            const SizedBox(width: 8),
            DropdownButton<String>(value: _format, underline: const SizedBox(),
              items: const [DropdownMenuItem(value: 'mp3', child: Text('MP3', style: TextStyle(fontSize: 12))), DropdownMenuItem(value: 'flac', child: Text('FLAC', style: TextStyle(fontSize: 12)))],
              onChanged: (v) { if (v != null) setState(() => _format = v); }),
            const SizedBox(width: 8),
            _ActionBtn(t('download.dl_song'), Icons.download, _startDownload, _running, isPrimary: true),
          ]),
          const SizedBox(height: 8),
          SizedBox(width: double.infinity, child: Text(t('download.or_enter_yt'), style: const TextStyle(color: AppColors.textMuted, fontSize: 11))),
          const SizedBox(height: 4),
          SizedBox(width: double.infinity, child: _ActionBtn(t('download.dl_yt_url'), Icons.link, _startYtDownload, _running)),
        ]),
      ),
      if (_running) ...[
        const SizedBox(height: 10),
        ClipRRect(borderRadius: BorderRadius.circular(4),
          child: LinearProgressIndicator(value: _progress, backgroundColor: AppColors.surfaceLight, valueColor: const AlwaysStoppedAnimation(AppColors.accent), minHeight: 6)),
        const SizedBox(height: 6),
        Text('${(_progress * 100).toStringAsFixed(0)}%', style: const TextStyle(color: AppColors.textMuted, fontSize: 11)),
      ],
      const SizedBox(height: 10),
      Text(t('download.log'), style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
      const SizedBox(height: 4),
      Expanded(child: Container(
        decoration: BoxDecoration(color: const Color(0xFF080808), borderRadius: BorderRadius.circular(10), border: Border.all(color: AppColors.border)),
        clipBehavior: Clip.antiAlias,
        child: _logs.isEmpty
            ? Center(child: Text(t('download.log_empty'), style: const TextStyle(color: AppColors.textMuted, fontSize: 11)))
            : ListView.builder(controller: _scrollCtrl, padding: const EdgeInsets.all(8), itemCount: _logs.length,
                itemBuilder: (ctx, i) => Padding(padding: const EdgeInsets.symmetric(vertical: 1),
                  child: Text(_logs[i], style: const TextStyle(fontSize: 12, fontFamily: 'Consolas', color: AppColors.textMuted, height: 1.4))))),
      ),
      const SizedBox(height: 12),
    ]);
  }
}

class _SttJob {
  String path;
  String name;
  double progress;
  bool done;
  bool failed;
  String? result;
  _SttJob({required this.path, required this.name, this.progress = 0, this.done = false, this.failed = false, this.result});
}

class _GroqSttTab extends StatefulWidget {
  const _GroqSttTab();
  @override
  State<_GroqSttTab> createState() => _GroqSttTabState();
}

class _GroqSttTabState extends State<_GroqSttTab> {
  final _apiKeyCtrl = TextEditingController();
  late String _model;
  String _language = 'zh';
  bool _transcribing = false;
  bool _keyVisible = false;
  Map<String, List<String>> _groups = {};
  Set<String> _selected = {};
  bool _loadingFiles = false;
  String? _loadError;
  final List<_SttJob> _jobs = [];
  final Set<String> _expanded = {};
  bool _cancelRequested = false;
  bool _pauseRequested = false;

  @override
  void initState() {
    super.initState();
    _model = GroqService.instance.defaultModel;
    final saved = ConfigService.instance.config.groqApiKey;
    if (saved.isNotEmpty) { _apiKeyCtrl.text = saved; GroqService.instance.setApiKey(saved); }
    _loadingFiles = true;
    _loadFiles();
  }

  @override
  void dispose() { _apiKeyCtrl.dispose(); super.dispose(); }

  void _saveApiKey() {
    final key = _apiKeyCtrl.text.trim();
    ConfigService.instance.config.groqApiKey = key;
    ConfigService.instance.save();
    GroqService.instance.setApiKey(key);
    if (mounted) { ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('API Key 已儲存'))); }
  }

  Future<void> _loadFiles() async {
    try {
      // Try multiple known paths
      final cfgBase = ConfigService.instance.config.basePath.trim();
      final homeDir = Platform.environment['USERPROFILE'] ?? '';
      final candidates = [
        if (cfgBase.isNotEmpty) '$cfgBase${Platform.pathSeparator}podcast_downloads',
        if (cfgBase.isNotEmpty) cfgBase.replaceAll('\\Music\\Spotube', '') + '${Platform.pathSeparator}podcast_downloads',
        '$homeDir${Platform.pathSeparator}Music${Platform.pathSeparator}Spotube${Platform.pathSeparator}podcast_downloads',
        '${Platform.environment['HOMEDRIVE'] ?? ''}${Platform.environment['HOMEPATH'] ?? ''}${Platform.pathSeparator}Music${Platform.pathSeparator}Spotube${Platform.pathSeparator}podcast_downloads',
      ];
      Directory? baseDir;
      String? foundPath;
      for (final p in candidates) {
        if (p.isEmpty) continue;
        final d = Directory(p);
        if (d.existsSync()) { baseDir = d; foundPath = p; break; }
      }
      if (baseDir == null) {
        if (mounted) setState(() { _loadingFiles = false; _loadError = '找不到 podcast_downloads\nbasePath=[$cfgBase]\n嘗試了 ${candidates.length} 個路徑'; });
        return;
      }

      final start = DateTime.now();
      final allFiles = <String>[];
      final toScan = [baseDir];

      while (toScan.isNotEmpty && DateTime.now().difference(start).inSeconds < 8) {
        final current = toScan.removeAt(0);
        try {
          final entities = current.listSync();
          for (final e in entities) {
            if (e is File) {
              final low = e.path.toLowerCase();
              if (low.endsWith('.mp3') || low.endsWith('.m4a') || low.endsWith('.wav') || low.endsWith('.flac')) allFiles.add(e.path);
            } else if (e is Directory) {
              toScan.add(e);
            }
          }
        } catch (_) {}
      }

      if (allFiles.isEmpty) {
        if (mounted) setState(() { _loadingFiles = false; _loadError = '未找到音檔'; });
        return;
      }

      allFiles.sort((a, b) => b.compareTo(a));
      final groups = <String, List<String>>{};
      for (final f in allFiles) {
        final seg = f.replaceAll('\\', '/').split('/');
        final parent = seg.length >= 2 ? seg[seg.length - 2] : '';
        final key = (parent.isNotEmpty && parent != 'podcast_downloads') ? parent : '未分類';
        groups.putIfAbsent(key, () => []).add(f);
      }
      if (mounted) setState(() { _groups = groups; _loadingFiles = false; _loadError = null; });
    } catch (e) {
      if (mounted) setState(() { _loadingFiles = false; _loadError = '讀取失敗: $e'; });
    }
  }

  int get _totalFiles => _groups.values.fold(0, (s, l) => s + l.length);

  void _toggleSelect(String path) { setState(() { if (_selected.contains(path)) _selected.remove(path); else _selected.add(path); }); }

  void _toggleGroup(String podcast) {
    final files = _groups[podcast]?.toSet() ?? {};
    setState(() { if (files.every((f) => _selected.contains(f))) _selected.removeAll(files); else _selected.addAll(files); });
  }

  void _cancelAllDownloads() {
    _cancelRequested = true;
    for (final j in _jobs) { if (!j.done && !j.failed) { j.failed = true; } }
    setState(() {});
  }

  void _pauseDownloads() {
    if (_pauseRequested) { _pauseRequested = false; }
    else { _pauseRequested = true; }
    setState(() {});
  }

  Future<void> _transcribeSelected() async {
    final apiKey = _apiKeyCtrl.text.trim();
    if (apiKey.isEmpty) { _snack('請先輸入 Groq API Key'); return; }
    if (_selected.isEmpty) { _snack('請勾選要辨識的音檔'); return; }
    GroqService.instance.setApiKey(apiKey);
    final paths = _selected.toList()..sort();
    _selected.clear();
    _cancelRequested = false;
    setState(() => _transcribing = true);

    // Sort by EP number naturally (EP1, EP2, ..., EP10, not EP1, EP10, EP2)
    paths.sort((a, b) {
      final ra = RegExp(r'EP(\d+)').firstMatch(a.split('\\').last);
      final rb = RegExp(r'EP(\d+)').firstMatch(b.split('\\').last);
      if (ra != null && rb != null) {
        return int.parse(ra.group(1)!).compareTo(int.parse(rb.group(1)!));
      }
      return a.compareTo(b);
    });

    // Fixed high concurrency - Python bridge handles key rotation + rate limiting
    int index = 0;
    final workerCount = (GroqService.instance.keyCount * 3).clamp(4, 12);

    Future<void> _worker() async {
      while (true) {
        if (_cancelRequested) break;
        while (_pauseRequested && !_cancelRequested) {
          await Future.delayed(const Duration(milliseconds: 500));
        }
        if (_cancelRequested) break;
        if (index >= paths.length) break;
        final i = index++;
        final path = paths[i];
        final name = path.split('\\').last;
        final txtPath = path.replaceAll(RegExp(r'\.\w+$'), '.txt');

        if (File(txtPath).existsSync()) {
          setState(() => _jobs.add(_SttJob(path: path, name: name, done: true, result: '⏭️ 已有逐字稿')));
          continue;
        }

        final job = _SttJob(path: path, name: name);
        setState(() { _jobs.add(job); });
        try {
          final text = await GroqService.instance.transcribeFile(
            filePath: path, model: _model, language: _language.isEmpty ? null : _language,
            onChunk: (chunk, p) { if (mounted) setState(() => job.progress = p); },
          );
          job.done = true; job.result = text;
          await File(txtPath).writeAsString(text);
        } catch (e) {
          job.failed = true; job.result = '❌ $e';
        }
        if (mounted) setState(() {});
      }
    }

    await Future.wait(List.generate(workerCount, (_) => _worker()));
    setState(() => _transcribing = false);
  }

  void _snack(String msg) { if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg))); }

  @override
  Widget build(BuildContext context) {
    return Column(children: [
      Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(color: AppColors.card, borderRadius: BorderRadius.circular(14), border: Border.all(color: AppColors.border)),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(child: TextField(controller: _apiKeyCtrl,
              decoration: InputDecoration(
                hintText: 'key1,key2,...',
                labelText: 'Groq API Key（多個用逗號分開）',
                prefixIcon: const Icon(Icons.key, size: 18),
                border: const OutlineInputBorder(),
                isDense: true,
                suffixIcon: IconButton(
                  icon: Icon(_keyVisible ? Icons.visibility_off : Icons.visibility, size: 16),
                  onPressed: () => setState(() => _keyVisible = !_keyVisible),
                ),
              ),
              style: const TextStyle(fontSize: 12), obscureText: !_keyVisible)),
            const SizedBox(width: 6),
            TextButton(onPressed: _saveApiKey, child: const Text('儲存', style: TextStyle(fontSize: 11))),
          ]),
            if (GroqService.instance.keyCount > 1)
              Padding(padding: const EdgeInsets.only(top: 2),
                child: Text('${GroqService.instance.keyCount} 個 Key · 併發 ${(GroqService.instance.keyCount * 3).clamp(4, 12)} 線程 · 429 自動降級 turbo',
                  style: const TextStyle(fontSize: 9, color: AppColors.accent))),
          const SizedBox(height: 8),
          Row(children: [
            Expanded(child: DropdownButtonFormField<String>(value: _model,
              decoration: const InputDecoration(labelText: '模型', border: OutlineInputBorder(), contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 8), isDense: true),
              items: GroqService.models.map((m) => DropdownMenuItem(value: m, child: Text(m, style: const TextStyle(fontSize: 11)))).toList(),
              onChanged: (v) { if (v != null) setState(() => _model = v); })),
            const SizedBox(width: 8),
            Expanded(child: DropdownButtonFormField<String>(value: _language,
              decoration: const InputDecoration(labelText: '語言', border: OutlineInputBorder(), contentPadding: EdgeInsets.symmetric(horizontal: 10, vertical: 8), isDense: true),
              items: GroqService.languages.map((l) => DropdownMenuItem(value: l,
                child: Text(l.isEmpty ? '自動' : l.toUpperCase(), style: const TextStyle(fontSize: 11)))).toList(),
              onChanged: (v) { if (v != null) setState(() => _language = v); })),
            const SizedBox(width: 6),
            if (_transcribing)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(
                    height: 30,
                    child: ElevatedButton.icon(
                      onPressed: _pauseDownloads,
                      icon: Icon(_pauseRequested ? Icons.play_arrow_rounded : Icons.pause_rounded, size: 14),
                      label: Text(_pauseRequested ? '繼續' : '暫停', style: const TextStyle(fontSize: 11)),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: _pauseRequested ? AppColors.accent : Colors.orange,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(horizontal: 8), visualDensity: VisualDensity.compact),
                    ),
                  ),
                  const SizedBox(width: 4),
                  SizedBox(
                    height: 30,
                    child: ElevatedButton.icon(
                      onPressed: _cancelAllDownloads,
                      icon: const Icon(Icons.stop_rounded, size: 14),
                      label: const Text('取消', style: TextStyle(fontSize: 11)),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: AppColors.error, foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(horizontal: 8), visualDensity: VisualDensity.compact),
                    ),
                  ),
                ],
              )
            else
              _ActionBtn(
                '開始辨識',
                Icons.transcribe,
                _transcribeSelected,
                _selected.isEmpty,
                isPrimary: true,
              ),
          ]),
        ]),
      ),
      const SizedBox(height: 8),
      Row(children: [
        Text('Podcast (${_groups.length})  ·  ${_totalFiles} 個檔案', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
        const Spacer(),
        if (_selected.isNotEmpty) Text('已選 ${_selected.length}', style: const TextStyle(fontSize: 11, color: AppColors.accent)),
        const SizedBox(width: 6),
        IconButton(icon: const Icon(Icons.refresh, size: 14), tooltip: '重新整理',
          onPressed: () { setState(() => _loadingFiles = true); _loadFiles(); }, padding: EdgeInsets.zero, constraints: const BoxConstraints()),
      ]),
      const SizedBox(height: 4),
      Expanded(
        child: _groups.isEmpty
            ? Center(child: Column(mainAxisSize: MainAxisSize.min, children: [
                if (_loadingFiles)
                  const Text('載入中...', style: TextStyle(color: AppColors.textMuted, fontSize: 12))
                else if (_loadError != null)
                  Column(children: [
                    const Icon(Icons.error_outline, size: 32, color: AppColors.error),
                    const SizedBox(height: 8),
                    Text(_loadError!, style: const TextStyle(color: AppColors.error, fontSize: 11)),
                    const SizedBox(height: 8),
                    TextButton(onPressed: () { setState(() { _loadingFiles = true; _loadError = null; }); _loadFiles(); },
                        child: const Text('重試', style: TextStyle(fontSize: 11))),
                  ])
                else
                  Column(children: [
                    Icon(Icons.folder_open, size: 40, color: AppColors.textMuted.withValues(alpha: 0.4)),
                    const SizedBox(height: 8),
                    const Text('按上方重新整理載入 Podcast 列表', style: TextStyle(color: AppColors.textMuted, fontSize: 12)),
                  ]),
              ]))
            : ListView(children: _groups.entries.map((e) {
                final podcast = e.key; final files = e.value;
                final allSelected = files.every((f) => _selected.contains(f));
                final someSelected = files.any((f) => _selected.contains(f));
                return Container(
                  margin: const EdgeInsets.only(bottom: 6),
                  decoration: BoxDecoration(color: AppColors.card, borderRadius: BorderRadius.circular(10), border: Border.all(color: AppColors.border)),
                  child: Column(children: [
                    ListTile(dense: true,
                      onTap: () { setState(() { if (_expanded.contains(podcast)) _expanded.remove(podcast); else _expanded.add(podcast); }); },
                      leading: GestureDetector(
                        onTap: () => _toggleGroup(podcast),
                        child: Container(width: 28, height: 28,
                          decoration: BoxDecoration(color: allSelected ? AppColors.accent : AppColors.surfaceLight, borderRadius: BorderRadius.circular(6)),
                          child: Icon(allSelected ? Icons.check : (someSelected ? Icons.remove : Icons.podcasts), size: 14,
                              color: allSelected ? Colors.black : AppColors.textMuted)),
                      ),
                      title: Text(podcast, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                      subtitle: Text('${files.length} 集', style: const TextStyle(fontSize: 10, color: AppColors.textMuted)),
                      trailing: Icon(_expanded.contains(podcast) ? Icons.expand_less : Icons.expand_more, size: 16, color: AppColors.textMuted),
                    ),
                    if (_expanded.contains(podcast)) ...files.map((f) {
                      final name = f.split('\\').last;
                      final sel = _selected.contains(f);
                      final existingTxt = File(f.replaceAll(RegExp(r'\.\w+$'), '.txt')).existsSync();
                      return ListTile(dense: true, contentPadding: const EdgeInsets.only(left: 48, right: 8),
                        leading: GestureDetector(
                          onTap: () => _toggleSelect(f),
                          child: Container(width: 22, height: 22,
                            decoration: BoxDecoration(color: sel ? AppColors.accent : (existingTxt ? AppColors.accentDim : AppColors.surfaceLight),
                                borderRadius: BorderRadius.circular(5),
                                border: sel ? Border.all(color: AppColors.accent, width: 2) : null),
                            child: sel ? const Icon(Icons.check, size: 12, color: Colors.black)
                                : (existingTxt ? const Icon(Icons.check_circle, size: 12, color: AppColors.accent) : null)),
                        ),
                        title: Text(name, style: const TextStyle(fontSize: 10), maxLines: 1, overflow: TextOverflow.ellipsis),
                        subtitle: existingTxt ? const Text('✓ 已有逐字稿', style: TextStyle(fontSize: 9, color: AppColors.accent)) : null,
                        onTap: () => _toggleSelect(f),
                      );
                    }),
                  ]),
                );
              }).toList()),
        ),
      if (_jobs.isNotEmpty) ...[
        const SizedBox(height: 8),
        Container(padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(color: AppColors.card, borderRadius: BorderRadius.circular(10), border: Border.all(color: AppColors.border)),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Row(children: [
              const Icon(Icons.transcribe, size: 14, color: AppColors.accent), const SizedBox(width: 4),
              Text('辨識佇列 (${_jobs.where((j) => !j.done && !j.failed).length}/${_jobs.length})', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
              const Spacer(),
            ]),
            const SizedBox(height: 4),
            ..._jobs.reversed.take(10).map((j) {
              final icon = j.failed ? '❌' : (j.done ? (j.result?.startsWith('⏭️') == true ? '⏭️' : '✅') : '⏳');
              return Padding(padding: const EdgeInsets.symmetric(vertical: 2), child: Row(children: [
                Text(icon, style: const TextStyle(fontSize: 12)), const SizedBox(width: 6),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text(j.name, style: const TextStyle(fontSize: 11), maxLines: 1, overflow: TextOverflow.ellipsis),
                  if (j.failed && j.result != null)
                    Text(j.result!.length > 120 ? '${j.result!.substring(0, 120)}...' : j.result!,
                        style: const TextStyle(fontSize: 10, color: AppColors.error)),
                ])),
                if (!j.done && !j.failed) Text('${(j.progress * 100).toStringAsFixed(0)}%', style: const TextStyle(fontSize: 10, color: AppColors.accent)),
              ]));
            }),
          ]),
        ),
      ],
      const SizedBox(height: 12),
    ]);
  }
}

class _ActionBtn extends StatelessWidget {
  final String label; final IconData icon; final VoidCallback onPressed; final bool disabled; final bool isPrimary;
  const _ActionBtn(this.label, this.icon, this.onPressed, this.disabled, {this.isPrimary = false});

  @override
  Widget build(BuildContext context) {
    return ElevatedButton.icon(
      onPressed: disabled ? null : onPressed,
      icon: Icon(icon, size: 15),
      label: Text(label, style: const TextStyle(fontSize: 12)),
      style: ElevatedButton.styleFrom(
        backgroundColor: isPrimary ? AppColors.accent : AppColors.surfaceLight,
        foregroundColor: isPrimary ? Colors.black : AppColors.text,
        disabledBackgroundColor: AppColors.surfaceLight.withValues(alpha: 0.5),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      ),
    );
  }
}
