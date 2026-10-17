# -*- mode: python ; coding: utf-8 -*-
"""crypto-alert Windows exe 빌드 설정 (PyInstaller --onefile).

빌드: .\.venv\Scripts\python.exe -m PyInstaller crypto-alert.spec
결과: dist/crypto-alert.exe (첫 실행 시 exe 옆에 watchlist.json 등 생성)
"""

a = Analysis(
    ["src/crypto_alert/main.py"],
    pathex=["src"],
    binaries=[],
    datas=[("src/crypto_alert/supplies.json", ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="crypto-alert",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI 앱이므로 콘솔 창 숨김
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
