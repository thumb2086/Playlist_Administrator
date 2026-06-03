import os
import sys
import time
import json
import subprocess
import logging

logger = logging.getLogger(__name__)

try:
    import pyautogui
    pyautogui.FAILSAFE = True
except ImportError:
    pyautogui = None

try:
    import win32gui
    import win32con
    import win32api
    import win32process
except ImportError:
    win32gui = None
    win32con = None
    win32api = None
    win32process = None


class SpotubeControllerError(Exception):
    pass


_STATE_FILE = "spotube_download_state.json"


class SpotubeController:
    """Controls Spotube GUI via coordinate-based clicking.

    Coordinates are **relative to the Spotube window's client area**.
    Use ``tools/spotube_calibrate.py`` to obtain them.

    State tracking
    --------------
    A JSON file at ``{library_path}/spotube_download_state.json`` records
    which playlists have been initiated for download so that re-runs skip
    them automatically.  Reset with ``--force`` or by deleting the file.
    """

    WINDOW_TITLES = ["Spotube"]

    _DEFAULT_COORDS = {
        "sidebar_library": (30, 280),
        "library_filter": (200, 100),
        "first_playlist_card": (100, 240),
        "three_dot_menu": (1300, 140),
        "download_all_offset": (-30, 30),
        "confirm_button": (960, 600),
        "skip_detect": (960, 600),
        "skip": (960, 600),
        "skip_all": (960, 600),
    }

    def __init__(self, config):
        if pyautogui is None:
            raise SpotubeControllerError("pyautogui is required")
        if win32gui is None:
            raise SpotubeControllerError("pywin32 is required")

        self.config = config
        self.coords = config.get("spotube_coords", {})
        self._hwnd = None
        self._prev_hwnd = None

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _resolve_coord(self, key):
        dx, dy = self.coords.get(key, self._DEFAULT_COORDS[key])
        ox, oy = self._client_origin()
        return (ox + dx, oy + dy)

    def _client_origin(self):
        hwnd = self.hwnd
        if not hwnd:
            raise SpotubeControllerError("Spotube window not found")
        rect = win32gui.GetWindowRect(hwnd)
        return (rect[0], rect[1])

    # ------------------------------------------------------------------
    # Window management
    # ------------------------------------------------------------------

    @property
    def hwnd(self):
        if self._hwnd and win32gui.IsWindow(self._hwnd):
            return self._hwnd
        self._hwnd = self._find_window()
        return self._hwnd

    def _find_window(self):
        def cb(h, results):
            if win32gui.IsWindowVisible(h):
                title = win32gui.GetWindowText(h)
                for t in self.WINDOW_TITLES:
                    if t.lower() in title.lower():
                        results.append(h)
                        break
        results = []
        win32gui.EnumWindows(cb, results)
        return results[0] if results else None

    def is_running(self):
        return self._find_window() is not None

    def launch(self, spotube_path=None):
        if self.is_running():
            return
        path = spotube_path or self.config.get("spotube_exe_path")
        if not path:
            candidates = [
                os.path.expandvars(r"%LOCALAPPDATA%\Spotube\Spotube.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\Spotube\Spotube.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Spotube\Spotube.exe"),
            ]
            for c in candidates:
                if os.path.exists(c):
                    path = c
                    break
        if not path or not os.path.exists(path):
            raise SpotubeControllerError("Spotube executable not found. Set spotube_exe_path in config.")
        subprocess.Popen([path], shell=True)
        for _ in range(30):
            time.sleep(0.5)
            if self._find_window():
                return
        raise SpotubeControllerError("Spotube did not start within 15 s.")

    def _activate(self):
        self._prev_hwnd = win32gui.GetForegroundWindow()
        hwnd = self.hwnd
        if not hwnd:
            raise SpotubeControllerError("Spotube window not found")
        if win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            for _ in range(20):
                time.sleep(0.15)
                r = win32gui.GetWindowRect(hwnd)
                if r[0] > -30000 and r[1] > -30000:
                    break
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.3)

    def _restore_previous(self):
        prev = self._prev_hwnd
        if prev and win32gui.IsWindow(prev):
            try:
                win32gui.SetForegroundWindow(prev)
            except Exception:
                pass
        self._prev_hwnd = None

    # ------------------------------------------------------------------
    # Low-level input
    # ------------------------------------------------------------------

    def _click(self, x, y, delay=0.25):
        pyautogui.click(x, y)
        time.sleep(delay)

    def _double_click(self, x, y, delay=0.3):
        pyautogui.doubleClick(x, y)
        time.sleep(delay)

    def _type(self, text):
        pyautogui.write(text, interval=0.05)
        time.sleep(0.3)

    def _hotkey(self, *keys):
        pyautogui.hotkey(*keys)
        time.sleep(0.4)

    # ------------------------------------------------------------------
    # Navigation actions (caller manages activate/restore)
    # ------------------------------------------------------------------

    def click_sidebar_library(self):
        x, y = self._resolve_coord("sidebar_library")
        logger.debug("Click sidebar Library at (%d, %d)", x, y)
        self._click(x, y, delay=0.5)

    def _get_focused_hwnd(self):
        """Get the focused child HWND of Spotube's window."""
        try:
            tid = win32process.GetWindowThreadProcessId(self.hwnd)[0]
            cur = win32api.GetCurrentThreadId()
            win32process.AttachThreadInput(cur, tid, True)
            time.sleep(0.05)
            f = win32gui.GetFocus()
            win32process.AttachThreadInput(cur, tid, False)
            return f
        except Exception:
            return None

    def _send_wm_char(self, text):
        """Send text via WM_CHAR messages to the focused control."""
        hwnd = self._get_focused_hwnd() or self.hwnd
        for ch in text:
            win32api.SendMessage(hwnd, win32con.WM_CHAR, ord(ch), 0)
            time.sleep(0.02)

    def filter_playlists(self, name):
        """Click filter → END → backspace×80 → type name."""
        x, y = self._resolve_coord("library_filter")
        logger.debug("Click filter at (%d, %d)", x, y)
        self._click(x, y, delay=0.5)
        time.sleep(0.3)

        fw = self._get_focused_hwnd() or self.hwnd

        # END → cursor to end of text
        win32api.SendMessage(fw, win32con.WM_KEYDOWN, win32con.VK_END, 0)
        win32api.SendMessage(fw, win32con.WM_KEYUP, win32con.VK_END, 0)
        time.sleep(0.1)

        # Backspace to delete from the end (full WM_KEYDOWN+CHAR+KEYUP per press)
        for _ in range(80):
            win32api.SendMessage(fw, win32con.WM_KEYDOWN, win32con.VK_BACK, 0)
            win32api.SendMessage(fw, win32con.WM_CHAR, 0x08, 0)
            win32api.SendMessage(fw, win32con.WM_KEYUP, win32con.VK_BACK, 0)
            time.sleep(0.02)
        time.sleep(0.2)

        # Type the playlist name
        self._send_wm_char(name)
        time.sleep(0.5)

    def click_first_playlist(self):
        x, y = self._resolve_coord("first_playlist_card")
        logger.debug("Double-click first playlist at (%d, %d)", x, y)
        self._double_click(x, y, delay=1.0)

    def click_three_dot_menu(self):
        x, y = self._resolve_coord("three_dot_menu")
        logger.debug("Click three-dot menu at (%d, %d)", x, y)
        self._click(x, y, delay=0.5)

    def click_download_all(self):
        tx, ty = self._resolve_coord("three_dot_menu")
        dx, dy = self.coords.get("download_all_offset", self._DEFAULT_COORDS["download_all_offset"])
        target = (tx + dx, ty + dy)
        logger.debug("Click Download All at (%d, %d)", *target)
        self._click(*target, delay=0.5)

    def click_confirm(self):
        x, y = self._resolve_coord("confirm_button")
        logger.debug("Click confirm at (%d, %d)", x, y)
        self._click(x, y, delay=0.3)

    def click_skip_all(self):
        """Click 'Skip All' when the 'already exists' dialog appears."""
        x, y = self._resolve_coord("skip_all")
        logger.debug("Click Skip All at (%d, %d)", x, y)
        self._click(x, y, delay=0.3)

    # ------------------------------------------------------------------
    # Window state
    # ------------------------------------------------------------------

    def maximize(self):
        hwnd = self.hwnd
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            time.sleep(0.3)

    def minimize(self):
        hwnd = self.hwnd
        if hwnd:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

    def close(self):
        hwnd = self.hwnd
        if hwnd:
            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)

    # ------------------------------------------------------------------
    # Download state tracking
    # ------------------------------------------------------------------

    def _state_path(self):
        lp = self.config.get("library_path", "")
        return os.path.join(lp, _STATE_FILE) if lp else _STATE_FILE

    def _load_state(self):
        path = self._state_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_state(self, state):
        path = self._state_path()
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def is_downloaded(self, playlist_name):
        """Return True if *playlist_name* has already been initiated."""
        return playlist_name in self._load_state()

    def mark_downloaded(self, playlist_name):
        state = self._load_state()
        state[playlist_name] = time.strftime("%Y-%m-%d %H:%M:%S")
        self._save_state(state)
        logger.info("Marked '%s' as downloaded", playlist_name)

    def list_downloaded(self):
        return list(self._load_state().keys())

    def reset_state(self, playlist_name=None):
        if playlist_name:
            state = self._load_state()
            state.pop(playlist_name, None)
            self._save_state(state)
        else:
            path = self._state_path()
            if os.path.exists(path):
                os.remove(path)
                logger.info("Download state file deleted")

    # ------------------------------------------------------------------
    # Single-playlist workflow
    # ------------------------------------------------------------------

    def _download_one(self, playlist_name, check_skip=True):
        """Core click sequence for one playlist (no window mgmt)."""
        # Use search_name from config if provided (Spotify names may differ)
        search_name = self.config.get("search_names", {}).get(playlist_name, playlist_name)

        self.click_sidebar_library()
        time.sleep(0.8)

        self.filter_playlists(search_name)
        time.sleep(1.2)

        self.click_first_playlist()
        time.sleep(1.5)

        self.click_three_dot_menu()
        time.sleep(0.8)

        self.click_download_all()

        # Confirm dialog (may appear right away)
        time.sleep(0.8)
        self.click_confirm()

        # "Already exists" dialog: poll until it appears (only first playlist).
        # Download speed varies, so the dialog may show after 2s or 30s.
        if check_skip:
            dx, dy = self._resolve_coord("skip_detect")
            for _ in range(5):
                time.sleep(2)
                try:
                    pr, pg, pb = pyautogui.pixel(dx, dy)
                    if (pr + pg + pb) / 3 > 200:
                        x, y = self._resolve_coord("skip")
                        self._click(x, y, delay=0.3)
                        self.click_skip_all()
                        logger.debug("Skip dialog detected, dismissed")
                        break
                except Exception:
                    break

        self.mark_downloaded(playlist_name)

    def download_playlist(self, playlist_name, force=False):
        """Download one playlist (single-use, handles window mgmt)."""
        if not force and self.is_downloaded(playlist_name):
            print(f"  [skip] {playlist_name} 已下載過")
            return

        self.launch()
        self.maximize()
        self._activate()
        try:
            self._download_one(playlist_name, check_skip=True)
        finally:
            self.minimize()
            self._restore_previous()

    def download_all_playlists(self, url_names, force=False):
        """Download all playlists sequentially — optimised for batch.

        Spotube stays in front the whole time; no minimise/restore between
        playlists.  Each playlist navigates back via the sidebar Library
        click at the start of ``_download_one``.
        """
        self.launch()
        self.maximize()
        self._activate()

        total = len(url_names)
        try:
            for i, (url, name) in enumerate(url_names.items(), 1):
                if not force and self.is_downloaded(name):
                    safe = name.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
                    print(f"  [{i}/{total}] [skip] {safe}")
                    continue

                safe = name.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding)
                print(f"  [{i}/{total}] {safe}")
                try:
                    self._download_one(name, check_skip=(i == 1))
                    time.sleep(1.5)
                except Exception as exc:
                    logger.error("Failed %s: %s", name, exc)
                    print(f"  [ERROR] {name}: {exc}")
                    # Try to get back to library for the next one
                    try:
                        self.click_sidebar_library()
                        time.sleep(1)
                    except Exception:
                        pass
        finally:
            self.minimize()
            self._restore_previous()
