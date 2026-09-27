from pathlib import Path

import pytest

from klientenverwaltung.models import TreatmentSession
from klientenverwaltung.services import MediaService, ServiceError
from klientenverwaltung.ui import media_cleanup as media_cleanup_module
from klientenverwaltung.ui.media_cleanup import offer_to_delete_now_unused_media


def _make_source_file(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_offer_to_delete_now_unused_media_shows_error_instead_of_crashing(
    monkeypatch: pytest.MonkeyPatch,
    media_service: MediaService,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    """Regression: delete_unused_media() ends in transaction(), whose
    whole purpose is to turn a SQLAlchemy failure into a German
    ServiceError - but the call here was bare, so that ServiceError
    escaped uncaught (a recoverable condition, e.g. the drive vanishing
    mid-delete, would have killed the whole application instead of
    showing its message).
    """
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.remove_link(treatment_session.id, outcome.media.id)

    monkeypatch.setattr(
        media_cleanup_module, "ask_delete_now_unused_media", lambda *a, **k: True
    )
    shown_messages: list[str] = []
    monkeypatch.setattr(
        media_cleanup_module,
        "show_error",
        lambda message, **k: shown_messages.append(message),
    )

    def _raise(*_args, **_kwargs):
        raise ServiceError("Mediendateien konnten nicht gelöscht werden.")

    monkeypatch.setattr(media_service, "delete_unused_media", _raise)

    offer_to_delete_now_unused_media(media_service, [outcome.media.id], parent=None)

    assert shown_messages == ["Mediendateien konnten nicht gelöscht werden."]
