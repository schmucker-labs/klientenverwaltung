# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller build config for the full application (build/ and dist/ output
# are gitignored, this file is not - keep it at the repo root, not build/).
# Build with `uv run python scripts/build_exe.py` (or directly:
# `uv run pyinstaller klientenverwaltung.spec --noconfirm`).
#
# Shared with klientenverwaltung-debug.spec (a console=True diagnostic
# build - see that file) via scripts/pyinstaller_common.py; only the
# EXE(name=..., console=...) below should ever differ between the two.

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
    name='klientenverwaltung',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Regenerate from ui/icons/logo.svg via scripts/generate_icons.py.
    icon=ICON_PATH,
    version=build_version_info(),
)
