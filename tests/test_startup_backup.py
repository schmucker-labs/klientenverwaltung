"""main._run_startup_backup: when the automatic backup at startup runs."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine

from klientenverwaltung import backup, config, main, storage


@pytest.fixture(autouse=True)
def _isolated_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    drive = tmp_path / "drive"
    drive.mkdir()
    created = storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort")
    yield created
    created.dispose()


def test_a_newer_copy_on_the_data_drive_does_not_count_as_backed_up(
    engine: Engine, tmp_path: Path
) -> None:
    """The data drive's own fallback copy protects nothing against losing
    the drive: once the external folder is reachable again, a database
    changed since the folder's last backup must be backed up there."""
    drive_root = tmp_path / "drive"
    folder = tmp_path / "backups"
    config.set_backup_folder_path(folder)
    now = datetime.now()
    backup.create_backup(engine, folder, now=now - timedelta(days=2))
    # made while the folder was unreachable - newer than the database file
    backup.create_backup(engine, drive_root, now=now + timedelta(minutes=5))

    assert main._run_startup_backup(engine, drive_root) is True

    assert len(backup.list_backups(folder)) == 2
