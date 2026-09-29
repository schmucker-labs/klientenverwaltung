"""Builds the full application into a standalone Windows .exe.

    uv run python scripts/build_exe.py            # release build (windowed)
    uv run python scripts/build_exe.py --debug     # diagnostic build (console)

Just a thin, repeatable wrapper around PyInstaller with the project's own
spec files (klientenverwaltung.spec / klientenverwaltung-debug.spec) - all
the actual build configuration (bundled data files, hidden imports, icon,
version resource) lives there (shared via scripts/pyinstaller_common.py),
not here. Both specs build a single file (no COLLECT step), so the result
is one self-contained .exe.

The --debug build shows a console window with unhandled-exception output
and Qt's own stderr diagnostics - use it to troubleshoot a release build
that fails silently on a machine without Python installed. Never ship it
to the actual user.
"""

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    debug = "--debug" in sys.argv
    spec_file = _REPO_ROOT / (
        "klientenverwaltung-debug.spec" if debug else "klientenverwaltung.spec"
    )
    exe_name = "klientenverwaltung-debug.exe" if debug else "klientenverwaltung.exe"

    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(spec_file), "--noconfirm"],
        cwd=_REPO_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    print(f"Gebaut: {_REPO_ROOT / 'dist' / exe_name}")


if __name__ == "__main__":
    main()
