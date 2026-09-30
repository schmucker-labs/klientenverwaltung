import os

import pytest
from PySide6.QtWidgets import QApplication

from klientenverwaltung import self_test, storage


def test_self_test_passes_and_leaves_the_environment_as_it_was(
    qapp: QApplication, capsys: pytest.CaptureFixture[str]
) -> None:
    appdata_before = os.environ.get("APPDATA")

    assert self_test.run() == 0

    assert os.environ.get("APPDATA") == appdata_before
    output = capsys.readouterr().out
    assert "FEHLER" not in output
    assert "Selbsttest bestanden" in output


def test_self_test_reports_a_failing_step_with_exit_code_1(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def _broken_setup(*_args: object, **_kwargs: object) -> None:
        raise ModuleNotFoundError("No module named 'logging.config'")

    monkeypatch.setattr(storage, "set_up_data_drive", _broken_setup)

    assert self_test.run() == 1

    output = capsys.readouterr().out
    assert "FEHLER" in output
    assert "ModuleNotFoundError" in output
