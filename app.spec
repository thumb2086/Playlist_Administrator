# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all

# 取得 zhconv 的所有資料
tmp_ret = collect_all('zhconv')
datas = tmp_ret[0]; binaries = tmp_ret[1]; hiddenimports = tmp_ret[2]

a = Analysis(
    ['gui/app.py'],
    pathex=[],
    binaries=binaries,  # 這裡帶入 zhconv 的 binaries
    datas=datas,        # 這裡帶入 zhconv 的 datas (包含 zhcdict.json)
    hiddenimports=hiddenimports, # 這裡帶入 zhconv 的 hiddenimports
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Playlist Administrator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
