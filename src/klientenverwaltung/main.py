import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QDialog
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from klientenverwaltung import backup, config, storage
from klientenverwaltung.services import (
    ClientService,
    TreatmentSessionService,
    TreatmentTypeService,
)
from klientenverwaltung.ui.dialogs import ask_retry, ask_retry_or_setup, show_error
from klientenverwaltung.ui.main_window import MainWindow
from klientenverwaltung.ui.password_dialog import ask_for_password
from klientenverwaltung.ui.setup_wizard import SetupWizard
from klientenverwaltung.ui.theme import apply_theme_mode, load_theme_mode


def _open_database_or_none(db_path: Path) -> Engine | None:
    while True:
        password = ask_for_password()
        if password is None:
            return None
        try:
            return storage.open_database(db_path, password)
        except storage.IncorrectPasswordError as exc:
            show_error(str(exc), title="Falsches Passwort")
        except storage.StorageError as exc:
            show_error(str(exc), title="Fehler")
            return None


def _run_setup_wizard() -> tuple[Path, Engine] | None:
    wizard = SetupWizard()
    if wizard.exec() == QDialog.DialogCode.Accepted:
        assert wizard.drive_root is not None
        assert wizard.engine is not None
        return wizard.drive_root, wizard.engine
    return None


def _acquire_drive_and_engine() -> tuple[Path, Engine] | None:
    """Finds an existing, already set-up drive and logs in, or - if none is
    found - offers to run the first-run setup wizard on a fresh drive.
    """
    while True:
        try:
            drive_root = storage.find_data_drive()
        except storage.DataDriveNotFoundError as exc:
            choice = ask_retry_or_setup(str(exc), title="Datenplatte nicht gefunden")
            if choice == "retry":
                continue
            if choice == "setup":
                setup_result = _run_setup_wizard()
                if setup_result is not None:
                    return setup_result
                continue
            return None
        except storage.MultipleDataDrivesFoundError as exc:
            if not ask_retry(str(exc), title="Mehrere Datenplatten gefunden"):
                return None
            continue

        engine = _open_database_or_none(drive_root / storage.DB_FILENAME)
        if engine is None:
            return None
        return drive_root, engine


def _run_startup_backup(engine: Engine, drive_root: Path) -> bool:
    """The automatic startup backup.

    Skipped when the database hasn't changed since the last backup and no
    migration is pending - running it anyway would just create an
    identical copy. A pending migration always forces a fresh backup
    regardless, per "vor Migrationen wird weiterhin immer gesichert".

    Returns True if the database is adequately protected (a fresh backup
    was just made, or none was needed); False if one was needed but could
    not be created anywhere - the caller decides whether that is fatal (a
    migration is about to run unprotected) or just a visible warning.
    """
    configured_folder = config.get_backup_folder_path()
    check_folders = [drive_root, *([configured_folder] if configured_folder else [])]
    last_backup = backup.most_recent_backup(check_folders)

    migration_pending = storage.has_pending_migrations(engine)
    db_path = drive_root / storage.DB_FILENAME
    if not migration_pending and backup.is_database_unchanged_since_backup(
        db_path, last_backup
    ):
        return True

    if configured_folder is not None:
        try:
            backup.create_backup(engine, configured_folder)
            return True
        except backup.BackupError:
            pass
    try:
        backup.create_backup(engine, drive_root)
        return True
    except backup.BackupError:
        return False


def main() -> int:
    # Only for QSettings (window geometry, column widths, splitter sizes) -
    # never client data, which stays on the encrypted USB-Datenplatte.
    QCoreApplication.setOrganizationName("Klientenverwaltung")
    QCoreApplication.setApplicationName("Klientenverwaltung")

    app = QApplication(sys.argv)
    font = app.font()
    font.setPointSize(font.pointSize() + 2)
    app.setFont(font)
    apply_theme_mode(load_theme_mode())

    acquired = _acquire_drive_and_engine()
    if acquired is None:
        return 0
    drive_root, engine = acquired
    app.aboutToQuit.connect(engine.dispose)

    if not _run_startup_backup(engine, drive_root):
        if storage.has_pending_migrations(engine):
            show_error(
                "Es konnte keine Sicherung erstellt werden (weder im "
                "Sicherungsordner noch auf der Datenplatte). Da eine "
                "Datenbank-Aktualisierung ansteht, wird das Programm nicht "
                "gestartet, um die Daten nicht zu gefährden.",
                title="Sicherung fehlgeschlagen",
            )
            return 0
        show_error(
            "Es konnte keine automatische Sicherung erstellt werden. Bitte "
            "den Sicherungsordner in den Einstellungen prüfen.",
            title="Sicherung fehlgeschlagen",
        )

    try:
        storage.apply_migrations(engine)
    except storage.StorageError as exc:
        show_error(str(exc), title="Fehler")
        return 0

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    client_service = ClientService(session_factory)
    treatment_type_service = TreatmentTypeService(session_factory)
    treatment_session_service = TreatmentSessionService(session_factory)

    window = MainWindow(
        client_service,
        treatment_type_service,
        treatment_session_service,
        engine=engine,
        drive_root=drive_root,
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
