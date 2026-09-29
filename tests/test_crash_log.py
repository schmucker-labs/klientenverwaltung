from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from sqlalchemy.exc import IntegrityError

from klientenverwaltung import config, main


@pytest.fixture(autouse=True)
def _isolated_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


# Only ever passed around as a value, like real client data: a literal
# inside one of the raising functions would show up in the traceback's
# source lines, which are (deliberately) still logged as program code.
_SECRET = "Geheimname"


def _raise_integrity_error_with_client_data(secret: str) -> None:
    try:
        raise ValueError(f"Bericht über Anna {secret}")
    except ValueError as cause:
        raise IntegrityError(
            "INSERT INTO client (first_name, last_name) VALUES (?, ?)",
            ("Anna", secret),
            cause,
        ) from cause


def test_crash_log_contains_neither_parameters_nor_exception_messages(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(main, "show_error", lambda *args, **kwargs: None)
    try:
        _raise_integrity_error_with_client_data(_SECRET)
    except IntegrityError as exc:
        main._log_and_show_crash(type(exc), exc, exc.__traceback__)

    log_text = config.error_log_path().read_text(encoding="utf-8")
    assert _SECRET not in log_text
    # Still useful for diagnosis: exception types and code locations.
    assert "IntegrityError" in log_text
    assert "ValueError" in log_text
    assert "_raise_integrity_error_with_client_data" in log_text
