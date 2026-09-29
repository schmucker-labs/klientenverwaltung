import sys
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

from PySide6.QtCore import (
    QCoreApplication,
    QEasingCurve,
    QLockFile,
    QPropertyAnimation,
    QSettings,
    QTimer,
)
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QDialog, QSplashScreen
from sqlalchemy import Engine

from klientenverwaltung import backup, config, crash_log, storage
from klientenverwaltung.app_context import AppServices, OpenDatabase
from klientenverwaltung.services import (
    DataUnavailableError,
    ServiceError,
)
from klientenverwaltung.ui.dialogs import (
    ask_retry,
    ask_retry_or_setup,
    ask_use_other_data_drive,
    show_error,
    show_info,
)
from klientenverwaltung.ui.icons import get_app_icon, load_pixmap
from klientenverwaltung.ui.main_window import MainWindow
from klientenverwaltung.ui.password_dialog import ask_for_password
from klientenverwaltung.ui.setup_wizard import SetupWizard
from klientenverwaltung.ui.theme import apply_theme_mode, load_theme_mode

_SPLASH_FADE_IN_MS = 700
_SPLASH_HOLD_MS = 400
_SPLASH_FADE_OUT_MS = 300
# After the splash has faded out, so the reminder never pops up behind it.
_BACKUP_REMINDER_DELAY_MS = 800


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
    # In front of the splash screen, with keyboard focus (see ask_for_password).
    wizard.show()
    wizard.raise_()
    wizard.activateWindow()
    if wizard.exec() == QDialog.DialogCode.Accepted:
        assert wizard.drive_root is not None
        assert wizard.engine is not None
        return wizard.drive_root, wizard.engine
    return None


def _acquire_drive_and_engine() -> tuple[Path, Engine] | None:
    """Finds an existing, already set-up drive and logs in, or - if none is
    found, or only the leftover of an interrupted setup - offers to run the
    setup wizard.
    """
    while True:
        try:
            drive_root = storage.find_data_drive()
        except storage.DataDriveNotFoundError as exc:
            choice = ask_retry_or_setup(str(exc), title="Datenplatte nicht gefunden")
        except storage.MultipleDataDrivesFoundError as exc:
            if not ask_retry(str(exc), title="Mehrere Datenplatten gefunden"):
                return None
            continue
        except storage.DifferentDataDriveError as exc:
            decision = ask_use_other_data_drive(str(exc))
            if decision == "cancel":
                return None
            if decision == "retry":
                continue
            storage.accept_data_drive(exc.drive_root)
            drive_root = exc.drive_root
            if storage.drive_setup_state(drive_root) is not (
                storage.DriveSetupState.INCOMPLETE
            ):
                break
            continue
        else:
            if storage.drive_setup_state(drive_root) is not (
                storage.DriveSetupState.INCOMPLETE
            ):
                break
            choice = ask_retry_or_setup(
                f"Auf dem Laufwerk {drive_root} wurde eine unvollständig "
                "eingerichtete Datenplatte gefunden: Die Kennungsdatei ist "
                "vorhanden, die Datenbank fehlt. Vermutlich wurde die Einrichtung "
                "abgebrochen. Sie kann jetzt mit „Neue Datenplatte einrichten…“ "
                "abgeschlossen werden (dabei dieses Laufwerk wählen).",
                title="Einrichtung unvollständig",
            )

        if choice == "retry":
            continue
        if choice == "setup":
            setup_result = _run_setup_wizard()
            if setup_result is not None:
                return setup_result
            continue
        return None

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
    case, and a reminder appears at most once a week.

    With a backup folder configured, the database is backed up there
    unless that folder's own newest backup already holds the current
    state - a newer fallback copy on the data drive does not count, it
    would be lost together with the drive. The drive itself is used only
    as a fallback for when the folder is unreachable right now - and
    always before a migration regardless, per "vor Migrationen wird
    weiterhin immer gesichert".

    Returns True if the database is adequately protected (a fresh backup
    was just made, or none was needed); False if one was needed but could
    not be created anywhere - the caller decides whether that is fatal (a
    migration is about to run unprotected) or just a visible warning.
    """
    configured_folder = config.get_backup_folder_path()
    migration_pending = storage.has_pending_migrations(engine)
    db_path = drive_root / storage.DB_FILENAME

    if configured_folder is None:
        if not migration_pending:
            return True
        try:
            backup.create_backup(engine, drive_root)
            return True
        except backup.BackupError:
            return False

    try:
        if migration_pending:
            backup.create_backup(engine, configured_folder)
        else:
            backup.back_up_if_changed(engine, db_path, configured_folder)
        return True
    except backup.BackupError:
        pass
    # The folder is unreachable right now: the data drive is the fallback.
    if not migration_pending and backup.is_database_unchanged_since_backup(
        db_path, backup.most_recent_backup([drive_root])
    ):
        return True
    try:
        backup.create_backup(engine, drive_root)
        return True
    except backup.BackupError:
        return False


def _run_shutdown_backup(database: OpenDatabase) -> None:
    """Backs up the day's work when the program closes.

    Without this, everything documented since the last start would exist
    only on the data drive until the next start's backup - the one medium
    that is carried around daily. Silent: the program is already closing,
    and a failure (folder unreachable, drive unplugged) is simply caught up
    on by the next start's backup.
    """
    folder = config.get_backup_folder_path()
    if database.closed or folder is None:
        return
    try:
        backup.back_up_if_changed(database.engine, database.db_path, folder)
    except backup.BackupError:
        pass


def _prepare_database(engine: Engine, drive_root: Path) -> bool:
    """Startup backup, then migrations. Returns False - after telling the
    user why - if the program must not start."""
    try:
        if not _run_startup_backup(engine, drive_root):
            if storage.has_pending_migrations(engine):
                show_error(
                    "Es konnte keine Sicherung erstellt werden (weder im "
                    "Sicherungsordner noch auf der Datenplatte). Da eine "
                    "Datenbank-Aktualisierung ansteht, wird das Programm nicht "
                    "gestartet, um die Daten nicht zu gefährden.",
                    title="Sicherung fehlgeschlagen",
                )
                return False
            show_error(
                "Es konnte keine automatische Sicherung erstellt werden. Bitte "
                "den Sicherungsordner in den Einstellungen prüfen.",
                title="Sicherung fehlgeschlagen",
            )
        storage.apply_migrations(engine)
    except storage.StorageError as exc:
        show_error(str(exc), title="Fehler")
        return False
    return True


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
    database = OpenDatabase(engine, drive_root)
    started = False

    def _on_about_to_quit() -> None:
        # Only after a complete start: a database whose startup failed
        # (e.g. a half-applied migration) must not push good backups out
        # of the rotation.
        if started:
            _run_shutdown_backup(database)
        # database.close, not engine.dispose: after a password change the
        # engine in use is a different one than the one opened here.
        database.close()

    app.aboutToQuit.connect(_on_about_to_quit)

    if not _prepare_database(engine, drive_root):
        splash.close()
        app.exit(0)
        return

    services = AppServices.for_database(database)
    services.media.cleanup_orphaned_part_files()

    window = MainWindow(services, database)
    window.show()
    started = True
    _fade_out_splash(splash)
    QTimer.singleShot(_BACKUP_REMINDER_DELAY_MS, window.remind_about_backups_if_due)


def _log_and_show_crash(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: TracebackType | None,
) -> None:
    """Last-resort handler for exceptions nothing else caught.

    Without this, the default excepthook just writes to stderr - which in
    this windowed (console=False) release build goes nowhere, so the app
    appears to simply vanish with no explanation. Logs the technical
    details to %APPDATA% - exception types and code locations only, never
    any exception message, since those can carry client data (see
    crash_log) - then tells the user in plain German instead of dying
    silently. Installed as sys.excepthook at the very top of main(), so it
    also covers exceptions PySide6 routes there itself (an exception
    escaping a Qt-driven callback, e.g. the splash-timer callback that
    builds the main window).
    """
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return

    if isinstance(exc_value, ServiceError):
        # A service call no dialog caught - typically a read while the data
        # drive was unplugged. Its message is already written for the user,
        # the service rolled back, nothing is half-done: show it and keep
        # running instead of ending the program.
        show_error(
            str(exc_value),
            title=(
                "Datenplatte nicht erreichbar"
                if isinstance(exc_value, DataUnavailableError)
                else "Fehler"
            ),
        )
        return

    log_path = crash_log.write_crash_log(exc_value, exc_tb)

    app = QApplication.instance() or QApplication(sys.argv)
    show_error(
        "Es ist ein unerwarteter Fehler aufgetreten. Die Anwendung wird "
        "beendet.\n\nTechnische Details wurden gespeichert in:\n"
        f"{log_path}",
        title="Unerwarteter Fehler",
    )
    app.quit()


def _acquire_single_instance_lock(lock_path: Path) -> QLockFile | None:
    """The lock that keeps a second copy of the program from running, or
    None if another instance holds it.

    Two instances on the same database (easily started by a second double
    click while the splash is showing) would each show stale lists,
    overwrite each other's edits and block a restore. Time-based staleness
    is disabled because the lock is held for the whole run; a lock left by
    a crashed instance is still recognized through its process id.
    """
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return QLockFile(str(lock_path))  # cannot lock at all: do not block starting
    lock = QLockFile(str(lock_path))
    lock.setStaleLockTime(0)
    return lock if lock.tryLock(100) else None


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

    # Held (referenced) until the process ends.
    instance_lock = _acquire_single_instance_lock(config.instance_lock_path())
    if instance_lock is None:
        show_info(
            "Die Klientenverwaltung läuft bereits. Bitte das schon geöffnete "
            "Fenster verwenden (zum Beispiel über die Taskleiste).",
            title="Programm läuft bereits",
        )
        return 0

    splash = _show_splash()
    _play_splash_intro(splash, on_finished=lambda: _run_startup(app, splash))

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
