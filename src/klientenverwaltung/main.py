import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from klientenverwaltung import storage
from klientenverwaltung.services import (
    ClientService,
    TreatmentSessionService,
    TreatmentTypeService,
)
from klientenverwaltung.ui.dialogs import ask_retry, show_error
from klientenverwaltung.ui.main_window import MainWindow
from klientenverwaltung.ui.password_dialog import ask_for_password


def _find_data_drive_or_none() -> Path | None:
    while True:
        try:
            return storage.find_data_drive()
        except storage.DataDriveNotFoundError as exc:
            if not ask_retry(str(exc), title="Datenplatte nicht gefunden"):
                return None
        except storage.MultipleDataDrivesFoundError as exc:
            if not ask_retry(str(exc), title="Mehrere Datenplatten gefunden"):
                return None


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


def main() -> int:
    # Only for QSettings (window geometry, column widths, splitter sizes) -
    # never client data, which stays on the encrypted USB-Datenplatte.
    QCoreApplication.setOrganizationName("Klientenverwaltung")
    QCoreApplication.setApplicationName("Klientenverwaltung")

    app = QApplication(sys.argv)
    font = app.font()
    font.setPointSize(font.pointSize() + 2)
    app.setFont(font)

    drive_root = _find_data_drive_or_none()
    if drive_root is None:
        return 0

    engine = _open_database_or_none(drive_root / storage.DB_FILENAME)
    if engine is None:
        return 0
    app.aboutToQuit.connect(engine.dispose)

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
        client_service, treatment_type_service, treatment_session_service
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
