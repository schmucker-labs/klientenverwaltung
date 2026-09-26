from pathlib import Path

import pytest
from PySide6.QtCore import QSettings as _RealQSettings
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QApplication, QHeaderView, QTableView

from klientenverwaltung.ui import window_settings


@pytest.fixture
def isolated_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Points window_settings.QSettings() at a private ini file for the
    duration of the test, so these tests never touch the real user
    settings and never see state left over from another test."""
    ini_path = tmp_path / "settings.ini"
    monkeypatch.setattr(
        window_settings,
        "QSettings",
        lambda: _RealQSettings(str(ini_path), _RealQSettings.Format.IniFormat),
    )
    return ini_path


def _header_for(qapp: QApplication, column_count: int) -> QHeaderView:
    # Kept alive via the header's own parent-child ownership (the view),
    # returned as the view too so the caller holds a reference to both.
    model = QStandardItemModel(1, column_count)
    view = QTableView()
    view.setModel(model)
    view.setProperty("_owning_model", model)  # keep model alive with the view
    return view


def test_restore_header_state_roundtrips_matching_columns(
    qapp: QApplication, isolated_settings: Path
) -> None:
    titles = ["A", "B", "C"]
    view = _header_for(qapp, len(titles))
    header = view.horizontalHeader()
    header.resizeSection(0, 123)
    window_settings.save_header_state(header, "test/key", titles)

    view2 = _header_for(qapp, len(titles))
    header2 = view2.horizontalHeader()
    restored = window_settings.restore_header_state(header2, "test/key", titles)

    assert restored is True
    assert header2.sectionSize(0) == 123


@pytest.mark.parametrize(
    "saved_titles",
    [
        ["Datum", "Behandlungsart", "Dauer (Min.)", "Notiz"],  # one more than now
        ["Datum", "Behandlungsart"],  # one fewer than now
    ],
    ids=["more-columns-saved", "fewer-columns-saved"],
)
def test_restore_header_state_discards_mismatched_column_shape(
    qapp: QApplication, isolated_settings: Path, saved_titles: list[str]
) -> None:
    """Regression for the IndexError in headerData() after a column was
    removed: a saved layout for a different column shape must be
    discarded, not applied, so the caller falls back to default widths
    instead of a view whose header thinks it has a column the model no
    longer provides."""
    view = _header_for(qapp, len(saved_titles))
    window_settings.save_header_state(view.horizontalHeader(), "test/key", saved_titles)

    current_titles = ["Datum", "Behandlungsart", "Dauer (Min.)"]
    view2 = _header_for(qapp, len(current_titles))
    restored = window_settings.restore_header_state(
        view2.horizontalHeader(), "test/key", current_titles
    )

    assert restored is False

    # Discarded outright, not merely ignored - a later run with the exact
    # same (mismatched) saved state must not keep re-discovering the
    # mismatch from stale data.
    settings = _RealQSettings(str(isolated_settings), _RealQSettings.Format.IniFormat)
    assert settings.value("test/key") is None
    assert settings.value("test/key/columns") is None


def test_restore_header_state_first_run_returns_false(
    qapp: QApplication, isolated_settings: Path
) -> None:
    view = _header_for(qapp, 3)
    restored = window_settings.restore_header_state(
        view.horizontalHeader(), "test/never-saved", ["A", "B", "C"]
    )

    assert restored is False
