import 'package:flutter/foundation.dart';
import '../version.dart';

class I18N extends ChangeNotifier {
  I18N._();
  static final I18N instance = I18N._();

  String _lang = 'zh-TW';
  String get currentLang => _lang;
  bool get isZh => _lang == 'zh-TW';

  void setLanguage(String lang) {
    if (_lang == lang) return;
    _lang = lang;
    notifyListeners();
  }

  String t(String key, [List<dynamic>? args]) {
    final map = _lang == 'en' ? _en : _zh;
    String text = map[key] ?? key;
    if (args != null && args.isNotEmpty) {
      for (int i = 0; i < args.length; i++) {
        text = text.replaceFirst('{$i}', args[i].toString());
      }
    }
    return text;
  }

  static final Map<String, String> _zh = {
    // App
    'app.title': '播放清單管理',
    'app.sidebar.library': '歌單庫',
    'app.sidebar.player': '播放器',
    'app.sidebar.pipeline': 'Pipeline',
    'app.sidebar.stats': '統計',
    'app.sidebar.spotube': 'Spotube',
    'app.sidebar.settings': '設定',
    'app.sidebar.playlist': 'Playlist',
    'app.sidebar.admin': 'Administrator',
    'app.version': 'v$appVersion',
    'app.header.badge': 'PLAYLIST ADMIN',

    // Library
    'library.url_hint': '貼上 Spotify 播放清單 URL…',
    'library.add_btn': '加入',
    'library.refresh': '重新整理',
    'library.empty_title': '尚未加入歌單',
    'library.empty_subtitle': '貼上 Spotify URL 開始',
    'library.stats_playlists': '歌單',
    'library.stats_songs': '歌曲',
    'library.stats_matched': '已匹配',
    'library.stats_completion': '完成率',
    'library.song_count': '{0}/{1} 首',

    // Pipeline
    'pipeline.step_convert': '轉檔',
    'pipeline.step_scrape': '爬取',
    'pipeline.step_prune': '清理',
    'pipeline.step_unsorted': '分類',
    'pipeline.step_metadata': '元資料',
    'pipeline.run_all': '完整流程',
    'pipeline.run_convert': '只轉檔',
    'pipeline.run_scrape': '只爬取',
    'pipeline.run_prune': '只清理',
    'pipeline.pause': '暫停',
    'pipeline.cancel': '取消',
    'pipeline.clear_log': '清除日誌',
    'pipeline.starting': 'Pipeline 啟動中…',
    'pipeline.log_placeholder': '日誌將顯示在這裡',
    'pipeline.cancelled': 'Pipeline 已取消',
    'pipeline.complete': 'Pipeline 完成',

    // Stats
    'stats.total_files': '總檔案',
    'stats.mp3': 'MP3',
    'stats.m4a': 'M4A',
    'stats.flac': 'FLAC',
    'stats.storage': '容量',
    'stats.saved': '節省空間',
    'stats.duplicates': '重複歌曲',
    'stats.dual_format': '雙格式',
    'stats.playlists': '播放清單',
    'stats.entries': '歌曲條目',
    'stats.format_distribution': '格式分布',
    'stats.refresh': '重新整理資料',

    // Spotube
    'spotube.status_ready': '就緒',
    'spotube.status_downloading': '下載中…',
    'spotube.status_error': '錯誤',
    'spotube.status_done': '完成',
    'spotube.status_cancelled': '已取消',
    'spotube.cancelled': '下載已取消',
    'spotube.status_moving': '搬移中…',
    'spotube.status_moved': '搬移完成',
    'spotube.download_all': '下載全部',
    'spotube.move_m4a': '搬移 M4A',
    'spotube.cancel': '取消',
    'spotube.reset_records': '重設記錄',
    'spotube.download_records': '下載記錄',
    'spotube.log': '日誌',
    'spotube.no_records': '尚無下載記錄',
    'spotube.log_placeholder': '日誌將顯示在這裡',
    'spotube.count_downloaded': '{0} 個已下載',
    'spotube.records_reset': '已重設下載記錄',
    'spotube.not_running': 'Spotube 未執行',
    'spotube.download_complete': '下載完成',
    'spotube.move_complete': '搬移完成: {0} 個檔案',
    'spotube.move_failed': '搬移失敗',
    'spotube.calibrate': '校準座標',

    // Settings
    'settings.general': '一般設定',
    'settings.library_path': '音樂庫路徑',
    'settings.thread_count': '轉檔執行緒數',
    'settings.ffmpeg_path': 'FFmpeg 路徑',
    'settings.language': '語言',
    'settings.theme': '主題',
    'settings.debug_mode': '除錯模式',
    'settings.metadata_enrich': 'Metadata 增強',
    'settings.auto_update_check': '自動檢查更新',
    'settings.spotube': 'Spotube 自動化',
    'settings.spotube_exe': '執行檔路徑',
    'settings.spotube_dl_path': '下載路徑',
    'settings.exact_match': '精確檔名比對',
    'settings.convert_matched_only': '只轉換有匹配的歌',
    'settings.lyrics_section': '歌詞設定',
    'settings.lyrics_folder': '歌詞資料夾',
    'settings.retroactive_lyrics': '回溯取得歌詞',
    'settings.save': '儲存設定',
    'settings.saved': '設定已儲存',
    'settings.search_aliases': '搜尋別名',
    'settings.no_aliases': '尚無別名，點擊下方新增',
    'settings.add_alias': '新增別名',

    // Player
    'player.select_playlist': '請選擇播放清單',
    'player.no_lyrics': '(無同步歌詞)',
    'player.lyric_offset': '歌詞偏移',

    // Common
    'common.loading': '載入中…',
    'common.error': '錯誤',
    'common.success': '成功',
    'common.skip': '跳過',
    'common.done': '完成',
    'common.failed': '失敗',
    'common.cancelled': '取消',
  };

  static final Map<String, String> _en = {
    'app.title': 'Playlist Administrator',
    'app.sidebar.library': 'Library',
    'app.sidebar.player': 'Player',
    'app.sidebar.pipeline': 'Pipeline',
    'app.sidebar.stats': 'Stats',
    'app.sidebar.spotube': 'Spotube',
    'app.sidebar.settings': 'Settings',
    'app.sidebar.playlist': 'Playlist',
    'app.sidebar.admin': 'Administrator',
    'app.version': 'v$appVersion',
    'app.header.badge': 'PLAYLIST ADMIN',

    'library.url_hint': 'Paste Spotify playlist URL…',
    'library.add_btn': 'Add',
    'library.refresh': 'Refresh',
    'library.empty_title': 'No playlists yet',
    'library.empty_subtitle': 'Paste a Spotify URL to get started',
    'library.stats_playlists': 'Playlists',
    'library.stats_songs': 'Songs',
    'library.stats_matched': 'Matched',
    'library.stats_completion': 'Complete',
    'library.song_count': '{0}/{1} songs',

    'pipeline.step_convert': 'Convert',
    'pipeline.step_scrape': 'Scrape',
    'pipeline.step_prune': 'Prune',
    'pipeline.step_unsorted': 'Sort',
    'pipeline.step_metadata': 'Metadata',
    'pipeline.run_all': 'Full Pipeline',
    'pipeline.run_convert': 'Convert Only',
    'pipeline.run_scrape': 'Scrape Only',
    'pipeline.run_prune': 'Prune Only',
    'pipeline.pause': 'Pause',
    'pipeline.cancel': 'Cancel',
    'pipeline.clear_log': 'Clear Log',
    'pipeline.starting': 'Pipeline starting…',
    'pipeline.log_placeholder': 'Log will appear here',
    'pipeline.cancelled': 'Pipeline cancelled',
    'pipeline.complete': 'Pipeline complete',

    'stats.total_files': 'Total Files',
    'stats.mp3': 'MP3',
    'stats.m4a': 'M4A',
    'stats.flac': 'FLAC',
    'stats.storage': 'Storage',
    'stats.saved': 'Space Saved',
    'stats.duplicates': 'Duplicates',
    'stats.dual_format': 'Dual Format',
    'stats.playlists': 'Playlists',
    'stats.entries': 'Entries',
    'stats.format_distribution': 'Format Distribution',
    'stats.refresh': 'Refresh Data',

    'spotube.status_ready': 'Ready',
    'spotube.status_downloading': 'Downloading…',
    'spotube.status_error': 'Error',
    'spotube.status_done': 'Complete',
    'spotube.status_cancelled': 'Cancelled',
    'spotube.cancelled': 'Download cancelled',
    'spotube.status_moving': 'Moving…',
    'spotube.status_moved': 'Move Complete',
    'spotube.download_all': 'Download All',
    'spotube.move_m4a': 'Move M4A',
    'spotube.cancel': 'Cancel',
    'spotube.reset_records': 'Reset Records',
    'spotube.download_records': 'Download Records',
    'spotube.log': 'Log',
    'spotube.no_records': 'No records yet',
    'spotube.log_placeholder': 'Log will appear here',
    'spotube.count_downloaded': '{0} downloaded',
    'spotube.records_reset': 'Download records reset',
    'spotube.not_running': 'Spotube is not running',
    'spotube.download_complete': 'Download complete',
    'spotube.move_complete': 'Moved {0} files',
    'spotube.move_failed': 'Move failed',
    'spotube.calibrate': 'Calibrate',

    'settings.general': 'General',
    'settings.library_path': 'Library Path',
    'settings.thread_count': 'Converter Threads',
    'settings.ffmpeg_path': 'FFmpeg Path',
    'settings.language': 'Language',
    'settings.theme': 'Theme',
    'settings.debug_mode': 'Debug Mode',
    'settings.metadata_enrich': 'Metadata Enrichment',
    'settings.auto_update_check': 'Auto Update Check',
    'settings.spotube': 'Spotube Automation',
    'settings.spotube_exe': 'Executable Path',
    'settings.spotube_dl_path': 'Download Path',
    'settings.exact_match': 'Exact Filename Match',
    'settings.convert_matched_only': 'Convert Matched Only',
    'settings.lyrics_section': 'Lyrics',
    'settings.lyrics_folder': 'Lyrics Folder',
    'settings.retroactive_lyrics': 'Retroactive Lyrics',
    'settings.save': 'Save',
    'settings.saved': 'Settings saved',
    'settings.search_aliases': 'Search Aliases',
    'settings.no_aliases': 'No aliases yet, tap Add below',
    'settings.add_alias': 'Add Alias',


    // Player
    'player.select_playlist': 'Select a playlist',
    'player.no_lyrics': '(No synced lyrics)',
    'player.lyric_offset': 'Lyric Offset',

    'common.loading': 'Loading…',
    'common.error': 'Error',
    'common.success': 'Success',
    'common.skip': 'Skip',
    'common.done': 'Done',
    'common.failed': 'Failed',
    'common.cancelled': 'Cancelled',
  };
}

String t(String key, [List<dynamic>? args]) => I18N.instance.t(key, args);
