import 'package:flutter/material.dart';
import '../services/config_service.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});
  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  late TextEditingController _basePathCtrl;
  late TextEditingController _workersCtrl;
  late TextEditingController _ffmpegPathCtrl;
  late TextEditingController _spotubeExeCtrl;
  late TextEditingController _spotubeDlCtrl;

  @override
  void initState() {
    super.initState();
    final c = ConfigService.instance.config;
    _basePathCtrl = TextEditingController(text: c.basePath);
    _workersCtrl = TextEditingController(text: c.maxThreads.toString());
    _ffmpegPathCtrl = TextEditingController(text: c.ffmpegPath);
    _spotubeExeCtrl = TextEditingController(text: c.spotubeExePath);
    _spotubeDlCtrl = TextEditingController(text: c.spotubeDownloadPath);
  }

  @override
  void dispose() {
    _basePathCtrl.dispose();
    _workersCtrl.dispose();
    _ffmpegPathCtrl.dispose();
    _spotubeExeCtrl.dispose();
    _spotubeDlCtrl.dispose();
    super.dispose();
  }

  void _save() {
    final c = ConfigService.instance.config;
    c.basePath = _basePathCtrl.text;
    c.maxThreads = int.tryParse(_workersCtrl.text) ?? 4;
    c.ffmpegPath = _ffmpegPathCtrl.text;
    c.spotubeExePath = _spotubeExeCtrl.text;
    c.spotubeDownloadPath = _spotubeDlCtrl.text;
    ConfigService.instance.save();
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('設定已儲存'), duration: Duration(seconds: 1)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final c = ConfigService.instance.config;
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _Section('一般設定', [
          _TextField('Library 路徑', _basePathCtrl, 'C:\\Users\\CPXru\\Music\\Spotube'),
          _TextField('轉換執行緒數', _workersCtrl, '4'),
          _TextField('FFmpeg 路徑', _ffmpegPathCtrl, 'bin/ffmpeg.exe'),
          _Switch('啟用 Debug 模式', c.debugMode, (v) { c.debugMode = v; _save(); }),
          _Switch('Metadata 強化', c.enableMetadataEnrichment, (v) { c.enableMetadataEnrichment = v; _save(); }),
        ]),
        const SizedBox(height: 12),
        _Section('Spotube 自動化', [
          _TextField('執行檔路徑', _spotubeExeCtrl, 'auto-detect'),
          _TextField('下載路徑', _spotubeDlCtrl, r'%USERPROFILE%\Downloads\Spotube'),
          _Switch('檔名精確比對', c.spotubeExactMatch, (v) { c.spotubeExactMatch = v; _save(); }),
          _Switch('只轉換符合歌單的檔案', c.spotubeConvertMatchedOnly, (v) { c.spotubeConvertMatchedOnly = v; _save(); }),
        ]),
        const SizedBox(height: 12),
        _Section('搜尋別名 (search_names)', [
          ...c.searchNames.entries.map((e) => Padding(
            padding: const EdgeInsets.only(bottom: 4),
            child: Row(
              children: [
                Expanded(flex: 2, child: Text(e.key, style: const TextStyle(fontSize: 12))),
                const Icon(Icons.arrow_forward, size: 14, color: Colors.grey),
                Expanded(flex: 2, child: Text(e.value, style: const TextStyle(fontSize: 12))),
              ],
            ),
          )),
          if (c.searchNames.isEmpty)
            const Text('無別名設定', style: TextStyle(color: Colors.grey, fontSize: 12)),
        ]),
        const SizedBox(height: 16),
        Center(
          child: ElevatedButton(
            onPressed: _save,
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF1DB954),
              foregroundColor: Colors.black,
              padding: const EdgeInsets.symmetric(horizontal: 48, vertical: 14),
            ),
            child: const Text('儲存設定', style: TextStyle(fontWeight: FontWeight.bold)),
          ),
        ),
      ],
    );
  }
}

class _Section extends StatelessWidget {
  final String title;
  final List<Widget> children;
  const _Section(this.title, this.children);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1e1e1e),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF2a2a2a)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
          const SizedBox(height: 12),
          ...children,
        ],
      ),
    );
  }
}

class _TextField extends StatelessWidget {
  final String label;
  final TextEditingController controller;
  final String hint;
  const _TextField(this.label, this.controller, this.hint);

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: TextField(
        controller: controller,
        decoration: InputDecoration(
          labelText: label,
          hintText: hint,
          border: const OutlineInputBorder(),
          contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          filled: true,
        ),
        style: const TextStyle(fontSize: 13),
      ),
    );
  }
}

class _Switch extends StatelessWidget {
  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;
  const _Switch(this.label, this.value, this.onChanged);

  @override
  Widget build(BuildContext context) {
    return SwitchListTile(
      title: Text(label, style: const TextStyle(fontSize: 13)),
      value: value,
      onChanged: onChanged,
      dense: true,
      contentPadding: EdgeInsets.zero,
    );
  }
}
