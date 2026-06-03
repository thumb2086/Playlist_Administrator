import 'package:flutter/material.dart';
import 'widgets/dark_theme.dart';
import 'pages/library_page.dart';
import 'pages/pipeline_page.dart';
import 'pages/stats_page.dart';
import 'pages/settings_page.dart';
import 'pages/spotube_page.dart';

class PlaylistAdminApp extends StatelessWidget {
  const PlaylistAdminApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Playlist Administrator',
      theme: buildDarkTheme(),
      darkTheme: buildDarkTheme(),
      themeMode: ThemeMode.dark,
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

  final _pages = const [
    LibraryPage(),
    PipelinePage(),
    StatsPage(),
    SpotubePage(),
    SettingsPage(),
  ];

  final _titles = [
    '歌單庫',
    'Pipeline',
    '統計',
    'Spotube',
    '設定',
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Row(
        children: [
          _Sidebar(
            selectedIndex: _selectedIndex,
            onSelected: (i) => setState(() => _selectedIndex = i),
          ),
          Expanded(
            child: Column(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
                  decoration: const BoxDecoration(
                    border: Border(bottom: BorderSide(color: Color(0xFF2a2a2a))),
                  ),
                  child: Row(
                    children: [
                      Text(_titles[_selectedIndex],
                          style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                      const Spacer(),
                      Text('Playlist Administrator v2',
                          style: TextStyle(color: Colors.grey[600], fontSize: 12)),
                    ],
                  ),
                ),
                Expanded(child: _pages[_selectedIndex]),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Sidebar extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> onSelected;
  const _Sidebar({required this.selectedIndex, required this.onSelected});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 200,
      decoration: const BoxDecoration(
        color: Color(0xFF1a1a1a),
        border: Border(right: BorderSide(color: Color(0xFF2a2a2a))),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(16, 24, 16, 24),
            child: Row(
              children: [
                Icon(Icons.queue_music, color: Color(0xFF1DB954), size: 28),
                SizedBox(width: 8),
                Text('Playlist Admin',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              ],
            ),
          ),
          const Divider(color: Color(0xFF2a2a2a)),
          _NavItem(icon: Icons.library_music, label: '歌單庫', index: 0, selectedIndex: selectedIndex, onSelected: onSelected),
          _NavItem(icon: Icons.play_circle, label: 'Pipeline', index: 1, selectedIndex: selectedIndex, onSelected: onSelected),
          _NavItem(icon: Icons.bar_chart, label: '統計', index: 2, selectedIndex: selectedIndex, onSelected: onSelected),
          _NavItem(icon: Icons.download, label: 'Spotube', index: 3, selectedIndex: selectedIndex, onSelected: onSelected),
          _NavItem(icon: Icons.settings, label: '設定', index: 4, selectedIndex: selectedIndex, onSelected: onSelected),
        ],
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final int index;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  const _NavItem({
    required this.icon,
    required this.label,
    required this.index,
    required this.selectedIndex,
    required this.onSelected,
  });

  @override
  Widget build(BuildContext context) {
    final selected = index == selectedIndex;
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: selected ? const Color(0xFF2a2a2a) : null,
        borderRadius: BorderRadius.circular(8),
      ),
      child: ListTile(
        dense: true,
        leading: Icon(icon, color: selected ? const Color(0xFF1DB954) : Colors.grey, size: 20),
        title: Text(label, style: TextStyle(color: selected ? Colors.white : Colors.grey[400], fontSize: 14)),
        onTap: () => onSelected(index),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
    );
  }
}
