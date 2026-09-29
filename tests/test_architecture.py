"""The layering rules from CLAUDE.md, checked on the source: ui/ talks to
services/ only (never to the ORM models), and services/ knows no Qt - so
services could run unchanged behind a web API one day."""

import ast
from pathlib import Path

import pytest

_PACKAGE = Path(__file__).resolve().parents[1] / "src" / "klientenverwaltung"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize(
    "path", sorted((_PACKAGE / "ui").glob("*.py")), ids=lambda path: path.name
)
def test_ui_never_imports_the_orm_models(path: Path) -> None:
    offending = {
        module
        for module in _imported_modules(path)
        if module in ("klientenverwaltung.models", "sqlalchemy.orm")
        or module.startswith(
            ("klientenverwaltung.models.", "klientenverwaltung.repositories")
        )
    }
    assert not offending


@pytest.mark.parametrize(
    "path",
    sorted([*(_PACKAGE / "services").glob("*.py"), *(_PACKAGE / "repositories").glob("*.py")]),
    ids=lambda path: f"{path.parent.name}/{path.name}",
)
def test_services_and_repositories_know_no_qt(path: Path) -> None:
    assert not {m for m in _imported_modules(path) if m.startswith("PySide6")}
