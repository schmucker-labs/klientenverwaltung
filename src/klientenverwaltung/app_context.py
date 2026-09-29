"""What the UI shares: the services and the open database.

Bundled so that a new dependency (say, a service for appointments) does not
change the constructor of every window between the main window and the
dialog that finally needs it. Built once in main.py, the composition root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from klientenverwaltung import storage
from klientenverwaltung.services import (
    ClientService,
    MediaService,
    TreatmentSessionService,
    TreatmentTypeService,
)


class OpenDatabase:
    """The data drive's open, encrypted database.

    Every service creates its sessions from the one session factory held
    here, so replace_engine() - after a password change - re-points all of
    them at once, without rebuilding services or windows.
    """

    def __init__(self, engine: Engine, drive_root: Path) -> None:
        self._engine = engine
        self._drive_root = drive_root
        self._session_factory: sessionmaker[Session] = sessionmaker(
            bind=engine, expire_on_commit=False
        )
        self._closed = False

    @property
    def engine(self) -> Engine:
        return self._engine

    @property
    def drive_root(self) -> Path:
        return self._drive_root

    @property
    def db_path(self) -> Path:
        return self._drive_root / storage.DB_FILENAME

    @property
    def password(self) -> str:
        return self._engine.url.password or ""

    @property
    def session_factory(self) -> sessionmaker[Session]:
        return self._session_factory

    @property
    def closed(self) -> bool:
        """True once the database file was replaced or released for good
        (e.g. by a restore) - nothing may use it again in this run."""
        return self._closed

    def replace_engine(self, engine: Engine) -> None:
        """Switches every service to engine and disposes the previous one."""
        previous = self._engine
        self._session_factory.configure(bind=engine)
        self._engine = engine
        previous.dispose()

    def close(self) -> None:
        self._engine.dispose()
        self._closed = True


@dataclass(frozen=True)
class AppServices:
    clients: ClientService
    treatment_types: TreatmentTypeService
    treatment_sessions: TreatmentSessionService
    media: MediaService

    @classmethod
    def for_database(cls, database: OpenDatabase) -> AppServices:
        session_factory = database.session_factory
        return cls(
            clients=ClientService(session_factory),
            treatment_types=TreatmentTypeService(session_factory),
            treatment_sessions=TreatmentSessionService(session_factory),
            media=MediaService(session_factory, database.drive_root),
        )
