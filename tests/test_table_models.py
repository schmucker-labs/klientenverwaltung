from collections.abc import Iterator

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication

from klientenverwaltung.services import ClientListEntry, TreatmentTypeEntry
from klientenverwaltung.ui.backup_table_model import BackupTableModel
from klientenverwaltung.ui.client_table_model import ClientTableModel
from klientenverwaltung.ui.media_table_model import MediaTableModel
from klientenverwaltung.ui.session_table_model import SessionTableModel
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

    assert (
        model.headerData(out_of_range_section, Qt.Orientation.Horizontal) is None
    )


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
