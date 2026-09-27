import sys
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import (
    QCoreApplication,
    QEasingCurve,
    QPropertyAnimation,
    QSettings,
    QTimer,
)
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog, QSplashScreen
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from klientenverwaltung import backup, config, storage
from klientenverwaltung.services import (
    ClientService,
    MediaService,
    TreatmentSessionService,
    TreatmentTypeService,
)
from klientenverwaltung.ui.dialogs import ask_retry, ask_retry_or_setup, show_error
from klientenverwaltung.ui.icons import get_app_icon, load_pixmap
from klientenverwaltung.ui.main_window import MainWindow
from klientenverwaltung.ui.password_dialog import ask_for_password
from klientenverwaltung.ui.setup_wizard import SetupWizard
from klientenverwaltung.ui.theme import apply_theme_mode, load_theme_mode

_SPLASH_FADE_IN_MS = 700
_SPLASH_HOLD_MS = 400
_SPLASH_FADE_OUT_MS = 300


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

    With no backup folder configured (deliberately skipped in the setup
    wizard, or never set up since), nothing is backed up automatically -
    not even onto the data drive itself - except when a migration is
    about to run, which always forces a backup regardless (see below).
    MainWindow's status bar tells the user backups aren't set up in this
    case; a dialog does not interrupt every single startup for it.

    With a backup folder configured, the drive itself is used only as a
    fallback for when that folder is unreachable right now - and always
    before a migration regardless of reachability, per "vor Migrationen
    wird weiterhin immer gesichert".

    Skipped entirely (in either case) when the database hasn't changed
    since the last backup and no migration is pending - running it anyway
    would just create an identical copy.

    Returns True if the database is adequately protected (a fresh backup
    was just made, or none was needed); False if one was needed but could
    not be created anywhere - the caller decides whether that is fatal (a
    migration is about to run unprotected) or just a visible warning.
    """
    configured_folder = config.get_backup_folder_path()
    migration_pending = storage.has_pending_migrations(engine)

    if configured_folder is None:
        if not migration_pending:
            return True
        try:
            backup.create_backup(engine, drive_root)
            return True
        except backup.BackupError:
            return False

    last_backup = backup.most_recent_backup([drive_root, configured_folder])
    db_path = drive_root / storage.DB_FILENAME
    if not migration_pending and backup.is_database_unchanged_since_backup(
        db_path, last_backup
    ):
        return True

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


def _show_splash() -> QSplashScreen:
    """Shows the splash centered on whichever screen the mouse cursor is
    currently on, invisible at first so _play_splash_intro() can fade it in.
    """
    screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
    splash_pixmap = load_pixmap("splash")
    splash = QSplashScreen(screen, splash_pixmap)
    splash.setWindowOpacity(0.0)
    splash.show()
    return splash


def _play_splash_intro(splash: QSplashScreen, on_finished: Callable[[], None]) -> None:
    """Fades `splash` in, holds it, then calls `on_finished` - via
    QPropertyAnimation/QTimer only, so nothing here blocks the event loop
    or delays whatever `on_finished` goes on to do.
    """
    fade_in = QPropertyAnimation(splash, b"windowOpacity", splash)
    fade_in.setDuration(_SPLASH_FADE_IN_MS)
    fade_in.setStartValue(0.0)
    fade_in.setEndValue(1.0)
    fade_in.setEasingCurve(QEasingCurve.Type.Linear)
    fade_in.finished.connect(lambda: QTimer.singleShot(_SPLASH_HOLD_MS, on_finished))
    fade_in.start()


def _fade_out_splash(splash: QSplashScreen) -> None:
    fade_out = QPropertyAnimation(splash, b"windowOpacity", splash)
    fade_out.setDuration(_SPLASH_FADE_OUT_MS)
    fade_out.setStartValue(splash.windowOpacity())
    fade_out.setEndValue(0.0)
    fade_out.setEasingCurve(QEasingCurve.Type.Linear)
    fade_out.finished.connect(splash.close)
    fade_out.start()


def _run_startup(app: QApplication, splash: QSplashScreen) -> None:
    """Everything after the splash intro: login, startup backup,
    migrations, main window.

    Runs from inside the already-started Qt event loop (main() returned as
    soon as it kicked off the splash intro), so a cancelled login or a
    fatal startup error calls app.exit(...) instead of returning a value -
    there is no more caller left to return to.

    The splash stays fully visible - behind the password prompt and any
    other dialog shown along the way - the whole time this runs; it only
    fades out once the main window is ready, or closes immediately (no
    fade) on every early-exit path below, so it never lingers on screen
    after the process has already decided to quit.
    """
    acquired = _acquire_drive_and_engine()
    if acquired is None:
        splash.close()
        app.exit(0)
        return
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
            splash.close()
            app.exit(0)
            return
        show_error(
            "Es konnte keine automatische Sicherung erstellt werden. Bitte "
            "den Sicherungsordner in den Einstellungen prüfen.",
            title="Sicherung fehlgeschlagen",
        )

    try:
        storage.apply_migrations(engine)
    except storage.StorageError as exc:
        show_error(str(exc), title="Fehler")
        splash.close()
        app.exit(0)
        return

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    client_service = ClientService(session_factory)
    treatment_type_service = TreatmentTypeService(session_factory)
    treatment_session_service = TreatmentSessionService(session_factory)
    media_service = MediaService(session_factory, drive_root)
    media_service.cleanup_orphaned_part_files()

    window = MainWindow(
        client_service,
        treatment_type_service,
        treatment_session_service,
        media_service,
        engine=engine,
        drive_root=drive_root,
    )
    window.show()
    _fade_out_splash(splash)


def _log_and_show_crash(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: TracebackType | None,
) -> None:
    """Last-resort handler for exceptions nothing else caught.

    Without this, the default excepthook just writes to stderr - which in
    this windowed (console=False) release build goes nowhere, so the app
    appears to simply vanish with no explanation. Logs the technical
    details (exception type/message/traceback only, never anything from a
    client record) to %APPDATA%, then tells the user in plain German
    instead of dying silently. Installed as sys.excepthook at the very top
    of main(), so it also covers exceptions PySide6 routes there itself
    (an exception escaping a Qt-driven callback, e.g. the splash-timer
    callback that builds the main window).
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    log_path = config.error_log_path()
    details = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"--- {datetime.now():%Y-%m-%d %H:%M:%S} ---\n{details}\n")
    except OSError:
        pass

    app = QApplication.instance() or QApplication(sys.argv)
    show_error(
        "Es ist ein unerwarteter Fehler aufgetreten. Die Anwendung wird "
        "beendet.\n\nTechnische Details wurden gespeichert in:\n"
        f"{log_path}",
        title="Unerwarteter Fehler",
    )
    app.quit()


def main() -> int:
    sys.excepthook = _log_and_show_crash

    # Only for QSettings (window geometry, column widths, splitter sizes) -
    # never client data, which stays on the encrypted USB-Datenplatte.
    QCoreApplication.setOrganizationName("Klientenverwaltung")
    QCoreApplication.setApplicationName("Klientenverwaltung")

    if "--reset-settings" in sys.argv:
        QSettings().clear()
        # last_known_drive_path/backup_folder_path live in config.json, not
        # QSettings - also clearing it here so this flag actually puts the
        # app back into a fresh-install state, not just resetting the UI.
        config.reset()
        print("Einstellungen wurden zurückgesetzt.")

    app = QApplication(sys.argv)
    font = app.font()
    font.setPointSize(font.pointSize() + 2)
    app.setFont(font)
    app.setWindowIcon(get_app_icon())
    apply_theme_mode(load_theme_mode())

    splash = _show_splash()
    _play_splash_intro(splash, on_finished=lambda: _run_startup(app, splash))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
