# -*- mode: python ; coding: utf-8 -*-
#
# Diagnostic build: identical to klientenverwaltung.spec except console=True,
# so unhandled-exception output (and Qt's own stderr diagnostics, e.g. a
# missing platform/SVG plugin) show up in a console window - the release
# build's console=False otherwise swallows all of that with nothing visible.
#
# For troubleshooting only, never for distribution to the actual user.
# Build with `uv run python scripts/build_exe.py --debug` (or directly:
# `uv run pyinstaller klientenverwaltung-debug.spec --noconfirm`). Produces
# dist/klientenverwaltung-debug.exe, separate from the release build.

import sys
from pathlib import Path

sys.path.insert(0, str(Path(SPECPATH) / "scripts"))
from pyinstaller_common import (
    HIDDEN_IMPORTS,
    ICON_PATH,
    MAIN_SCRIPT,
    SRC_PATH,
    build_version_info,
    get_datas,
)

a = Analysis(
    [MAIN_SCRIPT],
    pathex=[SRC_PATH],
    binaries=[],
    datas=get_datas(),
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='klientenverwaltung-debug',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # No UPX: compressed executables trigger antivirus false positives far
    # more often, and the size saving is not worth that for this user.
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH,
    version=build_version_info(),
)
