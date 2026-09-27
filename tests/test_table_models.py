import pytest
from PySide6.QtCore import Qt

from klientenverwaltung.ui.backup_table_model import BackupTableModel
from klientenverwaltung.ui.client_table_model import ClientTableModel
from klientenverwaltung.ui.media_table_model import MediaTableModel
from klientenverwaltung.ui.session_table_model import SessionTableModel
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
