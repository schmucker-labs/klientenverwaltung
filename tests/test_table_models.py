from collections.abc import Iterator
from datetime import datetime

import pytest
from PySide6.QtCore import QPersistentModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from klientenverwaltung.services import (
    ClientListEntry,
    SessionEntry,
    TreatmentTypeEntry,
)
from klientenverwaltung.ui.backup_table_model import BackupTableModel
from klientenverwaltung.ui.client_table_model import ClientTableModel
from klientenverwaltung.ui.media_table_model import MediaTableModel
from klientenverwaltung.ui.session_table_model import DATE_COLUMN, SessionTableModel
from klientenverwaltung.ui.theme import DARK_PALETTE, ThemeMode, apply_theme_mode
from klientenverwaltung.ui.treatment_type_table_model import TreatmentTypeTableModel


@pytest.mark.parametrize(
    "model_cls",
    [
        SessionTableModel,
        ClientTableModel,
        BackupTableModel,
        TreatmentTypeTableModel,
        MediaTableModel,
    ],
)
@pytest.mark.parametrize("out_of_range_section", [-1, 999])
def test_header_data_out_of_range_section_returns_none(
    model_cls: type, out_of_range_section: int
) -> None:
    """Regression: after a column is removed from a model, Qt can still
    briefly ask headerData() for a section index that no longer exists
    (e.g. while restoring a stale header layout) - see
    window_settings.restore_header_state() for why that should no longer
    happen at all, and this as the second, independent layer against it.
    """
    model = model_cls()

    assert model.headerData(out_of_range_section, Qt.Orientation.Horizontal) is None


@pytest.fixture
def dark_theme(qapp: QApplication) -> Iterator[None]:
    apply_theme_mode(ThemeMode.DARK)
    yield
    apply_theme_mode(ThemeMode.LIGHT)


def test_archived_clients_use_the_active_themes_color(dark_theme: None) -> None:
    """Regression: archived rows were always drawn in the light theme's
    gray - about 2.9:1 contrast on the dark theme's panels."""
    model = ClientTableModel()
    model.set_entries(
        [
            ClientListEntry(
                id=1,
                salutation=None,
                first_name="Anna",
                last_name="Muster",
                city=None,
                phone=None,
                archived=True,
                last_session_date=None,
                upcoming_appointments=[],
            )
        ]
    )

    color = model.data(model.index(0, 1), Qt.ItemDataRole.ForegroundRole)

    assert color == QColor(DARK_PALETTE.text_archived)


def test_inactive_treatment_types_use_the_active_themes_color(
    dark_theme: None,
) -> None:
    model = TreatmentTypeTableModel()
    model.set_types(
        [TreatmentTypeEntry(id=1, name="Reiki", description=None, active=False)]
    )

    color = model.data(model.index(0, 0), Qt.ItemDataRole.ForegroundRole)

    assert color == QColor(DARK_PALETTE.text_archived)


def _entry(entry_id: int, last_name: str) -> ClientListEntry:
    return ClientListEntry(
        id=entry_id,
        salutation=None,
        first_name="Anna",
        last_name=last_name,
        city=None,
        phone=None,
        archived=False,
        last_session_date=None,
        upcoming_appointments=[],
    )


def test_client_names_sort_in_german_order(qapp: QApplication) -> None:
    """Umlauts sort with their base letter (Ö with O), not after Z."""
    model = ClientTableModel()
    model.set_entries(
        [
            _entry(1, "Zimmer"),
            _entry(2, "Özdemir"),
            _entry(3, "Muster"),
            _entry(4, "Otto"),
        ]
    )

    model.sort(1, Qt.SortOrder.AscendingOrder)

    names = [model.entry_at(row).last_name for row in range(model.rowCount())]
    assert names == ["Muster", "Otto", "Özdemir", "Zimmer"]


def _session(session_id: int, day: int) -> SessionEntry:
    return SessionEntry(
        id=session_id,
        client_id=1,
        treatment_type_id=1,
        treatment_type_name="Meditation",
        date=datetime(2026, 9, day, 10, 0),
        duration_minutes=60,
        report=None,
        impulses=None,
    )


def test_sorting_sessions_by_date_keeps_the_selection_on_its_session(
    qapp: QApplication,
) -> None:
    """A persistent index (what a view's selection is made of) must follow
    its session to the new row - otherwise "Löschen" after a click on the
    column heading would act on a different session than the one selected."""
    model = SessionTableModel()
    model.set_sessions([_session(1, 29), _session(2, 30), _session(3, 15)], {})
    selected = QPersistentModelIndex(model.index(2, 0))

    model.sort(DATE_COLUMN, Qt.SortOrder.AscendingOrder)

    assert [model.session_at(row).id for row in range(3)] == [3, 1, 2]
    assert model.session_at(selected.row()).id == 3

    model.sort(DATE_COLUMN, Qt.SortOrder.DescendingOrder)

    assert [model.session_at(row).id for row in range(3)] == [2, 1, 3]
    assert model.session_at(selected.row()).id == 3
