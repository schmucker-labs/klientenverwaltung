import tomllib
from pathlib import Path

import klientenverwaltung

_PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_package_version_matches_pyproject() -> None:
    """The version lives in two places (pyproject.toml for the package,
    __init__.py for the about dialog and the .exe's file properties) -
    they must not drift apart."""
    project = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]

    assert project["version"] == klientenverwaltung.__version__
    assert "Add your description" not in project["description"]
