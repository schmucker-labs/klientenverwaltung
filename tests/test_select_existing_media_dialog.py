from pathlib import Path

import pytest

from klientenverwaltung.models import TreatmentSession
from klientenverwaltung.services import MediaService, ServiceError
from klientenverwaltung.ui import (
    select_existing_media_dialog as select_existing_media_dialog_module,
)
from klientenverwaltung.ui.select_existing_media_dialog import SelectExistingMediaDialog


def _make_source_file(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_on_add_clicked_shows_error_instead_of_crashing(
    qapp,
    monkeypatch: pytest.MonkeyPatch,
    media_service: MediaService,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    """Regression: link_existing_media() ends in transaction(), whose whole
    purpose is to turn a SQLAlchemy failure into a German ServiceError -
    but the call here was bare, so that ServiceError escaped uncaught
    instead of being shown to the user.
    """
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.remove_link(treatment_session.id, outcome.media.id)

    dialog = SelectExistingMediaDialog(media_service, treatment_session.id)
    dialog._table_view.selectRow(0)
    dialog._update_button_states()
    assert dialog._add_button.isEnabled() is True

    shown_messages: list[str] = []
    monkeypatch.setattr(
        select_existing_media_dialog_module,
        "show_error",
        lambda message, **k: shown_messages.append(message),
    )

    def _raise(*_args, **_kwargs):
        raise ServiceError("Mediendateien konnten nicht verknüpft werden.")

    monkeypatch.setattr(media_service, "link_existing_media", _raise)

    dialog._on_add_clicked()

    assert shown_messages == ["Mediendateien konnten nicht verknüpft werden."]
