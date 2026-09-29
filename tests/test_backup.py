import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, text

from klientenverwaltung import backup, storage


@pytest.fixture(autouse=True)
def _isolated_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let these tests touch the developer's real %APPDATA%."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    drive = tmp_path / "drive"
    drive.mkdir()
    created = storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort")
    yield created
    created.dispose()


class TestCreateBackupRotation:
    def test_keeps_only_the_ten_most_recent_backups(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        target = tmp_path / "backups"
        base = datetime(2026, 1, 1, 12, 0)

        created_paths = [
            backup.create_backup(engine, target, now=base + timedelta(minutes=i))
            for i in range(12)
        ]

        remaining = backup.list_backups(target)
        assert len(remaining) == backup.MAX_BACKUPS_KEPT
        # newest-first: the two oldest (index 0, 1) must have been rotated away
        assert set(remaining) == set(created_paths[2:])

    def test_same_second_collision_gets_a_distinct_filename(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        target = tmp_path / "backups"
        same_instant = datetime(2026, 1, 1, 12, 0, 0)

        first = backup.create_backup(engine, target, now=same_instant)
        second = backup.create_backup(engine, target, now=same_instant)

        assert first != second
        assert first.exists()
        assert second.exists()

    def test_list_backups_is_newest_first(self, engine: Engine, tmp_path: Path) -> None:
        target = tmp_path / "backups"
        base = datetime(2026, 1, 1, 12, 0)
        oldest = backup.create_backup(engine, target, now=base)
        newest = backup.create_backup(engine, target, now=base + timedelta(hours=1))

        result = backup.list_backups(target)

        assert result[0] == newest
        assert result[-1] == oldest


class TestPreRestoreBackup:
    def test_lives_in_its_own_subfolder_with_its_own_rotation(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        target = tmp_path / "backups"
        base = datetime(2026, 1, 1, 12, 0)

        # Fill the regular rotation to its limit first.
        regular_paths = [
            backup.create_backup(engine, target, now=base + timedelta(minutes=i))
            for i in range(backup.MAX_BACKUPS_KEPT)
        ]

        pre_restore_paths = [
            backup.create_pre_restore_backup(
                engine, target, now=base + timedelta(hours=1, minutes=i)
            )
            for i in range(backup.PRE_RESTORE_MAX_BACKUPS_KEPT + 2)
        ]

        # The pre-restore backups must not have evicted any regular backup.
        assert set(backup.list_backups(target)) == set(regular_paths)
        # And their own rotation (5) must still apply, independently.
        pre_restore_folder = target / backup.PRE_RESTORE_SUBFOLDER_NAME
        remaining_pre_restore = backup.list_backups(pre_restore_folder)
        assert len(remaining_pre_restore) == backup.PRE_RESTORE_MAX_BACKUPS_KEPT
        assert set(remaining_pre_restore) == set(
            pre_restore_paths[-backup.PRE_RESTORE_MAX_BACKUPS_KEPT :]
        )


class TestMostRecentBackup:
    def test_picks_the_newest_across_multiple_folders(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        folder_a = tmp_path / "a"
        folder_b = tmp_path / "b"
        base = datetime(2026, 1, 1, 12, 0)
        backup.create_backup(engine, folder_a, now=base)
        newest = backup.create_backup(engine, folder_b, now=base + timedelta(hours=1))
        backup.create_backup(engine, folder_a, now=base + timedelta(minutes=30))

        result = backup.most_recent_backup([folder_a, folder_b])

        assert result == newest

    def test_none_when_no_folder_has_any_backup(self, tmp_path: Path) -> None:
        assert backup.most_recent_backup([tmp_path / "empty"]) is None


class TestIsDatabaseUnchangedSinceBackup:
    def test_true_when_database_not_modified_after_backup(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        target = tmp_path / "backups"
        backup_path = backup.create_backup(engine, target)
        db_path = tmp_path / "drive" / storage.DB_FILENAME
        backup_time = backup.parse_backup_timestamp(backup_path)
        assert backup_time is not None
        os.utime(db_path, (backup_time.timestamp(), backup_time.timestamp()))

        assert backup.is_database_unchanged_since_backup(db_path, backup_path) is True

    def test_false_when_database_modified_after_backup(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        target = tmp_path / "backups"
        backup_path = backup.create_backup(engine, target)
        db_path = tmp_path / "drive" / storage.DB_FILENAME
        future = datetime.now() + timedelta(days=1)
        os.utime(db_path, (future.timestamp(), future.timestamp()))

        assert backup.is_database_unchanged_since_backup(db_path, backup_path) is False

    def test_true_right_after_a_real_backup_despite_sub_second_mtime(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        """Backup filenames only carry whole-second resolution, but a real
        file's mtime has sub-second precision - naively comparing the two
        makes the database look "newer" than the backup almost every time,
        even though the backup was just taken. Regression test: no os.utime
        trickery, just a real create_backup() call like production code."""
        target = tmp_path / "backups"
        db_path = tmp_path / "drive" / storage.DB_FILENAME

        backup_path = backup.create_backup(engine, target)

        assert backup.is_database_unchanged_since_backup(db_path, backup_path) is True

    def test_false_when_no_backup_exists_yet(self, tmp_path: Path) -> None:
        db_path = tmp_path / "drive" / storage.DB_FILENAME
        assert backup.is_database_unchanged_since_backup(db_path, None) is False


class TestIsWritableDirectory:
    def test_true_for_a_writable_existing_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "writable"
        target.mkdir()
        assert backup.is_writable_directory(target) is True

    def test_false_for_a_nonexistent_directory(self, tmp_path: Path) -> None:
        assert backup.is_writable_directory(tmp_path / "missing") is False

    def test_false_for_a_path_that_is_a_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "a_file"
        file_path.write_bytes(b"x")
        assert backup.is_writable_directory(file_path) is False


class TestDeleteBackup:
    def test_removes_the_file(self, engine: Engine, tmp_path: Path) -> None:
        target = tmp_path / "backups"
        backup_path = backup.create_backup(engine, target)

        backup.delete_backup(backup_path)

        assert not backup_path.exists()

    def test_raises_backup_error_when_file_is_missing(self, tmp_path: Path) -> None:
        with pytest.raises(backup.BackupError):
            backup.delete_backup(tmp_path / "does-not-exist.db")


class TestCreateBackupUnreachableTarget:
    def test_raises_backup_error_when_target_cannot_be_created(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        # A regular file where a directory is expected makes mkdir() fail,
        # simulating an unreachable backup target (e.g. a disconnected
        # network share or missing second drive).
        blocking_file = tmp_path / "not_a_directory"
        blocking_file.write_bytes(b"x")
        unreachable_target = blocking_file / "backups"

        with pytest.raises(backup.BackupError):
            backup.create_backup(engine, unreachable_target)

    def test_does_not_raise_a_raw_exception_type(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        """Only BackupError should ever cross this boundary, per the
        service-layer convention of never leaking raw library exceptions."""
        blocking_file = tmp_path / "not_a_directory"
        blocking_file.write_bytes(b"x")
        unreachable_target = blocking_file / "backups"

        try:
            backup.create_backup(engine, unreachable_target)
        except backup.BackupError:
            pass
        except Exception as exc:  # noqa: BLE001 - deliberately broad for this check
            pytest.fail(f"leaked a raw {type(exc).__name__} instead of BackupError")


class TestRestoreBackup:
    def test_restores_database_to_the_state_at_backup_time(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        target = tmp_path / "backups"
        with engine.connect() as connection:
            connection.execute(
                text(
                    "INSERT INTO client (first_name, last_name, archived) "
                    "VALUES ('Anna', 'Muster', 0)"
                )
            )
            connection.commit()

        backup_path = backup.create_backup(engine, target)

        with engine.connect() as connection:
            connection.execute(
                text(
                    "INSERT INTO client (first_name, last_name, archived) "
                    "VALUES ('Berta', 'Beispiel', 0)"
                )
            )
            connection.commit()
        engine.dispose()

        db_path = tmp_path / "drive" / storage.DB_FILENAME
        backup.restore_backup(backup_path, db_path)

        restored_engine = storage.open_database(db_path, "ein-sehr-sicheres-passwort")
        try:
            with restored_engine.connect() as connection:
                names = {
                    row[0]
                    for row in connection.execute(text("SELECT first_name FROM client"))
                }
        finally:
            restored_engine.dispose()

        assert names == {"Anna"}, "only the client present at backup time survives"

    def test_raises_backup_error_when_backup_file_is_missing(
        self, tmp_path: Path
    ) -> None:
        missing_backup = tmp_path / "does-not-exist.db"
        db_path = tmp_path / "drive" / storage.DB_FILENAME

        with pytest.raises(backup.BackupError):
            backup.restore_backup(missing_backup, db_path)

    def test_leaves_existing_database_untouched_if_copy_fails_partway(
        self, engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        target = tmp_path / "backups"
        backup_path = backup.create_backup(engine, target)
        engine.dispose()

        db_path = tmp_path / "drive" / storage.DB_FILENAME
        original_content = db_path.read_bytes()

        def _failing_copy2(*_args: object, **_kwargs: object) -> None:
            raise OSError("simulated failure partway through the copy")

        monkeypatch.setattr(backup.shutil, "copy2", _failing_copy2)

        with pytest.raises(backup.BackupError):
            backup.restore_backup(backup_path, db_path)

        assert db_path.read_bytes() == original_content
        assert not (db_path.with_name(db_path.name + ".restoring")).exists()

    def test_prepare_hook_changes_the_copy_before_it_replaces_the_database(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        """Used to re-encrypt a backup made under an older password with the
        current one, so the restored database opens with today's password."""
        backup_path = backup.create_backup(engine, tmp_path / "backups")
        engine.dispose()
        db_path = tmp_path / "drive" / storage.DB_FILENAME

        backup.restore_backup(
            backup_path,
            db_path,
            prepare=lambda copy: storage.rekey_database_file(
                copy, "ein-sehr-sicheres-passwort", "das-neue-passwort-1"
            ),
        )

        storage.verify_database_file(db_path, "das-neue-passwort-1")
        storage.verify_database_file(backup_path, "ein-sehr-sicheres-passwort")

    def test_failing_prepare_hook_leaves_existing_database_untouched(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        backup_path = backup.create_backup(engine, tmp_path / "backups")
        engine.dispose()
        db_path = tmp_path / "drive" / storage.DB_FILENAME
        original_content = db_path.read_bytes()

        def _failing_prepare(_copy: Path) -> None:
            raise storage.StorageError("Umschlüsseln fehlgeschlagen.")

        with pytest.raises(storage.StorageError):
            backup.restore_backup(backup_path, db_path, prepare=_failing_prepare)

        assert db_path.read_bytes() == original_content
        assert not (db_path.with_name(db_path.name + ".restoring")).exists()


class TestListRestorableBackups:
    def test_includes_safety_copies_taken_before_a_restore(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        drive_root = tmp_path / "drive"
        folder = tmp_path / "backups"
        base = datetime(2026, 1, 1, 12, 0)
        on_drive = backup.create_backup(engine, drive_root, now=base)
        in_folder = backup.create_backup(engine, folder, now=base + timedelta(hours=1))
        before_restore = backup.create_pre_restore_backup(
            engine, folder, now=base + timedelta(hours=2)
        )
        before_restore_on_drive = backup.create_pre_restore_backup(
            engine, drive_root, now=base + timedelta(hours=3)
        )

        restorable = backup.list_restorable_backups(drive_root, folder)

        assert [(entry.path, entry.origin) for entry in restorable] == [
            (before_restore_on_drive, backup.BackupOrigin.PRE_RESTORE_DATA_DRIVE),
            (before_restore, backup.BackupOrigin.PRE_RESTORE_BACKUP_FOLDER),
            (in_folder, backup.BackupOrigin.BACKUP_FOLDER),
            (on_drive, backup.BackupOrigin.DATA_DRIVE),
        ]

    def test_without_a_configured_folder_lists_only_the_data_drive(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        drive_root = tmp_path / "drive"
        on_drive = backup.create_backup(engine, drive_root)

        restorable = backup.list_restorable_backups(drive_root, None)

        assert [entry.path for entry in restorable] == [on_drive]


class TestParseBackupTimestamp:
    def test_parses_the_suffix_of_a_same_second_collision(self, tmp_path: Path) -> None:
        second_in_same_second = tmp_path / "klientenverwaltung_backup_20260101_120000_2.db"

        assert backup.parse_backup_timestamp(second_in_same_second) == datetime(
            2026, 1, 1, 12, 0, 0
        )


class TestBackUpIfChanged:
    def test_backs_up_a_database_changed_since_the_last_backup(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        folder = tmp_path / "backups"
        db_path = tmp_path / "drive" / storage.DB_FILENAME
        long_ago = datetime.now() - timedelta(days=1)
        backup.create_backup(engine, folder, now=long_ago)

        created = backup.back_up_if_changed(engine, db_path, folder)

        assert created is not None
        assert len(backup.list_backups(folder)) == 2

    def test_skips_a_database_unchanged_since_the_last_backup(
        self, engine: Engine, tmp_path: Path
    ) -> None:
        folder = tmp_path / "backups"
        db_path = tmp_path / "drive" / storage.DB_FILENAME
        backup.create_backup(engine, folder, now=datetime.now() + timedelta(minutes=1))

        assert backup.back_up_if_changed(engine, db_path, folder) is None
        assert len(backup.list_backups(folder)) == 1


class TestBackupFolderWarning:
    def test_warns_about_a_folder_on_the_data_drive_itself(self, tmp_path: Path) -> None:
        warning = backup.backup_folder_warning(tmp_path / "Sicherungen", tmp_path / "drive")

        assert warning is not None
        assert "Datenplatte" in warning

    @pytest.mark.parametrize(
        "folder",
        [
            Path("D:/Benutzer/Anna/OneDrive/Sicherungen"),
            Path("D:/Benutzer/Anna/OneDrive - Praxis/Sicherungen"),
            Path("D:/Dropbox/Klienten"),
        ],
    )
    def test_warns_about_a_cloud_synced_folder(self, folder: Path) -> None:
        warning = backup.backup_folder_warning(folder, Path("E:/"))

        assert warning is not None
        assert "Cloud" in warning

    def test_no_warning_for_a_folder_on_another_local_drive(self) -> None:
        assert backup.backup_folder_warning(Path("D:/Sicherungen"), Path("E:/")) is None
