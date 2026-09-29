"""What the UI shares: the services and the open database.

Bundled so that a new dependency (say, a service for appointments) does not
change the constructor of every window between the main window and the
dialog that finally needs it. Built once in main.py, the composition root.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from klientenverwaltung import backup, config, storage
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

    def change_password(self, current_password: str, new_password: str) -> None:
        """Re-encrypts the database with new_password ("Passwort ändern").

        Order matters: verify, then a backup under the *old* password (so a
        failed rekey can never cost data), then the rekey itself, and only
        then switch every service to an engine keyed with the new password.
        If anything before the switch fails, the old password stays valid
        and the program keeps working with it.

        Raises IncorrectPasswordError for a wrong current_password and
        StorageError (German message) for every other refusal or failure.
        """
        if not hmac.compare_digest(current_password, self.password):
            raise storage.IncorrectPasswordError("Das bisherige Passwort ist falsch.")
        if new_password == current_password:
            raise storage.StorageError(
                "Das neue Passwort muss sich vom bisherigen unterscheiden."
            )
        if len(new_password) < storage.MIN_PASSWORD_LENGTH:
            raise storage.WeakPasswordError(
                f"Das Passwort muss mindestens {storage.MIN_PASSWORD_LENGTH} "
                "Zeichen lang sein."
            )
        self._back_up_before_password_change()
        self._engine.dispose()
        storage.rekey_database_file(self.db_path, current_password, new_password)
        # From here on only new_password opens the file - no failure may
        # read like "wrong current password" or the user keeps the old one.
        try:
            new_engine = storage.open_database(self.db_path, new_password)
        except storage.StorageError as exc:
            raise storage.StorageError(
                "Das Passwort wurde geändert, die Datenbank ließ sich danach aber "
                "nicht neu öffnen. Bitte das Programm neu starten und mit dem "
                "neuen Passwort anmelden."
            ) from exc
        self.replace_engine(new_engine)

    def _back_up_before_password_change(self) -> None:
        folders = [
            folder
            for folder in (config.get_backup_folder_path(), self._drive_root)
            if folder is not None
        ]
        for folder in folders:
            try:
                backup.create_backup(self._engine, folder)
                return
            except backup.BackupError:
                continue
        raise storage.StorageError(
            "Vor der Passwortänderung konnte keine Sicherung erstellt werden. "
            "Das Passwort wurde nicht geändert."
        )

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
