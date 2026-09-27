from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from klientenverwaltung.models import Client, TreatmentSession, TreatmentType
from klientenverwaltung.services import (
    MediaService,
    ServiceError,
    TreatmentSessionService,
)
from klientenverwaltung.ui import media_overview_dialog as media_overview_dialog_module
from klientenverwaltung.ui.media_overview_dialog import MediaOverviewDialog
from klientenverwaltung.ui.media_overview_table_model import USED_COLUMN


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


def test_delete_gate_follows_the_selected_entry_across_a_header_sort(
    qapp,
    media_service: MediaService,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    """Regression: sorting by clicking a column header reorders the model's
    rows in place without remapping persistent indexes, so Qt's selection
    model kept selecting the same *row number* rather than the same
    *entry* - after a sort, the delete button (and the "Verwendet in:"
    panel) could reflect a completely different file than the one still
    visually highlighted.
    """
    media_service.import_file(
        treatment_session.id, _make_source_file(tmp_path, "used.jpg", b"a" * 5)
    )
    unused_outcome = media_service.import_file(
        treatment_session.id, _make_source_file(tmp_path, "unused.jpg", b"b" * 5)
    )
    media_service.remove_link(treatment_session.id, unused_outcome.media.id)

    dialog = MediaOverviewDialog(media_service)
    for row in range(dialog._table_model.rowCount()):
        if dialog._table_model.entry_at(row).media_id == unused_outcome.media.id:
            dialog._table_view.selectRow(row)
    dialog._update_button_states()
    assert dialog._delete_button.isEnabled() is True  # sanity: the unused file is selected

    # Re-sort by a different order - the used file must not silently end
    # up "selected" in the unused file's place.
    dialog._table_view.sortByColumn(USED_COLUMN, Qt.SortOrder.DescendingOrder)

    selected = dialog._single_selected_entry()
    assert selected is not None
    assert selected.media_id == unused_outcome.media.id  # selection followed the entry
    assert dialog._delete_button.isEnabled() is True  # still correct for that entry


def test_on_delete_clicked_shows_error_instead_of_crashing(
    qapp,
    monkeypatch: pytest.MonkeyPatch,
    media_service: MediaService,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    """Regression: delete_unused_media() ends in transaction(), whose
    whole purpose is to turn a SQLAlchemy failure into a German
    ServiceError - but the call here was bare, so that ServiceError
    escaped uncaught instead of being shown to the user.
    """
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.remove_link(treatment_session.id, outcome.media.id)

    dialog = MediaOverviewDialog(media_service)
    dialog._table_view.selectRow(0)
    dialog._update_button_states()
    assert dialog._delete_button.isEnabled() is True

    monkeypatch.setattr(
        media_overview_dialog_module, "ask_confirm_delete", lambda *a, **k: True
    )
    shown_messages: list[str] = []
    monkeypatch.setattr(
        media_overview_dialog_module,
        "show_error",
        lambda message, **k: shown_messages.append(message),
    )

    def _raise(*_args, **_kwargs):
        raise ServiceError("Mediendateien konnten nicht gelöscht werden.")

    monkeypatch.setattr(media_service, "delete_unused_media", _raise)

    dialog._on_delete_clicked()

    assert shown_messages == ["Mediendateien konnten nicht gelöscht werden."]
