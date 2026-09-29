import shutil
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from klientenverwaltung import storage


@pytest.fixture(autouse=True)
def _isolated_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let storage/config tests touch the developer's real %APPDATA%."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


def _make_drive_with_identifier(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / storage.IDENTIFIER_FILENAME).write_text(str(uuid.uuid4()), encoding="utf-8")
    return root


class TestFindDataDriveAmong:
    def test_raises_not_found_when_no_candidate_matches(self, tmp_path: Path) -> None:
        empty_drive = tmp_path / "empty"
        empty_drive.mkdir()

        with pytest.raises(storage.DataDriveNotFoundError):
            storage._find_data_drive_among([empty_drive], last_known_path=None)

    def test_returns_the_single_matching_candidate(self, tmp_path: Path) -> None:
        drive = _make_drive_with_identifier(tmp_path / "drive")
        other = tmp_path / "other"
        other.mkdir()

        found = storage._find_data_drive_among([drive, other], last_known_path=None)

        assert found == drive

    def test_raises_on_multiple_matching_candidates(self, tmp_path: Path) -> None:
        drive_a = _make_drive_with_identifier(tmp_path / "a")
        drive_b = _make_drive_with_identifier(tmp_path / "b")

        with pytest.raises(storage.MultipleDataDrivesFoundError) as exc_info:
            storage._find_data_drive_among([drive_a, drive_b], last_known_path=None)

        assert set(exc_info.value.candidate_paths) == {drive_a, drive_b}

    def test_checks_last_known_path_first_and_skips_the_scan(
        self, tmp_path: Path
    ) -> None:
        last_known = _make_drive_with_identifier(tmp_path / "last-known")
        # Deliberately ambiguous candidates: if the scan ran, this would raise.
        drive_a = _make_drive_with_identifier(tmp_path / "a")
        drive_b = _make_drive_with_identifier(tmp_path / "b")

        found = storage._find_data_drive_among(
            [drive_a, drive_b], last_known_path=last_known
        )

        assert found == last_known

    def test_falls_back_to_scan_when_last_known_path_no_longer_matches(
        self, tmp_path: Path
    ) -> None:
        stale_last_known = tmp_path / "gone"  # never created
        drive = _make_drive_with_identifier(tmp_path / "drive")

        found = storage._find_data_drive_among(
            [drive], last_known_path=stale_last_known
        )

        assert found == drive

    def test_unresponsive_drive_is_skipped_within_timeout(self, tmp_path: Path) -> None:
        good_drive = _make_drive_with_identifier(tmp_path / "good")
        unresponsive_drive = tmp_path / "unresponsive"
        unresponsive_drive.mkdir()

        def slow_reader(path: Path) -> str | None:
            if path == unresponsive_drive:
                time.sleep(2)
            return storage._read_identifier_file(path)

        started = time.monotonic()
        found = storage._find_data_drive_among(
            [good_drive, unresponsive_drive],
            last_known_path=None,
            reader=slow_reader,
            timeout=0.1,
        )

        assert found == good_drive
        # The search must not wait for the hung drive (e.g. an offline
        # network drive letter) - that is the whole point of the timeout.
        assert time.monotonic() - started < 1.0

    def test_unresponsive_last_known_drive_does_not_block_the_search(
        self, tmp_path: Path
    ) -> None:
        good_drive = _make_drive_with_identifier(tmp_path / "good")
        unresponsive_last_known = tmp_path / "unresponsive"
        unresponsive_last_known.mkdir()

        def slow_reader(path: Path) -> str | None:
            if path == unresponsive_last_known:
                time.sleep(2)
            return storage._read_identifier_file(path)

        started = time.monotonic()
        found = storage._find_data_drive_among(
            [good_drive],
            last_known_path=unresponsive_last_known,
            reader=slow_reader,
            timeout=0.1,
        )

        assert found == good_drive
        assert time.monotonic() - started < 1.0


class TestSetUpDataDrive:
    def test_creates_identifier_file_and_database_without_treatment_types(
        self, tmp_path: Path
    ) -> None:
        drive = tmp_path / "drive"
        drive.mkdir()

        engine = storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort")
        try:
            identifier_content = (drive / storage.IDENTIFIER_FILENAME).read_text(
                encoding="utf-8"
            )
            uuid.UUID(identifier_content)  # does not raise
            assert (drive / storage.DB_FILENAME).exists()

            # Auftrag D1: the user creates their own treatment types, so
            # setup must not pre-populate any.
            with engine.connect() as connection:
                count = connection.execute(
                    text("SELECT count(*) FROM treatment_type")
                ).scalar()
            assert count == 0
        finally:
            engine.dispose()

    def test_rejects_password_shorter_than_minimum(self, tmp_path: Path) -> None:
        drive = tmp_path / "drive"
        drive.mkdir()

        with pytest.raises(storage.WeakPasswordError):
            storage.set_up_data_drive(drive, "zu-kurz")

    def test_refuses_a_drive_that_is_already_fully_set_up(self, tmp_path: Path) -> None:
        drive = tmp_path / "drive"
        drive.mkdir()
        storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort").dispose()

        with pytest.raises(storage.StorageError):
            storage.set_up_data_drive(drive, "ein-anderes-passwort-123")

    def test_completes_an_interrupted_setup_with_identifier_but_no_database(
        self, tmp_path: Path
    ) -> None:
        drive = _make_drive_with_identifier(tmp_path / "drive")

        engine = storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort")
        engine.dispose()

        assert storage.drive_already_set_up(drive) is True

    def test_writes_no_identifier_file_when_setup_fails_unexpectedly(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Any failure - not just a StorageError - must leave the drive as if
        setup never ran; otherwise the next start finds an identifier
        without a database and the wizard refuses the drive."""
        drive = tmp_path / "drive"
        drive.mkdir()

        def _crashing_apply_migrations(_engine: object) -> None:
            raise ModuleNotFoundError("No module named 'logging.config'")

        monkeypatch.setattr(storage, "apply_migrations", _crashing_apply_migrations)

        with pytest.raises(ModuleNotFoundError):
            storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort")

        assert not (drive / storage.IDENTIFIER_FILENAME).exists()
        assert not (drive / storage.DB_FILENAME).exists()

    def test_keeps_a_pre_existing_identifier_when_completing_setup_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        drive = _make_drive_with_identifier(tmp_path / "drive")
        identifier_before = (drive / storage.IDENTIFIER_FILENAME).read_text(
            encoding="utf-8"
        )

        def _failing_apply_migrations(_engine: object) -> None:
            raise storage.StorageError("Migration ist fehlgeschlagen.")

        monkeypatch.setattr(storage, "apply_migrations", _failing_apply_migrations)

        with pytest.raises(storage.StorageError):
            storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort")

        assert (drive / storage.IDENTIFIER_FILENAME).read_text(
            encoding="utf-8"
        ) == identifier_before
        assert not (drive / storage.DB_FILENAME).exists()

    def test_refuses_to_overwrite_existing_database_file(self, tmp_path: Path) -> None:
        drive = tmp_path / "drive"
        drive.mkdir()
        (drive / storage.DB_FILENAME).write_bytes(b"")

        with pytest.raises(storage.StorageError):
            storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort")

    def test_cleans_up_identifier_and_database_file_when_migrations_fail(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        drive = tmp_path / "drive"
        drive.mkdir()

        def _failing_apply_migrations(_engine: object) -> None:
            raise storage.StorageError("Migration ist fehlgeschlagen.")

        monkeypatch.setattr(storage, "apply_migrations", _failing_apply_migrations)

        with pytest.raises(storage.StorageError, match="Migration ist fehlgeschlagen"):
            storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort")

        assert not (drive / storage.IDENTIFIER_FILENAME).exists()
        assert not (drive / storage.DB_FILENAME).exists()


class TestHasPendingMigrations:
    def test_false_right_after_set_up_data_drive(self, tmp_path: Path) -> None:
        drive = tmp_path / "drive"
        drive.mkdir()
        engine = storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort")
        try:
            assert storage.has_pending_migrations(engine) is False
        finally:
            engine.dispose()

    def test_true_when_database_predates_the_latest_migration(
        self, tmp_path: Path
    ) -> None:
        from alembic import command

        drive = tmp_path / "drive"
        drive.mkdir()
        db_path = drive / storage.DB_FILENAME
        engine = storage.create_encrypted_engine(db_path, "ein-sehr-sicheres-passwort")
        try:
            with engine.connect() as connection:
                command.upgrade(storage._alembic_config(connection), "9ac5d775d208")
            assert storage.has_pending_migrations(engine) is True
        finally:
            engine.dispose()


class TestDriveAlreadySetUp:
    def test_true_when_identifier_and_database_present(self, tmp_path: Path) -> None:
        drive = _make_drive_with_identifier(tmp_path / "drive")
        (drive / storage.DB_FILENAME).write_bytes(b"")
        assert storage.drive_already_set_up(drive) is True

    def test_false_for_an_interrupted_setup_without_database(
        self, tmp_path: Path
    ) -> None:
        drive = _make_drive_with_identifier(tmp_path / "drive")
        assert storage.drive_already_set_up(drive) is False

    def test_false_when_no_identifier_file(self, tmp_path: Path) -> None:
        drive = tmp_path / "drive"
        drive.mkdir()
        assert storage.drive_already_set_up(drive) is False


class TestOpenDatabase:
    def test_opens_with_correct_password(self, tmp_path: Path) -> None:
        drive = tmp_path / "drive"
        drive.mkdir()
        storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort").dispose()

        engine = storage.open_database(
            drive / storage.DB_FILENAME, "ein-sehr-sicheres-passwort"
        )
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT count(*) FROM client"))
        finally:
            engine.dispose()

    def test_raises_incorrect_password_error_for_wrong_password(
        self, tmp_path: Path
    ) -> None:
        drive = tmp_path / "drive"
        drive.mkdir()
        storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort").dispose()

        with pytest.raises(storage.IncorrectPasswordError):
            storage.open_database(drive / storage.DB_FILENAME, "falsches-passwort-123")

    def test_raises_storage_error_when_database_file_is_missing(
        self, tmp_path: Path
    ) -> None:
        drive = tmp_path / "drive"
        drive.mkdir()

        with pytest.raises(storage.StorageError):
            storage.open_database(
                drive / storage.DB_FILENAME, "ein-sehr-sicheres-passwort"
            )

    @pytest.mark.parametrize(
        "password",
        [
            "Sommer@Wiese2026",
            "a:b@c:d@e12345678",
            "Sommer%41Wiese2026",
            'mit"Anführungs\'zeichen',
            "mein?pass#wort/12:",
            "Grüße-aus-Köln-ß",
        ],
    )
    def test_password_with_special_characters_is_used_verbatim(
        self, tmp_path: Path, password: str
    ) -> None:
        drive = tmp_path / "drive"
        drive.mkdir()
        storage.set_up_data_drive(drive, password).dispose()

        engine = storage.open_database(drive / storage.DB_FILENAME, password)
        engine.dispose()

    def test_percent_escape_in_password_is_not_url_decoded(self, tmp_path: Path) -> None:
        drive = tmp_path / "drive"
        drive.mkdir()
        storage.set_up_data_drive(drive, "Sommer%41Wiese2026").dispose()

        with pytest.raises(storage.IncorrectPasswordError):
            storage.open_database(drive / storage.DB_FILENAME, "SommerAWiese2026")

    def test_database_errors_never_carry_statement_parameters(
        self, tmp_path: Path
    ) -> None:
        """Parameters can be client data - they must never end up in an
        exception message, which may reach the crash log on the laptop."""
        drive = tmp_path / "drive"
        drive.mkdir()
        engine = storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort")
        try:
            with pytest.raises(DBAPIError) as exc_info, engine.connect() as connection:
                connection.execute(
                    text(
                        "INSERT INTO client (first_name, last_name, archived) "
                        "VALUES (:first_name, NULL, 0)"
                    ),
                    {"first_name": "Anna Geheimname"},
                )
            assert "Geheimname" not in str(exc_info.value)
        finally:
            engine.dispose()

    def test_connection_loss_is_reported_as_an_invalidated_connection(
        self, tmp_path: Path
    ) -> None:
        """Approximates a mid-operation drive disconnect.

        Windows locks an open SQLite file against rename/delete, so a real
        yank-while-connected can't be reproduced here. Disposing the engine
        first releases that lock; the drive directory is then removed
        entirely (like a USB stick vanishing) and reused via the same,
        already-configured engine object to trigger the handle_error hook.

        Reported as a disconnect (connection_invalidated), so the pool drops
        its dead connections and the service layer can translate it into a
        German "Datenplatte nicht erreichbar" message.
        """
        drive = tmp_path / "drive"
        drive.mkdir()
        db_path = drive / storage.DB_FILENAME
        storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort").dispose()

        engine = storage.open_database(db_path, "ein-sehr-sicheres-passwort")
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()

        shutil.rmtree(drive)

        with pytest.raises(DBAPIError) as exc_info, engine.connect() as connection:
            connection.execute(text("SELECT * FROM client"))
        assert exc_info.value.connection_invalidated is True


class TestCreateEncryptedEngineThreading:
    def test_connection_works_from_a_different_thread(self, tmp_path: Path) -> None:
        """The media importer (Auftrag C1) runs its DB writes on a background
        QThread while the GUI thread may still be using this same engine -
        sqlite3 otherwise refuses a connection object outside the thread
        that created it. SQLAlchemy's pysqlcipher/pysqlite dialect already
        passes check_same_thread=False for a file-based database, so this
        already works today; pinned here so a future dependency upgrade
        can't silently take it away.
        """
        from concurrent.futures import ThreadPoolExecutor

        drive = tmp_path / "drive"
        drive.mkdir()
        db_path = drive / storage.DB_FILENAME
        engine = storage.create_encrypted_engine(db_path, "ein-sehr-sicheres-passwort")
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))

            def _query_from_other_thread() -> int:
                with engine.connect() as other_connection:
                    return other_connection.execute(text("SELECT 1")).scalar()

            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(_query_from_other_thread).result()
            assert result == 1
        finally:
            engine.dispose()
