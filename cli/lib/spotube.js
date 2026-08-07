import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import readline from 'node:readline';
import { spawn } from 'node:child_process';
import { sleep } from './util.js';

// PowerShell P/Invoke worker — Windows UI automation (user32.dll).
const WORKER_CS = String.raw`
using System;
using System.Text;
using System.Runtime.InteropServices;
public class U {
  public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
  [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc cb, IntPtr lParam);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder sb, int maxCount);
  [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int cmd);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool IsWindow(IntPtr hWnd);
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int x, int y);
  [DllImport("user32.dll")] public static extern void mouse_event(uint flags, uint dx, uint dy, uint data, UIntPtr extraInfo);
  [DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extraInfo);
  [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vKey);
  [DllImport("user32.dll")] public static extern IntPtr GetDC(IntPtr hwnd);
  [DllImport("user32.dll")] public static extern int ReleaseDC(IntPtr hwnd, IntPtr dc);
  [DllImport("gdi32.dll")] public static extern uint GetPixel(IntPtr dc, int x, int y);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
  public static IntPtr FindSpotube() {
    IntPtr found = IntPtr.Zero;
    EnumWindows((h, l) => {
      int len = GetWindowTextLength(h);
      if (len > 0) {
        StringBuilder sb = new StringBuilder(len + 1);
        GetWindowText(h, sb, len + 1);
        if (sb.ToString().ToLower().Contains("spotube")) { found = h; return false; }
      }
      return true;
    }, IntPtr.Zero);
    return found;
  }
  public static int[] Rect(IntPtr h) { RECT r; GetWindowRect(h, out r); return new int[] { r.Left, r.Top, r.Right, r.Bottom }; }
  public static void Click(int x, int y) {
    SetCursorPos(x, y);
    mouse_event(0x0002, 0, 0, 0, UIntPtr.Zero); // LEFTDOWN
    mouse_event(0x0004, 0, 0, 0, UIntPtr.Zero); // LEFTUP
  }
  public static void Key(byte vk, bool up) {
    keybd_event(vk, 0, up ? (byte)0x0002 : (byte)0, UIntPtr.Zero);
  }
  public static void TypeChar(int ch) {
    keybd_event(0, (byte)(ch & 0xFF), 0x0004, UIntPtr.Zero); // KEYEVENTF_UNICODE down
    keybd_event(0, (byte)(ch & 0xFF), 0x0004 | 0x0002, UIntPtr.Zero); // up
  }
  public static bool EscDown() { return (GetAsyncKeyState(0x1B) & 0x8000) != 0; }
  public static int Pixel(int x, int y) {
    IntPtr dc = GetDC(IntPtr.Zero);
    uint p = GetPixel(dc, x, y);
    ReleaseDC(IntPtr.Zero, dc);
    return (int)((p & 0xFF) + ((p >> 8) & 0xFF) + ((p >> 16) & 0xFF)) / 3;
  }
  public static void Activate(IntPtr h) {
    if (IsIconic(h)) ShowWindow(h, 9); // SW_RESTORE
    SetForegroundWindow(h);
  }
}
`;

const PS_SCRIPT = `
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
${WORKER_CS}
'@ -Language CSharp
$reader = [System.IO.StreamReader]::new([System.Console]::OpenStandardInput())
while ($true) {
  $line = $reader.ReadLine()
  if ($null -eq $line) { break }
  try {
    $req = $line | ConvertFrom-Json
    $cmd = $req.cmd
    $r = $null
    switch ($cmd) {
      'find'      { $r = @([U]::FindSpotube().ToInt64()) }
      'rect'      { $r = [U]::Rect([IntPtr]$req.args[0]) }
      'activate'  { [U]::Activate([IntPtr]$req.args[0]); $r = @($true) }
      'foreground'{ $r = @([U]::GetForegroundWindow().ToInt64()) }
      'minimize'  { [U]::ShowWindow([IntPtr]$req.args[0], 6); $r = @($true) }
      'maximize'  { [U]::ShowWindow([IntPtr]$req.args[0], 3); $r = @($true) }
      'click'     { [U]::Click([int]$req.args[0], [int]$req.args[1]); $r = @($true) }
      'vk'        { [U]::Key([byte]$req.args[0], [bool]$req.args[1]); $r = @($true) }
      'type'      { [U]::TypeChar([int]$req.args[0]); $r = @($true) }
      'pixel'     { $r = @([U]::Pixel([int]$req.args[0], [int]$req.args[1])) }
      'esc'       { $r = @([U]::EscDown()) }
      'sleep'     {
        $ms = [int]$req.args[0]
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        $aborted = $false
        while ($sw.ElapsedMilliseconds -lt $ms) {
          if ([U]::EscDown()) { $aborted = $true; break }
          Start-Sleep -Milliseconds 20
        }
        $r = @($aborted)
      }
      'exit'      { break }
    }
    [Console]::Out.WriteLine(("{0}" -f (@{ ok = $true; data = $r } | ConvertTo-Json -Compress -Depth 5)))
    [Console]::Out.Flush()
    if ($cmd -eq 'exit') { break }
  } catch {
    [Console]::Out.WriteLine(("{0}" -f (@{ ok = $false; error = $_.Exception.Message } | ConvertTo-Json -Compress)))
    [Console]::Out.Flush()
  }
}
`;

const defaultCoords = {
  sidebar_library: [30, 280],
  library_filter: [200, 100],
  first_playlist_card: [100, 240],
  three_dot_menu: [1300, 140],
  download_all_offset: [-30, 30],
  confirm_button: [960, 600],
  skip_detect: [960, 600],
  skip: [960, 600],
  skip_all: [960, 600],
};

function stateFile() {
  return path.join(
    process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'),
    'Playlist Administrator', 'data', 'spotube_download_state.json');
}

function loadState() {
  try {
    if (!fs.existsSync(stateFile())) return {};
    return JSON.parse(fs.readFileSync(stateFile(), 'utf-8'));
  } catch { return {}; }
}

function saveState(state) {
  try {
    fs.mkdirSync(path.dirname(stateFile()), { recursive: true });
    fs.writeFileSync(stateFile(), JSON.stringify(state), 'utf-8');
  } catch {}
}

class PsWorker {
  constructor() {
    const scriptFile = path.join(os.tmpdir(), `pa_spotube_worker_${process.pid}.ps1`);
    fs.writeFileSync(scriptFile, PS_SCRIPT, 'utf-8');
    this._scriptFile = scriptFile;
    this.proc = spawn(
      'powershell', ['-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', scriptFile],
      { windowsHide: true, shell: false },
    );
    this.pending = [];
    this.rl = readline.createInterface({ input: this.proc.stdout });
    this.rl.on('line', (line) => {
      const p = this.pending.shift();
      if (!p) return;
      try { p.resolve(JSON.parse(line)); } catch { p.resolve({ ok: false, error: 'bad json' }); }
    });
    this.proc.on('error', () => {});
    this.proc.stdin.write(`${JSON.stringify({ cmd: 'find' })}\n`); // warm up (also compiles C#)
  }

  call(cmd, args = []) {
    return new Promise((resolve) => {
      const t = setTimeout(() => resolve({ ok: false, error: 'timeout' }), 30000);
      this.pending.push({ resolve: (r) => { clearTimeout(t); resolve(r); } });
      try {
        this.proc.stdin.write(`${JSON.stringify({ cmd, args })}\n`);
      } catch {
        resolve({ ok: false, error: 'worker closed' });
      }
    });
  }

  async close() {
    try {
      this.proc.stdin.write(`${JSON.stringify({ cmd: 'exit' })}\n`);
      await sleep(300);
      this.proc.kill();
    } catch {}
    try { fs.unlinkSync(this._scriptFile); } catch {}
  }
}

export class SpotubeController {
  constructor({ libraryPath, coords = {} }) {
    this.libraryPath = libraryPath;
    this._coords = { ...defaultCoords, ...coords };
    this._prevHwnd = null;
    this._aborted = false;
    this.worker = null;
  }

  async _w() {
    if (!this.worker) this.worker = new PsWorker();
    return this.worker;
  }

  _coord(key) {
    return this._coords[key] || defaultCoords[key] || [0, 0];
  }

  async hwnd() {
    const w = await this._w();
    const r = await w.call('find');
    return r.ok && r.data && r.data[0] ? r.data[0] : null;
  }

  async isRunning() {
    return (await this.hwnd()) != null;
  }

  async _clientOrigin() {
    const h = await this.hwnd();
    if (!h) return [0, 0];
    const w = await this._w();
    const r = await w.call('rect', [h]);
    if (!r.ok || !r.data) return [0, 0];
    return [r.data[0], r.data[1]];
  }

  async _absolute(key) {
    const c = this._coord(key);
    const origin = await this._clientOrigin();
    return [origin[0] + c[0], origin[1] + c[1]];
  }

  async activate() {
    const h = await this.hwnd();
    if (!h) throw new Error('Spotube not found');
    const w = await this._w();
    const fg = await w.call('foreground');
    if (fg.ok && fg.data && fg.data[0]) this._prevHwnd = fg.data[0];
    await w.call('activate', [h]);
    await this._aWait(300);
  }

  async restorePrevious() {
    if (this._prevHwnd) {
      const w = await this._w();
      await w.call('activate', [this._prevHwnd]);
      this._prevHwnd = null;
    }
  }

  async minimize() {
    const h = await this.hwnd();
    if (h) { const w = await this._w(); await w.call('minimize', [h]); }
  }

  async maximize() {
    const h = await this.hwnd();
    if (h) { const w = await this._w(); await w.call('maximize', [h]); }
  }

  async click(x, y) {
    const w = await this._w();
    await w.call('click', [x, y]);
    await this._aWait(200);
  }

  async doubleClick(x, y) {
    await this.click(x, y);
    await sleep(100);
    await this.click(x, y);
    await this._aWait(300);
  }

  async sendChars(text) {
    const w = await this._w();
    for (const ch of [...text]) {
      if (this._aborted) return;
      await w.call('type', [ch.codePointAt(0)]);
      await sleep(30);
    }
  }

  async sendBackspaces(count) {
    const w = await this._w();
    for (let i = 0; i < count; i++) {
      if (this._aborted) return;
      await w.call('vk', [0x08, false]);
      await w.call('vk', [0x08, true]);
      await sleep(20);
    }
  }

  async sendEscape() {
    const w = await this._w();
    await w.call('vk', [0x1B, false]);
    await w.call('vk', [0x1B, true]);
    await this._aWait(100);
  }

  async pixelBrightness(x, y) {
    const w = await this._w();
    const r = await w.call('pixel', [x, y]);
    return r.ok && r.data ? r.data[0] : 0;
  }

  async _aWait(ms) {
    const w = await this._w();
    const r = await w.call('sleep', [ms]);
    if (r.ok && r.data && r.data[0]) this._aborted = true;
  }

  async hasSkipDialog() {
    const pos = await this._absolute('skip_detect');
    return (await this.pixelBrightness(pos[0], pos[1])) > 200;
  }

  async _checkAborted() {
    if (this._aborted) {
      await this.sendEscape();
      await this.minimize();
      await this.restorePrevious();
      return true;
    }
    return false;
  }

  async _stepPlaylist(name, { checkSkip = false } = {}) {
    await this._clickSidebarLibrary();
    await this._wait(800);
    if (await this._checkAborted()) return;
    await this._filterPlaylists(name);
    await this._wait(1500);
    if (await this._checkAborted()) return;
    await this._clickFirstPlaylist();
    await this._wait(2000);
    if (await this._checkAborted()) return;
    await this._clickThreeDot();
    await this._wait(800);
    if (await this._checkAborted()) return;
    await this._clickDownloadAll();
    await this._wait(800);
    if (await this._checkAborted()) return;
    await this._clickConfirm();
    if (checkSkip) {
      for (let i = 0; i < 5; i++) {
        await this._wait(2000);
        if (await this._checkAborted()) return;
        if (await this.hasSkipDialog()) {
          await this._clickSkip();
          await this._wait(200);
          await this._clickSkipAll();
          break;
        }
      }
    }
  }

  async _clickSidebarLibrary() {
    const pos = await this._absolute('sidebar_library');
    await this.click(pos[0], pos[1]);
  }

  async _filterPlaylists(name) {
    const pos = await this._absolute('library_filter');
    await this.click(pos[0], pos[1]);
    await this._aWait(200);
    await this.sendBackspaces(80);
    await this._aWait(50);
    await this.sendChars(name);
  }

  async _clickFirstPlaylist() {
    const pos = await this._absolute('first_playlist_card');
    await this.doubleClick(pos[0], pos[1]);
  }

  async _clickThreeDot() {
    const pos = await this._absolute('three_dot_menu');
    await this.click(pos[0], pos[1]);
  }

  async _clickDownloadAll() {
    const base = await this._absolute('three_dot_menu');
    const offset = this._coord('download_all_offset');
    await this.click(base[0] + offset[0], base[1] + offset[1]);
  }

  async _clickConfirm() {
    const pos = await this._absolute('confirm_button');
    await this.click(pos[0], pos[1]);
  }

  async _clickSkip() {
    const pos = await this._absolute('skip');
    await this.click(pos[0], pos[1]);
  }

  async _clickSkipAll() {
    const pos = await this._absolute('skip_all');
    await this.click(pos[0], pos[1]);
  }

  async downloadPlaylist(name) {
    if (await this._checkAborted()) return;
    if (!(await this.isRunning())) throw new Error('Spotube is not running');
    await this.maximize();
    await this.activate();
    await this._stepPlaylist(name, { checkSkip: true });
    await this.minimize();
    await this.restorePrevious();
  }

  async downloadAll(names) {
    this._aborted = false;
    if (!(await this.isRunning())) throw new Error('Spotube is not running');
    await this.maximize();
    await this.activate();
    for (let i = 0; i < names.length; i++) {
      if (this._aborted) break;
      await this._stepPlaylist(names[i], { checkSkip: i === 0 });
    }
    await this.minimize();
    await this.restorePrevious();
  }

  async moveDownloads(resolvedDownloadPath) {
    const src = resolvedDownloadPath;
    const dst = path.join(this.libraryPath, 'm4a');
    if (!fs.existsSync(src)) return 0;
    fs.mkdirSync(dst, { recursive: true });
    let moved = 0;
    const walk = (dir) => {
      for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
        if (this._aborted) return;
        const full = path.join(dir, e.name);
        if (e.isDirectory()) walk(full);
        else if (e.isFile() && /\.(m4a|mp3|flac|wav|webm)$/i.test(e.name)) {
          const target = path.join(dst, e.name);
          if (!fs.existsSync(target)) {
            fs.renameSync(full, target);
            moved++;
          }
        }
      }
    };
    walk(src);
    return moved;
  }
}
