from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from klientenverwaltung.models import Base, Client, TreatmentSession, TreatmentType
from klientenverwaltung.services import (
    ClientService,
    MediaService,
    TreatmentSessionService,
    TreatmentTypeService,
)


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """A QApplication instance, required before constructing any Qt GUI
    object (QTextDocument, QWidget, ...) in a test - shared across the
    whole test session since only one may ever exist per process."""
    return QApplication.instance() or QApplication([])


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    """A temporary, file-backed (unencrypted) SQLite database for repository/service tests.

    Encryption is storage.py's concern and is already covered by the risk
    prototype; this layer only needs a real SQLite database with foreign key
    enforcement on.
    """
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture
def client_service(session_factory: sessionmaker[Session]) -> ClientService:
    return ClientService(session_factory)


@pytest.fixture
def treatment_type_service(
    session_factory: sessionmaker[Session],
) -> TreatmentTypeService:
    return TreatmentTypeService(session_factory)


@pytest.fixture
def treatment_session_service(
    session_factory: sessionmaker[Session],
) -> TreatmentSessionService:
    return TreatmentSessionService(session_factory)


@pytest.fixture
def client(client_service: ClientService) -> Client:
    return client_service.create_client(first_name="Anna", last_name="Muster")


@pytest.fixture
def treatment_type(treatment_type_service: TreatmentTypeService) -> TreatmentType:
    return treatment_type_service.create_treatment_type(name="Chakrenausgleich")


@pytest.fixture
def treatment_session(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> TreatmentSession:
    return treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 15, 10, 0),
        duration_minutes=60,
    )


@pytest.fixture
def media_service(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> MediaService:
    # The drive itself always exists on a real setup (it's a mounted USB
    # drive letter) - only its "medien" subfolder is created lazily by the
    # first import, so shutil.disk_usage() must always have a real
    # directory to inspect even before that first import.
    drive_root = tmp_path / "drive"
    drive_root.mkdir()
    return MediaService(session_factory, drive_root)
