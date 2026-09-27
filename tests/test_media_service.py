import hashlib
from pathlib import Path

import pytest

from klientenverwaltung.models import Client, TreatmentSession, TreatmentType
from klientenverwaltung.services import MediaService, NotFoundError
from klientenverwaltung.services.media_service import ImportOutcome


def _make_source_file(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_import_copies_file_and_links_it_to_the_session(
    media_service: MediaService,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5000)

    outcome = media_service.import_file(treatment_session.id, source)

    assert outcome.status == "imported"
    assert outcome.media is not None
    assert outcome.media.media_kind == "image"
    assert outcome.media.size_bytes == 5000
    assert outcome.media.sha256 == hashlib.sha256(b"a" * 5000).hexdigest()

    stored_path = media_service.resolve_media_path(outcome.media)
    assert stored_path.read_bytes() == b"a" * 5000
    assert stored_path.name != source.name  # neutral uuid name, not the original

    entries = media_service.list_media_for_session(treatment_session.id)
    assert [entry.media_id for entry in entries] == [outcome.media.id]
    assert entries[0].original_filename == "foto.jpg"


def test_duplicate_content_is_linked_not_recopied(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    tmp_path: Path,
) -> None:
    from datetime import datetime

    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 2, 1, 9, 0),
        duration_minutes=45,
    )
    session_a_id = other_session.id
    other_session_b = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 2, 2, 9, 0),
        duration_minutes=45,
    )
    session_b_id = other_session_b.id

    content = b"same bytes" * 1000
    source_a = _make_source_file(tmp_path, "original.mp4", content)
    first = media_service.import_file(session_a_id, source_a)
    assert first.status == "imported"

    # Different filename, identical content, attached to a *different*
    # session - must be recognized as the same file by hash and only
    # linked, never copied a second time.
    source_b = _make_source_file(tmp_path, "kopie.mp4", content)
    confirmations: list[str] = []
    second = media_service.import_file(
        session_b_id,
        source_b,
        confirm_duplicate=lambda original_filename: confirmations.append(
            original_filename
        )
        or True,
    )
    assert second.status == "linked_existing"
    assert second.media.id == first.media.id
    assert confirmations == ["original.mp4"]

    media_dir = media_service.resolve_media_path(first.media).parent
    assert len(list(media_dir.glob("*.mp4"))) == 1  # copied exactly once

    # Attaching the *same* content to session_a again, where it is already
    # linked: must short-circuit to "already_linked" without even asking.
    source_c = _make_source_file(tmp_path, "nochmal.mp4", content)
    third = media_service.import_file(
        session_a_id,
        source_c,
        confirm_duplicate=lambda _original_filename: pytest.fail(
            "must not ask when already linked to this session"
        ),
    )
    assert third.status == "already_linked"
    assert third.media.id == first.media.id


def test_cancel_during_copy_leaves_no_file_and_no_db_row(
    session_factory, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    drive_root = tmp_path / "drive"
    drive_root.mkdir()
    service = MediaService(session_factory, drive_root)
    source = _make_source_file(tmp_path, "video.mp4", b"x" * (2 * 1024 * 1024))

    outcome = service.import_file(
        treatment_session.id, source, should_cancel=lambda: True
    )

    assert outcome == ImportOutcome("cancelled", None, "video.mp4")
    media_dir = drive_root / "medien"
    leftovers = list(media_dir.glob("*")) if media_dir.exists() else []
    assert leftovers == []
    assert service.list_media_for_session(treatment_session.id) == []


def test_deleting_session_removes_link_but_keeps_media_and_file(
    media_service: MediaService,
    session_factory,
    treatment_session_service,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    from klientenverwaltung.repositories import MediaRepository

    source = _make_source_file(tmp_path, "aufnahme.mp3", b"audio" * 100)
    outcome = media_service.import_file(treatment_session.id, source)
    media_id = outcome.media.id
    stored_path = media_service.resolve_media_path(outcome.media)

    treatment_session_service.delete_session(treatment_session.id)

    assert media_service.list_media_for_session(treatment_session.id) == []
    assert stored_path.exists()  # file untouched (cleanup is Auftrag C2)
    with session_factory() as session:
        assert MediaRepository(session).get_by_id(media_id) is not None


def test_resolve_media_path_uses_the_given_drive_root(
    session_factory, tmp_path: Path, treatment_session: TreatmentSession
) -> None:
    original_root = tmp_path / "drive-one"
    original_root.mkdir()
    service_a = MediaService(session_factory, original_root)
    source = _make_source_file(tmp_path, "bild.png", b"p" * 10)
    outcome = service_a.import_file(treatment_session.id, source)

    # Same database, different drive_root (e.g. the drive was remounted
    # under a different letter, or opened from a different machine) -
    # resolve_media_path must follow the new root, since only the relative
    # stored_filename is ever persisted.
    other_root = tmp_path / "drive-two"
    service_b = MediaService(session_factory, other_root)
    resolved = service_b.resolve_media_path(outcome.media)

    assert resolved == other_root / "medien" / outcome.media.stored_filename
    assert not str(resolved).startswith(str(original_root))


def test_import_raises_not_found_for_unknown_session(
    media_service: MediaService, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "x.jpg", b"x")
    with pytest.raises(NotFoundError):
        media_service.import_file(999, source)
