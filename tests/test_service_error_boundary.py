"""Only ServiceError (with a German message) may leave the service layer -
for reads as much as for writes, and for a vanished data drive too."""

import shutil
from pathlib import Path

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from klientenverwaltung import storage
from klientenverwaltung.services import (
    ClientService,
    DataUnavailableError,
    ServiceError,
    TreatmentSessionService,
)


@pytest.fixture(autouse=True)
def _isolated_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


def test_a_failing_read_raises_service_error(
    engine: Engine, client_service: ClientService
) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE client RENAME TO client_gone")

    with pytest.raises(ServiceError):
        client_service.list_clients_with_last_session()


def test_a_failing_read_in_another_service_raises_service_error(
    engine: Engine, treatment_session_service: TreatmentSessionService
) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE session RENAME TO session_gone")

    with pytest.raises(ServiceError):
        treatment_session_service.list_sessions_for_client(1)


def test_vanished_data_drive_raises_data_unavailable_error(tmp_path: Path) -> None:
    drive = tmp_path / "drive"
    drive.mkdir()
    db_path = drive / storage.DB_FILENAME
    storage.set_up_data_drive(drive, "ein-sehr-sicheres-passwort").dispose()
    engine = storage.open_database(db_path, "ein-sehr-sicheres-passwort")
    client_service = ClientService(sessionmaker(bind=engine, expire_on_commit=False))
    client_service.list_clients()
    engine.dispose()  # releases Windows' file lock, see test_storage

    shutil.rmtree(drive)

    with pytest.raises(DataUnavailableError, match="Datenplatte"):
        client_service.list_clients()
