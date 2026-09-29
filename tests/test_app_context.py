from pathlib import Path

import pytest

from klientenverwaltung import backup, config, storage
from klientenverwaltung.app_context import AppServices, OpenDatabase

_OLD = "das-alte-passwort-1"
_NEW = "das@neue%41Passwort"


@pytest.fixture(autouse=True)
def _isolated_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


@pytest.fixture
def database(tmp_path: Path) -> OpenDatabase:
    drive = tmp_path / "drive"
    drive.mkdir()
    opened = OpenDatabase(storage.set_up_data_drive(drive, _OLD), drive)
    yield opened
    opened.close()


def test_change_password_rekeys_and_keeps_every_service_working(
    database: OpenDatabase, tmp_path: Path
) -> None:
    config.set_backup_folder_path(tmp_path / "backups")
    services = AppServices.for_database(database)
    services.clients.create_client(first_name="Anna", last_name="Muster")

    database.change_password(_OLD, _NEW)

    assert database.password == _NEW
    # Services built before the change keep working on the new engine.
    services.clients.create_client(first_name="Berta", last_name="Beispiel")
    assert len(services.clients.list_clients()) == 2
    database.engine.dispose()  # release the file for the checks below
    storage.verify_database_file(database.db_path, _NEW)
    with pytest.raises(storage.IncorrectPasswordError):
        storage.verify_database_file(database.db_path, _OLD)


def test_change_password_first_backs_up_under_the_old_password(
    database: OpenDatabase, tmp_path: Path
) -> None:
    backup_folder = tmp_path / "backups"
    config.set_backup_folder_path(backup_folder)

    database.change_password(_OLD, _NEW)

    backups = backup.list_backups(backup_folder)
    assert len(backups) == 1
    storage.verify_database_file(backups[0], _OLD)


def test_change_password_rejects_a_wrong_current_password(
    database: OpenDatabase,
) -> None:
    with pytest.raises(storage.IncorrectPasswordError):
        database.change_password("nicht-das-alte-pw", _NEW)

    assert database.password == _OLD


@pytest.mark.parametrize("new_password", [_OLD, "zu-kurz"])
def test_change_password_rejects_an_unchanged_or_too_short_password(
    database: OpenDatabase, new_password: str
) -> None:
    with pytest.raises(storage.StorageError):
        database.change_password(_OLD, new_password)

    assert database.password == _OLD
