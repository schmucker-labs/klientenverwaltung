"""Shared PyInstaller build config for klientenverwaltung.spec and
klientenverwaltung-debug.spec, so the two stay in sync automatically -
only their EXE(name=..., console=...) should ever differ.
"""

import sys
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_SCRIPT = str(REPO_ROOT / "src" / "klientenverwaltung" / "main.py")
SRC_PATH = str(REPO_ROOT / "src")
ICON_PATH = str(REPO_ROOT / "src" / "klientenverwaltung" / "ui" / "icons" / "app.ico")

# klientenverwaltung/__init__.py is the single source for the app's name,
# version and author - imported directly (not re-typed here, not
# re-parsed from pyproject.toml) so the .exe's file properties can never
# drift from what the about dialog and splash screen show. Safe to import
# at build time: __init__.py has no side effects and pulls in neither
# PySide6 nor sqlalchemy.
sys.path.insert(0, SRC_PATH)
from klientenverwaltung import AUTHOR, __version__

# sqlcipher3 (the compiled SQLCipher driver) is only imported from inside
# sqlalchemy.dialects.sqlite.pysqlcipher's import_dbapi(), a try/except
# inside a method body rather than a straightforward top-level import -
# named explicitly here so PyInstaller's static analysis is never relied
# on to find it.
#
# logging.config is imported by alembic/env.py, which - unlike ordinary
# source files - is bundled as a plain DATA file (see build_alembic_datas()
# below) because Alembic loads it straight off disk by file path, never
# through Python's import system. PyInstaller's static analysis therefore
# never sees that file's imports at all, so anything it imports that isn't
# already pulled in some other way (this was the actual cause of a real
# "ModuleNotFoundError: No module named 'logging.config'" crash, only on a
# machine without Python installed - a plain `import logging` elsewhere
# does not bundle the logging.config submodule) must be added here by
# hand. If env.py or a versions/*.py migration script ever needs a new
# import nothing else in the app already uses, it goes here too.
#
HIDDEN_IMPORTS = [
    "sqlcipher3",
    "logging.config",
]


def build_version_info() -> VSVersionInfo:
    version_tuple = (tuple(int(part) for part in __version__.split(".")) + (0, 0, 0, 0))[
        :4
    ]
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040704B0",
                        [
                            StringStruct("CompanyName", AUTHOR),
                            StringStruct("FileDescription", "Klientenverwaltung"),
                            StringStruct("FileVersion", __version__),
                            StringStruct("InternalName", "klientenverwaltung"),
                            StringStruct("LegalCopyright", f"© 2026 {AUTHOR}"),
                            StringStruct("OriginalFilename", "klientenverwaltung.exe"),
                            StringStruct("ProductName", "Klientenverwaltung"),
                            StringStruct("ProductVersion", __version__),
                        ],
                    )
                ]
            ),
            # German (0x0407) / Unicode codepage (1200) - must match the
            # StringTable identifier above ("0407" + hex(1200) == "040704B0").
            VarFileInfo([VarStruct("Translation", [0x0407, 1200])]),
        ],
    )


def build_alembic_datas() -> list[tuple[str, str]]:
    """alembic.ini plus every real file under alembic/ (env.py,
    script.py.mako, versions/*.py), skipping __pycache__.

    storage._bundle_root() looks for these at the bundle root (repo root
    in dev, sys._MEIPASS when frozen). Alembic loads env.py and each
    revision script straight off disk by file path, not as importable
    modules, so these must exist as real files, not just be importable
    code inside the PYZ archive.
    """
    alembic_dir = REPO_ROOT / "alembic"
    datas = [(str(REPO_ROOT / "alembic.ini"), ".")]
    for path in alembic_dir.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            dest = Path("alembic") / path.relative_to(alembic_dir).parent
            datas.append((str(path), str(dest)))
    return datas


def get_datas() -> list[tuple[str, str]]:
    # Runtime-loaded, non-Python resource folders under
    # src/klientenverwaltung/ui/ (icons/, assets/) need a destination path
    # that mirrors their normal package location - code loads them via
    # `Path(__file__).parent / "icons"` etc., which only resolves
    # correctly inside the frozen app if the bundled layout matches the
    # source layout. Add any future such folder here too.
    return [
        (
            str(REPO_ROOT / "src" / "klientenverwaltung" / "ui" / "icons"),
            "klientenverwaltung/ui/icons",
        ),
        (
            str(REPO_ROOT / "src" / "klientenverwaltung" / "ui" / "assets"),
            "klientenverwaltung/ui/assets",
        ),
        *build_alembic_datas(),
    ]
