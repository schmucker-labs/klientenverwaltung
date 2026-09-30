"""`klientenverwaltung.exe --self-test`: checks a build, without any user data.

A frozen build can lack things a development checkout has: a module that
only alembic/env.py or a migration imports (both are bundled as data files,
invisible to PyInstaller's analysis), a Qt plugin, an icon. Such a build
runs fine in development and fails only on the user's machine - usually
right at the first start, in front of the user.

The self test therefore runs exactly those parts against a throwaway data
drive in a temporary folder: setup (every bundled migration), reopening,
a round trip through all services, backup and verification, a password
change, and building the main window (never shown). It prints one line per
step and returns 0 if everything worked, 1 otherwise.

Nothing of the user is touched: %APPDATA% and QSettings are redirected into
the temporary folder for the duration, the data drive search never runs,
and the only records are the made-up ones created here.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from klientenverwaltung import backup, config, storage
from klientenverwaltung.app_context import AppServices, OpenDatabase
from klientenverwaltung.ui.icons import get_app_icon, load_pixmap
from klientenverwaltung.ui.main_window import MainWindow
from klientenverwaltung.ui.theme import ThemeMode, apply_theme_mode

# Deliberately with the characters that once broke the database URL.
_PASSWORD = "Selbsttest@Passwort%41"
_NEW_PASSWORD = "Selbsttest-neues-Passwort"


class _SelfTest:
    def __init__(self, root: Path) -> None:
        self._drive = root / "datenplatte"
        self._backup_folder = root / "sicherungen"
        self._database: OpenDatabase | None = None
        self._services: AppServices | None = None
        self._window: MainWindow | None = None

    def steps(self) -> list[tuple[str, Callable[[], None]]]:
        return [
            ("Qt-Oberfläche, Theme und Icons laden", self._load_ui_resources),
            ("Datenplatte einrichten (alle Migrationen)", self._set_up_drive),
            ("Datenbank erneut öffnen", self._reopen),
            ("Klient, Behandlungsart, Sitzung und Bericht", self._use_services),
            ("Sicherung erstellen und prüfen", self._back_up),
            ("Passwort ändern", self._change_password),
            ("Hauptfenster aufbauen", self._build_main_window),
        ]

    def close(self) -> None:
        if self._window is not None:
            self._window.deleteLater()
        if self._database is not None:
            self._database.close()

    def _load_ui_resources(self) -> None:
        # Light last: the main window is built in it further down.
        for mode in reversed(ThemeMode):
            apply_theme_mode(mode)
        if get_app_icon().isNull():
            raise RuntimeError("app.ico fehlt im Build")
        for name in ("logo", "splash", "sun", "dawn", "moon", "plus"):
            if load_pixmap(name).isNull():
                raise RuntimeError(f"Icon fehlt im Build: {name}.png")

    def _set_up_drive(self) -> None:
        self._drive.mkdir(parents=True)
        engine = storage.set_up_data_drive(self._drive, _PASSWORD)
        try:
            if storage.has_pending_migrations(engine):
                raise RuntimeError("nach der Einrichtung stehen noch Migrationen aus")
        finally:
            engine.dispose()

    def _reopen(self) -> None:
        engine = storage.open_database(self._drive / storage.DB_FILENAME, _PASSWORD)
        storage.apply_migrations(engine)
        self._database = OpenDatabase(engine, self._drive)
        self._services = AppServices.for_database(self._database)

    def _use_services(self) -> None:
        services = self._require_services()
        client = services.clients.create_client(
            first_name="anna", last_name="özdemir", city="Überlingen"
        )
        treatment_type = services.treatment_types.create_treatment_type(
            name="Meditation"
        )
        session = services.treatment_sessions.create_session(
            client_id=client.id,
            treatment_type_id=treatment_type.id,
            date=datetime(2026, 1, 15, 10, 0, 47),
            duration_minutes=60,
        )
        services.treatment_sessions.save_report(
            session.id, report="<p>Bericht</p>", impulses=None
        )
        found = services.clients.list_clients_with_last_session(search="ozdemir über")
        if [entry.last_name for entry in found] != ["Özdemir"]:
            raise RuntimeError("Suche findet den angelegten Klienten nicht")
        if services.treatment_sessions.count_sessions_with_content(client.id) != 1:
            raise RuntimeError("Bericht wurde nicht gespeichert")
        if services.media.list_all_media():
            raise RuntimeError("unerwartete Mediendateien")

    def _back_up(self) -> None:
        database = self._require_database()
        config.set_backup_folder_path(self._backup_folder)
        created = backup.create_backup(database.engine, self._backup_folder)
        storage.verify_database_file(created, _PASSWORD)

    def _change_password(self) -> None:
        database = self._require_database()
        database.change_password(_PASSWORD, _NEW_PASSWORD)
        if len(self._require_services().clients.list_clients()) != 1:
            raise RuntimeError("Daten nach dem Passwortwechsel nicht lesbar")

    def _build_main_window(self) -> None:
        self._window = MainWindow(self._require_services(), self._require_database())

    def _require_database(self) -> OpenDatabase:
        if self._database is None:
            raise RuntimeError("Datenbank wurde nicht geöffnet")
        return self._database

    def _require_services(self) -> AppServices:
        if self._services is None:
            raise RuntimeError("Datenbank wurde nicht geöffnet")
        return self._services


def run() -> int:
    """Runs the self test; returns the process exit code (0 = passed)."""
    root = Path(tempfile.mkdtemp(prefix="klientenverwaltung-selbsttest-"))
    appdata_before = os.environ.get("APPDATA")
    os.environ["APPDATA"] = str(root / "appdata")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(root / "qsettings")
    )
    # Referenced until the end: widgets need a live QApplication.
    app = QApplication.instance() or QApplication([])

    print("Selbsttest der Klientenverwaltung (ohne Anwenderdaten)")
    self_test = _SelfTest(root)
    passed = True
    try:
        for title, step in self_test.steps():
            try:
                step()
            except Exception:  # noqa: BLE001 - every failure is a test result
                # Only made-up data is involved here, so the full traceback
                # (unlike in the crash log) is safe to show. print(), not
                # traceback.print_exc(): the windowed release build has no
                # stdout/stderr at all, and print() then simply does nothing.
                print(f"[FEHLER] {title}")
                print(traceback.format_exc())
                passed = False
                break
            print(f"[  OK  ] {title}")
    finally:
        self_test.close()
        app.processEvents()
        QSettings.setDefaultFormat(QSettings.Format.NativeFormat)
        if appdata_before is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = appdata_before
        shutil.rmtree(root, ignore_errors=True)

    print("Selbsttest bestanden." if passed else "Selbsttest NICHT bestanden.")
    return 0 if passed else 1
