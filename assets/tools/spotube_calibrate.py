"""Spotube 座標校準工具 — 自動儲存到 config.json

使用方法:
    python tools/spotube_calibrate.py

每個步驟會即時顯示：
  - 視窗左上角位置 (ox, oy)
  - 滑鼠螢幕座標 (mx, my)
  - 計算後的視窗相對座標 (dx, dy)
"""

import os
import sys
import time
import json
import msvcrt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import win32gui
    import win32api
    import win32con
except ImportError:
    win32gui = None
    win32api = None
    win32con = None


def get_spotube_hwnd():
    def cb(h, results):
        if win32gui.IsWindowVisible(h):
            title = win32gui.GetWindowText(h)
            if "spotube" in title.lower():
                results.append(h)
    results = []
    win32gui.EnumWindows(cb, results)
    return results[0] if results else None


def load_config(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_config(path, config):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)


def wait_for_enter(prompt):
    print(prompt, end=" ", flush=True)
    while True:
        if msvcrt.kbhit():
            key = msvcrt.getch()
            if key in (b"\r", b"\n"):
                print()
                return
        time.sleep(0.05)


def record_point():
    time.sleep(0.2)
    hwnd = get_spotube_hwnd()
    if not hwnd:
        raise RuntimeError("找不到 Spotube 視窗")
    rect = win32gui.GetWindowRect(hwnd)
    ox, oy = rect[0], rect[1]
    mx, my = win32api.GetCursorPos()
    dx, dy = mx - ox, my - oy
    print(f"   視窗原點: ({ox}, {oy})  滑鼠: ({mx}, {my})  相對: ({dx}, {dy})")
    if dx < 0 or dx > 10000:
        print(f"   ⚠️  相對座標 ({dx}, {dy}) 異常 — 視窗可能被最小化")
    return [dx, dy]


def main():
    if win32api is None or win32gui is None:
        print("錯誤: 需要 pywin32（pip install pywin32）")
        return 1

    hwnd = get_spotube_hwnd()
    if not hwnd:
        print("錯誤: 找不到 Spotube 視窗，請先啟動 Spotube")
        return 1

    if win32gui.IsIconic(hwnd):
        print("Spotube 正在最小化狀態，自動還原…")
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(1)

    rect = win32gui.GetWindowRect(hwnd)
    ox, oy = rect[0], rect[1]
    w, h = rect[2] - ox, rect[3] - oy
    cls_name = win32gui.GetClassName(hwnd)

    print(f"找到 Spotube 視窗")
    print(f"  類別: {cls_name}")
    print(f"  視窗位置: ({ox}, {oy})  大小: {w} × {h}")
    print(f"  座標 API: win32gui.GetWindowRect + win32api.GetCursorPos")
    print()

    targets = [
        ("sidebar_library",      "側邊欄 Library 圖示"),
        ("library_filter",       "Library 頁面的搜尋/過濾輸入框"),
        ("first_playlist_card",  "Library 中第一個歌單卡片（過濾後）"),
        ("three_dot_menu",       "歌單頁面右上角的三點選單"),
    ]

    results = {}
    print("=" * 60)
    print("將滑鼠移到目標元素上，按 Enter 記錄")
    print("按 Ctrl+C 可中斷")
    print("=" * 60)

    for key, desc in targets:
        print(f"\n--- {desc} ---")
        wait_for_enter(f"  移到 [{key}] 上，按 Enter")
        results[key] = record_point()

    # Download All offset (from three_dot_menu)
    print(f"\n--- 下載全部 (在三點選單彈出選單中) ---")
    print("  提示: 先手動點擊三點選單，彈出選單後再將滑鼠移到「下載全部」")
    wait_for_enter(f"  移到「下載全部」上，按 Enter")
    pt = record_point()
    tx, ty = results["three_dot_menu"]
    offset_dx = pt[0] - tx
    offset_dy = pt[1] - ty
    results["download_all_offset"] = [offset_dx, offset_dy]
    print(f"  偏移 (相對三點選單): ({offset_dx}, {offset_dy})")

    # Confirm button
    print(f"\n--- 確認對話框的「同意」按鈕 ---")
    print("  提示: 先手動點擊「下載全部」，出現確認對話框後再將滑鼠移到「同意」")
    wait_for_enter(f"  移到「同意」上，按 Enter")
    results["confirm_button"] = record_point()

    # White/bright spot to detect if skip dialog is showing
    print(f"\n--- 偵測點 (白色按鈕/文字，用來判斷對話框是否存在) ---")
    print("  請在「歌曲已存在」對話框上，找一個**白色且明顯**的元素")
    print("  （可以是按鈕文字、標題等），將滑鼠移上去")
    wait_for_enter(f"  移到白色偵測點上，按 Enter")
    results["skip_detect"] = record_point()

    # Skip / Skip All buttons (appears when songs already exist)
    print(f"\n--- 歌曲已存在對話框：略過 (Skip) ---")
    print("  移到「略過 / Skip」按鈕上，按 Enter")
    wait_for_enter(f"  移到「略過 / Skip」上，按 Enter")
    results["skip"] = record_point()

    print(f"\n--- 歌曲已存在對話框：全部略過 (Skip All) ---")
    wait_for_enter(f"  移到「全部略過 / Skip All」上，按 Enter")
    results["skip_all"] = record_point()

    print()
    print("=" * 60)

    # --- auto-save to config.json ---
    appdata_dir = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expandvars(r"%USERPROFILE%\AppData\Local")),
        "playlist-admin", "data",
    )
    appdata_cfg = os.path.join(appdata_dir, "config.json")

    real_config_path = appdata_cfg
    if os.path.exists(appdata_cfg):
        pointer = load_config(appdata_cfg)
        base = pointer.get("base_path", "")
        if base:
            candidate = os.path.join(base, "config.json")
            if os.path.exists(candidate):
                real_config_path = candidate

    config = load_config(real_config_path)
    config["spotube_coords"] = results
    save_config(real_config_path, config)

    print(f"已自動寫入: {real_config_path}")
    print(f"spotube_coords = {json.dumps(results, indent=4, ensure_ascii=False)}")
    print()
    print("校準完成！現在可以直接使用 spotube-download 指令。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n已中斷。")
        sys.exit(1)
