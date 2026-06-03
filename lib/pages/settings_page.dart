import 'package:flutter/material.dart';
import '../services/config_service.dart';
import '../widgets/dark_theme.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});
  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  late TextEditingController _basePathCtrl, _workersCtrl, _ffmpegCtrl, _spotubeExeCtrl, _spotubeDlCtrl;

  @override
  void initState() {
    super.initState();
    final c = ConfigService.instance.config;
    _basePathCtrl = TextEditingController(text: c.basePath);
    _workersCtrl = TextEditingController(text: c.maxThreads.toString());
    _ffmpegCtrl = TextEditingController(text: c.ffmpegPath);
    _spotubeExeCtrl = TextEditingController(text: c.spotubeExePath);
    _spotubeDlCtrl = TextEditingController(text: c.spotubeDownloadPath);
  }

  @override
  void dispose() {
    _basePathCtrl.dispose(); _workersCtrl.dispose(); _ffmpegCtrl.dispose();
    _spotubeExeCtrl.dispose(); _spotubeDlCtrl.dispose();
    super.dispose();
  }

  void _save() {
    final c = ConfigService.instance.config;
    c.basePath = _basePathCtrl.text; c.maxThreads = int.tryParse(_workersCtrl.text) ?? 4;
    c.ffmpegPath = _ffmpegCtrl.text; c.spotubeExePath = _spotubeExeCtrl.text; c.spotubeDownloadPath = _spotubeDlCtrl.text;
    ConfigService.instance.save();
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('設定已儲存'), duration: Duration(seconds: 1)));
  }

  @override
  Widget build(BuildContext context) {
    final c = ConfigService.instance.config;
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: ListView(children: [
        _Section('一般設定', [
          _Field('Library 路徑', _basePathCtrl, 'C:\\Users\\CPXru\\Music\\Spotube'),
          _Field('轉換執行緒數', _workersCtrl, '4'),
          _Field('FFmpeg 路徑', _ffmpegCtrl, 'bin/ffmpeg.exe'),
          _Toggle('Debug 模式', c.debugMode, (v) { c.debugMode = v; _save(); }),
          _Toggle('Metadata 強化', c.enableMetadataEnrichment, (v) { c.enableMetadataEnrichment = v; _save(); }),
        ]),
        const SizedBox(height: 12),
        _Section('Spotube 自動化', [
          _Field('執行檔路徑', _spotubeExeCtrl, 'auto-detect'),
          _Field('下載路徑', _spotubeDlCtrl, r'%USERPROFILE%\Downloads\Spotube'),
          _Toggle('檔名精確比對', c.spotubeExactMatch, (v) { c.spotubeExactMatch = v; _save(); }),
          _Toggle('只轉換符合歌單的檔案', c.spotubeConvertMatchedOnly, (v) { c.spotubeConvertMatchedOnly = v; _save(); }),
        ]),
        const SizedBox(height: 12),
        _Section('搜尋別名', [
          if (c.searchNames.isEmpty)
            const Padding(padding: EdgeInsets.only(bottom: 8), child:
              Text('無別名設定\n在 config.json 中加入 "search_names"', style: TextStyle(color: AppColors.textMuted, fontSize: 12)),
            )
          else
            ...c.searchNames.entries.map((e) => Padding(padding: const EdgeInsets.only(bottom: 4), child:
              Row(children: [
                Expanded(flex: 2, child: Text(e.key, style: const TextStyle(fontSize: 12, color: AppColors.textSecondary))),
                const Icon(Icons.arrow_forward, size: 14, color: AppColors.textMuted),
                Expanded(flex: 2, child: Text(e.value, style: const TextStyle(fontSize: 12))),
              ]),
            )),
        ]),
        const SizedBox(height: 20),
        Center(
          child: Container(
            decoration: BoxDecoration(
              gradient: const LinearGradient(colors: [AppColors.accent, Color(0xFF169C46)]),
              borderRadius: BorderRadius.circular(10),
            ),
            child: ElevatedButton(
              onPressed: _save,
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.transparent, shadowColor: Colors.transparent,
                foregroundColor: Colors.black, padding: const EdgeInsets.symmetric(horizontal: 48, vertical: 14),
              ),
              child: const Text('儲存設定', style: TextStyle(fontWeight: FontWeight.bold)),
            ),
          ),
        ),
        const SizedBox(height: 24),
      ]),
    );
  }
}

class _Section extends StatelessWidget {
  final String title; final List<Widget> children;
  const _Section(this.title, this.children);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.card, borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(title, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
        const SizedBox(height: 14), ...children,
      ]),
    );
  }
}

class _Field extends StatelessWidget {
  final String label; final TextEditingController controller; final String hint;
  const _Field(this.label, this.controller, this.hint);

  @override
  Widget build(BuildContext context) {
    return Padding(padding: const EdgeInsets.only(bottom: 10), child:
      TextField(controller: controller,
        decoration: InputDecoration(labelText: label, hintText: hint, border: const OutlineInputBorder()),
        style: const TextStyle(fontSize: 13),
      ),
    );
  }
}

class _Toggle extends StatelessWidget {
  final String label; final bool value; final ValueChanged<bool> onChanged;
  const _Toggle(this.label, this.value, this.onChanged);

  @override
  Widget build(BuildContext context) {
    return SwitchListTile(
      title: Text(label, style: const TextStyle(fontSize: 13)),
      value: value, onChanged: onChanged, dense: true, contentPadding: EdgeInsets.zero,
      activeTrackColor: AppColors.accent,
    );
  }
}
