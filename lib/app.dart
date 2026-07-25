import 'dart:async';
import 'package:flutter/material.dart';
import 'widgets/dark_theme.dart';
import 'pages/library_page.dart';
import 'pages/pipeline_page.dart';
import 'pages/stats_page.dart';
import 'pages/settings_page.dart';
import 'pages/spotube_page.dart';
import 'pages/player_page.dart';
import 'pages/download_page.dart';
import 'services/i18n.dart';
import 'services/config_service.dart';
import 'services/update_service.dart';
import 'services/version_checker.dart';
import 'widgets/update_dialog.dart';

class PlaylistAdminApp extends StatefulWidget {
  const PlaylistAdminApp({super.key});
  @override
  State<PlaylistAdminApp> createState() => _PlaylistAdminAppState();
}

class _PlaylistAdminAppState extends State<PlaylistAdminApp> {
  @override
  void initState() {
    super.initState();
    I18N.instance.addListener(_onChanged);
    ConfigService.instance.addListener(_onChanged);
  }

  @override
  void dispose() {
    I18N.instance.removeListener(_onChanged);
    ConfigService.instance.removeListener(_onChanged);
    super.dispose();
  }

  void _onChanged() => setState(() {});

  @override
  Widget build(BuildContext context) {
    final isDark = ConfigService.instance.config.theme != 'light';
    return MaterialApp(
      title: t('app.title'),
      theme: isDark ? buildDarkTheme() : buildLightTheme(),
      darkTheme: buildDarkTheme(),
      themeMode: isDark ? ThemeMode.dark : ThemeMode.light,
      home: const MainShell(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class MainShell extends StatefulWidget {
  const MainShell({super.key});
  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  int _selectedIndex = 0;
  final _updateSvc = UpdateService.instance;
  BuildContext? _context;

  late List<_NavItemData> _navItems;

  final _pages = const [
    LibraryPage(),
    PlayerPage(),
    PipelinePage(),
    StatsPage(),
    DownloadPage(),
    SpotubePage(),
    SettingsPage(),
  ];

  @override
  void initState() {
    super.initState();
    _rebuildNav();
    I18N.instance.addListener(_rebuildNav);
    _updateSvc.addListener(_onUpdate);
    _checkForUpdates();
    // Periodic check every 30 minutes while app is running
    Timer.periodic(const Duration(minutes: 30), (_) => _checkForUpdates());
  }

  void _onUpdate() {
    if (mounted) setState(() {});
    if (_updateSvc.state == UpdateState.ready && mounted && _context != null) {
      ScaffoldMessenger.maybeOf(_context!)?.showSnackBar(
        SnackBar(
          content: const Text('更新已下載完成，點擊側邊欄「安裝更新」'),
          behavior: SnackBarBehavior.floating,
          duration: const Duration(seconds: 5),
          action: SnackBarAction(label: '安裝', onPressed: _updateSvc.launchInstaller),
        ),
      );
    }
  }

  void _checkForUpdates() {
    if (!VersionChecker.shouldCheck()) return;
    Future.delayed(const Duration(seconds: 3), () async {
      final info = await VersionChecker.checkForUpdate();
      if (!info.hasUpdate) return;
      if (!mounted) return;
      if (ConfigService.instance.config.autoDownloadUpdate) {
        _updateSvc.startDownload(info);
      } else {
        showDialog(context: context, builder: (_) => UpdateDialog(info: info));
      }
    });
  }

  @override
  void dispose() {
    I18N.instance.removeListener(_rebuildNav);
    super.dispose();
  }

  void _rebuildNav() {
    setState(() {
      _navItems = [
        _NavItemData(Icons.library_music_outlined, Icons.library_music, t('app.sidebar.library')),
        _NavItemData(Icons.music_note_outlined, Icons.music_note, t('app.sidebar.player')),
        _NavItemData(Icons.play_circle_outline, Icons.play_circle_filled, t('app.sidebar.pipeline')),
        _NavItemData(Icons.bar_chart_rounded, Icons.bar_chart_rounded, t('app.sidebar.stats')),
        _NavItemData(Icons.cloud_download_outlined, Icons.cloud_download, t('app.sidebar.download')),
        _NavItemData(Icons.download_outlined, Icons.download, t('app.sidebar.spotube')),
        _NavItemData(Icons.settings_outlined, Icons.settings, t('app.sidebar.settings')),
      ];
    });
  }

  @override
  Widget build(BuildContext context) {
    _context = context;
    return Scaffold(
      body: Row(
        children: [
          _Sidebar(
            items: _navItems,
            selectedIndex: _selectedIndex,
            onSelected: (i) {
              setState(() => _selectedIndex = i);
            },
          ),
          Expanded(
            child: Column(
            children: [
              _Header(title: _navItems[_selectedIndex].label),
              Expanded(
                child: IndexedStack(
                  index: _selectedIndex,
                  children: _pages,
                ),
              ),
            ],
          ),
          ),
        ],
      ),
    );
  }
}

class _NavItemData {
  final IconData icon;
  final IconData activeIcon;
  final String label;
  const _NavItemData(this.icon, this.activeIcon, this.label);
}

class _Sidebar extends StatelessWidget {
  final List<_NavItemData> items;
  final int selectedIndex;
  final ValueChanged<int> onSelected;
  static final _updateSvc = UpdateService.instance;
  const _Sidebar({required this.items, required this.selectedIndex, required this.onSelected});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 220,
      decoration: const BoxDecoration(
        color: Color(0xFF111111),
        border: Border(right: BorderSide(color: AppColors.border, width: 1)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: 20),
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
            child: Row(
              children: [
                Container(
                  width: 36, height: 36,
                  decoration: const BoxDecoration(
                    color: AppColors.accent,
                    borderRadius: BorderRadius.all(Radius.circular(10)),
                  ),
                  child: const Icon(Icons.queue_music_rounded, color: Colors.black, size: 20),
                ),
                const SizedBox(width: 10),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(t('app.sidebar.playlist'), style: const TextStyle(color: AppColors.text, fontSize: 15, fontWeight: FontWeight.bold)),
                    Text(t('app.sidebar.admin'), style: const TextStyle(color: AppColors.textMuted, fontSize: 10, letterSpacing: 1.2)),
                  ],
                ),
              ],
            ),
          ),
          const Divider(indent: 20, endIndent: 20),
          const SizedBox(height: 8),
          ...List.generate(items.length, (i) {
            final item = items[i];
            final selected = i == selectedIndex;
            return Container(
              margin: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
              decoration: BoxDecoration(
                color: selected ? AppColors.accentDim : null,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Material(
                color: Colors.transparent,
                child: InkWell(
                  borderRadius: BorderRadius.circular(10),
                  onTap: () => onSelected(i),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    child: Row(
                      children: [
                        Icon(
                          selected ? item.activeIcon : item.icon,
                          color: selected ? AppColors.accent : AppColors.textMuted,
                          size: 20,
                        ),
                        const SizedBox(width: 12),
                        Text(
                          item.label,
                          style: TextStyle(
                            color: selected ? AppColors.text : AppColors.textSecondary,
                            fontSize: 13,
                            fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
                          ),
                        ),
                        const Spacer(),
                        if (selected)
                          Container(
                            width: 3, height: 16,
                            decoration: const BoxDecoration(
                              color: AppColors.accent,
                              borderRadius: BorderRadius.all(Radius.circular(2)),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          }),
          const Spacer(),
          if (_updateSvc.state == UpdateState.downloading)
            GestureDetector(
              onTap: () => onSelected(2),
              child: Container(
                margin: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                child: Column(children: [
                  Row(children: [
                    const Icon(Icons.system_update, size: 12, color: AppColors.accent),
                    const SizedBox(width: 4),
                    const Text('更新下載中', style: TextStyle(color: AppColors.accent, fontSize: 9)),
                    const Spacer(),
                    Text('${(_updateSvc.progress * 100).toStringAsFixed(0)}%',
                        style: const TextStyle(color: AppColors.accent, fontSize: 9)),
                  ]),
                  const SizedBox(height: 4),
                  ClipRRect(borderRadius: BorderRadius.circular(2),
                    child: LinearProgressIndicator(value: _updateSvc.progress, minHeight: 3,
                        backgroundColor: AppColors.surfaceLight,
                        valueColor: const AlwaysStoppedAnimation(AppColors.accent)),
                  ),
                ]),
              ),
            ),
          if (_updateSvc.state == UpdateState.ready)
            GestureDetector(
              onTap: _updateSvc.launchInstaller,
              child: Container(
                margin: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 10),
                decoration: BoxDecoration(color: AppColors.accentDim, borderRadius: BorderRadius.circular(8)),
                child: Row(children: [
                  const Icon(Icons.check_circle, size: 12, color: AppColors.accent),
                  const SizedBox(width: 4),
                  const Text('安裝更新', style: TextStyle(color: AppColors.accent, fontSize: 10, fontWeight: FontWeight.w600)),
                ]),
              ),
            ),
          Container(
            margin: const EdgeInsets.all(16),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppColors.accentDim,
              borderRadius: BorderRadius.circular(10),
            ),
            child: Row(
              children: [
                const Icon(Icons.info_outline, color: AppColors.accent, size: 14),
                const SizedBox(width: 8),
                Text(t('app.version'), style: TextStyle(color: AppColors.accent, fontSize: 11, fontWeight: FontWeight.w500)),
                const Spacer(),
                Text('Flutter', style: TextStyle(color: AppColors.accent.withValues(alpha: 0.7), fontSize: 10)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  final String title;
  const _Header({required this.title});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
      decoration: const BoxDecoration(
        color: AppColors.bg,
        border: Border(bottom: BorderSide(color: AppColors.border, width: 1)),
      ),
      child: Row(
        children: [
          Text(title, style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w700, letterSpacing: -0.3)),
          const Spacer(),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
            decoration: BoxDecoration(
              color: AppColors.accentDim,
              borderRadius: BorderRadius.circular(6),
            ),
              child: const Text('PLAYLIST ADMIN', style: TextStyle(color: AppColors.accent, fontSize: 9, letterSpacing: 1.5)),
          ),
        ],
      ),
    );
  }
}
