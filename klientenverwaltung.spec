# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller build config for the full application (build/ and dist/ output
# are gitignored, this file is not - keep it at the repo root, not build/).
#
# Runtime-loaded, non-Python resource folders under src/klientenverwaltung/ui/
# (icons/, assets/) must be listed in `datas` below with a destination path
# that mirrors their normal package location - code loads them via
# `Path(__file__).parent / "icons"` etc., which only resolves correctly
# inside the frozen app if the bundled layout matches the source layout.
# Add any future such folder here too.

a = Analysis(
    ['src/klientenverwaltung/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/klientenverwaltung/ui/icons', 'klientenverwaltung/ui/icons'),
        ('src/klientenverwaltung/ui/assets', 'klientenverwaltung/ui/assets'),
    ],
    hiddenimports=[],
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
)
