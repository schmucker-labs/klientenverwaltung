from pathlib import Path

from klientenverwaltung.models import Client, TreatmentSession, TreatmentType
from klientenverwaltung.services import MediaService, TreatmentSessionService
from klientenverwaltung.ui.media_overview_dialog import MediaOverviewDialog


def _make_source_file(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_delete_button_disabled_when_selection_mixes_used_and_unused(
    qapp,
    media_service: MediaService,
    treatment_session_service: TreatmentSessionService,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    media_service.import_file(
        treatment_session.id, _make_source_file(tmp_path, "used.jpg", b"a" * 5)
    )
    unused_outcome = media_service.import_file(
        treatment_session.id, _make_source_file(tmp_path, "unused.jpg", b"b" * 5)
    )
    media_service.remove_link(treatment_session.id, unused_outcome.media.id)

    dialog = MediaOverviewDialog(media_service)
    dialog._table_view.selectAll()  # selects both the used and the unused row
    dialog._update_button_states()

    assert dialog._delete_button.isEnabled() is False
    assert "Sitzung" in dialog._delete_button.toolTip()

    dialog._table_view.clearSelection()
    for row in range(dialog._table_model.rowCount()):
        if dialog._table_model.entry_at(row).media_id == unused_outcome.media.id:
            dialog._table_view.selectRow(row)
    dialog._update_button_states()

    assert dialog._delete_button.isEnabled() is True
