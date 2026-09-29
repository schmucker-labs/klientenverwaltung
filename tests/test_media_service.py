import hashlib
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from klientenverwaltung.models import Client, TreatmentSession, TreatmentType
from klientenverwaltung.services import MediaService, NotFoundError, ValidationError
from klientenverwaltung.services.media_service import ImportOutcome, MediaUsageEntry


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


def test_import_records_added_at_as_local_time(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    """MediaTableModel displays added_at with strftime as if it already
    were local time (matching how session.date is stored) - a bare
    server_default=func.now() alone would store SQLite's CURRENT_TIMESTAMP,
    which is UTC, and silently mis-display by the local UTC offset.
    """
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 10)
    before = datetime.now()
    media_service.import_file(treatment_session.id, source)
    after = datetime.now()

    entries = media_service.list_media_for_session(treatment_session.id)
    assert len(entries) == 1
    margin = timedelta(seconds=5)
    assert before - margin <= entries[0].added_at <= after + margin


def test_cancel_during_hash_only_pass_leaves_no_file_and_no_db_row(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    """Cancelling while a same-size candidate forces the hash-only
    verification pass (no copy_to) must be honored by that pass too, not
    just by the copy pass exercised in
    test_cancel_during_copy_leaves_no_file_and_no_db_row.
    """
    content = b"y" * 4096
    first_source = _make_source_file(tmp_path, "first.bin", content)
    first = media_service.import_file(treatment_session.id, first_source)
    assert first.status == "imported"

    # Different content, same size as the existing entry -> triggers the
    # hash-only pass rather than a fresh copy.
    second_source = _make_source_file(tmp_path, "second.bin", b"z" * 4096)
    outcome = media_service.import_file(
        treatment_session.id,
        second_source,
        should_cancel=lambda: True,
        confirm_duplicate=lambda _name: pytest.fail(
            "must not reach the duplicate question when cancelled first"
        ),
    )

    assert outcome == ImportOutcome("cancelled", None, "second.bin")
    media_dir = media_service.resolve_media_path(first.media).parent
    assert len(list(media_dir.glob("*"))) == 1  # only the first file, no leftovers
    entries = media_service.list_media_for_session(treatment_session.id)
    assert [entry.media_id for entry in entries] == [first.media.id]


def test_cleanup_orphaned_part_files_removes_part_files_but_keeps_others(
    session_factory, tmp_path: Path
) -> None:
    """A .part file left behind by a hard kill/power loss/dead battery
    mid-import is by definition incomplete and was never recorded in the
    database, so removing it loses nothing. A genuine media file in the
    same folder must be left untouched.
    """
    drive_root = tmp_path / "drive"
    media_dir = drive_root / "medien"
    media_dir.mkdir(parents=True)
    orphaned = media_dir / "abc123.jpg.part"
    orphaned.write_bytes(b"partial")
    real_media = media_dir / "def456.jpg"
    real_media.write_bytes(b"complete")

    service = MediaService(session_factory, drive_root)
    removed = service.cleanup_orphaned_part_files()

    assert removed == 1
    assert not orphaned.exists()
    assert real_media.exists()


def test_cleanup_orphaned_part_files_skips_a_file_that_is_currently_open(
    session_factory, tmp_path: Path
) -> None:
    """Nothing in this program currently stops two instances from running
    at once against the same data drive - if another instance is
    mid-import, its .part file is still open for writing and must not be
    deleted out from under it. Windows refuses to unlink an open file;
    that failure must be swallowed, not raised, and the file must survive.
    """
    drive_root = tmp_path / "drive"
    media_dir = drive_root / "medien"
    media_dir.mkdir(parents=True)
    in_progress = media_dir / "xyz789.mp4.part"
    in_progress.write_bytes(b"partial")

    service = MediaService(session_factory, drive_root)
    with in_progress.open("r+b"):  # stands in for another process's open handle
        removed = service.cleanup_orphaned_part_files()

    assert removed == 0
    assert in_progress.exists()


def test_cleanup_orphaned_part_files_returns_zero_when_medien_folder_is_missing(
    session_factory, tmp_path: Path
) -> None:
    service = MediaService(session_factory, tmp_path / "drive")
    assert service.cleanup_orphaned_part_files() == 0


def test_list_all_media_reports_usage_count_and_normal_entries(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 20)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.link_existing_media(other_session.id, [outcome.media.id])

    entries = media_service.list_all_media()

    assert len(entries) == 1
    entry = entries[0]
    assert entry.media_id == outcome.media.id
    assert entry.original_filename == "foto.jpg"
    assert entry.usage_count == 2
    assert entry.file_missing is False
    assert entry.size_bytes == 20


def test_list_all_media_detects_a_missing_file(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.resolve_media_path(outcome.media).unlink()  # simulate manual deletion

    entries = media_service.list_all_media()

    assert len(entries) == 1
    assert entries[0].media_id == outcome.media.id
    assert entries[0].file_missing is True
    assert entries[0].usage_count == 1  # the DB link still exists


def test_list_all_media_detects_an_unknown_file_but_ignores_part_files(
    media_service: MediaService, tmp_path: Path
) -> None:
    media_dir = media_service.resolve_media_path_for_stored_filename("x").parent
    media_dir.mkdir(parents=True)
    unknown = media_dir / "12345678deadbeef.png"
    unknown.write_bytes(b"?" * 7)
    in_progress = media_dir / "abcdef0123456789.mp4.part"
    in_progress.write_bytes(b"partial")

    entries = media_service.list_all_media()

    assert len(entries) == 1
    entry = entries[0]
    assert entry.media_id is None
    assert entry.original_filename is None
    assert entry.stored_filename == "12345678deadbeef.png"
    assert entry.media_kind == "image"
    assert entry.size_bytes == 7
    assert entry.usage_count == 0


def test_list_usages_returns_client_name_and_session_date(
    media_service: MediaService,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)

    usages = media_service.list_usages(outcome.media.id)

    assert usages == [
        MediaUsageEntry(
            client_name=f"{client.first_name} {client.last_name}",
            session_date=treatment_session.date,
        )
    ]


def test_count_sessions_for_media_reflects_number_of_links(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    assert media_service.count_sessions_for_media(outcome.media.id) == 1

    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    media_service.link_existing_media(other_session.id, [outcome.media.id])
    assert media_service.count_sessions_for_media(outcome.media.id) == 2


def test_rename_media_updates_original_filename_only(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    stored_path = media_service.resolve_media_path(outcome.media)

    media = media_service.rename_media(outcome.media.id, "Urlaubsfoto.jpg")

    assert media.original_filename == "Urlaubsfoto.jpg"
    assert media.stored_filename == outcome.media.stored_filename
    assert stored_path.exists()  # the file on disk never moved


def test_rename_media_rejects_an_empty_name(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)

    with pytest.raises(ValidationError):
        media_service.rename_media(outcome.media.id, "   .jpg")


def test_rename_media_rejects_a_forbidden_character_anywhere_in_the_name(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)

    with pytest.raises(ValidationError):
        media_service.rename_media(outcome.media.id, "vor:nach.jpg")


def test_find_now_unused_reports_media_with_no_remaining_links(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.remove_link(treatment_session.id, outcome.media.id)

    unused = media_service.find_now_unused([outcome.media.id])

    assert [m.id for m in unused] == [outcome.media.id]


def test_find_now_unused_excludes_media_still_linked_elsewhere(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.link_existing_media(other_session.id, [outcome.media.id])

    media_service.remove_link(treatment_session.id, outcome.media.id)
    unused = media_service.find_now_unused([outcome.media.id])

    assert unused == []  # still linked to other_session


def test_deleting_a_session_leaves_its_only_medium_findable_as_unused(
    media_service: MediaService, treatment_session_service, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)

    treatment_session_service.delete_session(treatment_session.id)

    assert [m.id for m in media_service.find_now_unused([outcome.media.id])] == [
        outcome.media.id
    ]


def test_delete_unused_media_removes_file_and_db_row(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.remove_link(treatment_session.id, outcome.media.id)
    stored_path = media_service.resolve_media_path(outcome.media)

    failures = media_service.delete_unused_media([outcome.media.id])

    assert failures == []
    assert not stored_path.exists()
    assert media_service.list_all_media() == []


def test_delete_unused_media_refuses_a_still_used_medium(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    stored_path = media_service.resolve_media_path(outcome.media)

    failures = media_service.delete_unused_media([outcome.media.id])

    assert failures == []  # not reported as a failure - it's simply not deleted
    assert stored_path.exists()
    assert len(media_service.list_all_media()) == 1


def test_delete_unused_media_reports_a_file_it_cannot_remove(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.remove_link(treatment_session.id, outcome.media.id)
    stored_path = media_service.resolve_media_path(outcome.media)

    with stored_path.open("r+b"):  # stands in for "open in another program"
        failures = media_service.delete_unused_media([outcome.media.id])

    assert [m.id for m in failures] == [outcome.media.id]
    assert stored_path.exists()
    assert len(media_service.list_all_media()) == 1  # DB row kept, still 0x


def test_delete_unknown_file_removes_an_untracked_file(
    media_service: MediaService, tmp_path: Path
) -> None:
    media_dir = media_service.resolve_media_path_for_stored_filename("x").parent
    media_dir.mkdir(parents=True)
    unknown = media_dir / "12345678deadbeef.png"
    unknown.write_bytes(b"?")

    assert media_service.delete_unknown_file("12345678deadbeef.png") is True
    assert not unknown.exists()


def test_list_media_ids_for_client_deduplicates_a_file_shared_across_own_sessions(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    """The same file attached to two of one client's own sessions must be
    offered for deletion exactly once after that client is deleted, not
    once per session it was attached to.
    """
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    source = _make_source_file(tmp_path, "shared.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.link_existing_media(other_session.id, [outcome.media.id])

    ids = media_service.list_media_ids_for_client(client.id)

    assert ids == [outcome.media.id]  # not duplicated


def test_list_media_ids_for_client_covers_all_of_that_clients_sessions(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    source_a = _make_source_file(tmp_path, "a.jpg", b"a" * 5)
    source_b = _make_source_file(tmp_path, "b.jpg", b"b" * 5)
    outcome_a = media_service.import_file(treatment_session.id, source_a)
    outcome_b = media_service.import_file(other_session.id, source_b)

    ids = media_service.list_media_ids_for_client(client.id)

    assert set(ids) == {outcome_a.media.id, outcome_b.media.id}


def test_list_unlinked_media_for_session_excludes_already_linked_media(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)

    unlinked_for_original = media_service.list_unlinked_media_for_session(
        treatment_session.id
    )
    unlinked_for_other = media_service.list_unlinked_media_for_session(other_session.id)

    assert unlinked_for_original == []
    assert [e.media_id for e in unlinked_for_other] == [outcome.media.id]


def test_list_unlinked_media_for_session_filters_by_search(
    media_service: MediaService, treatment_session_service, treatment_type: TreatmentType,
    client: Client, treatment_session: TreatmentSession, tmp_path: Path,
) -> None:
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    media_service.import_file(treatment_session.id, _make_source_file(tmp_path, "urlaub.jpg", b"a" * 5))
    media_service.import_file(treatment_session.id, _make_source_file(tmp_path, "arbeit.jpg", b"b" * 5))

    results = media_service.list_unlinked_media_for_session(other_session.id, search="urla")

    assert [e.original_filename for e in results] == ["urlaub.jpg"]


def test_list_unlinked_media_for_session_search_ignores_umlaut_case(
    media_service: MediaService, treatment_session_service, treatment_type: TreatmentType,
    client: Client, treatment_session: TreatmentSession, tmp_path: Path,
) -> None:
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    media_service.import_file(treatment_session.id, _make_source_file(tmp_path, "Übung.mp3", b"a" * 5))

    results = media_service.list_unlinked_media_for_session(other_session.id, search="übung")

    assert [e.original_filename for e in results] == ["Übung.mp3"]


def test_link_existing_media_attaches_without_copying(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_dir = media_service.resolve_media_path(outcome.media).parent

    media_service.link_existing_media(other_session.id, [outcome.media.id])

    assert len(list(media_dir.glob("*.jpg"))) == 1  # no second copy
    entries = media_service.list_media_for_session(other_session.id)
    assert [e.media_id for e in entries] == [outcome.media.id]


@pytest.mark.parametrize(
    "stored_filename",
    [r"..\klientenverwaltung.db", "../klientenverwaltung.db", "..", r"C:\x.db", ""],
)
def test_file_names_outside_the_medien_folder_are_refused(
    media_service: MediaService, tmp_path: Path, stored_filename: str
) -> None:
    """Defense in depth for the planned web API: a stored file name must
    never reach outside the medien folder (e.g. to delete the database)."""
    database_file = tmp_path / "drive" / "klientenverwaltung.db"
    database_file.write_bytes(b"data")

    with pytest.raises(ValidationError):
        media_service.delete_unknown_file(stored_filename)
    with pytest.raises(ValidationError):
        media_service.resolve_media_path_for_stored_filename(stored_filename)

    assert database_file.read_bytes() == b"data"
