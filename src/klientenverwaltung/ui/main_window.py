from datetime import date, timedelta
from pathlib import Path

from PySide6.QtCore import QSettings, QSize
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent
from PySide6.QtWidgets import QDialog, QLabel, QMainWindow

from klientenverwaltung import AUTHOR, __version__, backup, config
from klientenverwaltung.app_context import AppServices, OpenDatabase
from klientenverwaltung.ui.backup_management_dialog import BackupManagementDialog
from klientenverwaltung.ui.change_password_dialog import ChangePasswordDialog
from klientenverwaltung.ui.client_list_widget import ClientListWidget
from klientenverwaltung.ui.dialogs import (
    ask_set_up_backup_folder,
    show_about,
    show_error,
    show_info,
)
from klientenverwaltung.ui.icons import load_pixmap
from klientenverwaltung.ui.media_overview_dialog import MediaOverviewDialog
from klientenverwaltung.ui.theme import (
    THEME_MODE_LABELS,
    ThemeMode,
    apply_theme_mode,
    load_theme_mode,
    save_theme_mode,
)
from klientenverwaltung.ui.theme_switcher import ThemeSwitcher
from klientenverwaltung.ui.treatment_type_management_dialog import (
    TreatmentTypeManagementDialog,
)
from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry

_GEOMETRY_SETTINGS_KEY = "main_window/geometry"
_BACKUP_REMINDER_SETTINGS_KEY = "backup/reminder_last_shown"
_BACKUP_REMINDER_INTERVAL = timedelta(days=7)


def _format_backup_time(path: Path) -> str:
    timestamp = backup.parse_backup_timestamp(path)
    return timestamp.strftime("%d.%m.%Y %H:%M") if timestamp else "unbekannt"


class MainWindow(QMainWindow):
    def __init__(self, services: AppServices, database: OpenDatabase) -> None:
        super().__init__()
        self._services = services
        self._database = database
        self._theme_mode = load_theme_mode()

        self.setWindowTitle("Klientenverwaltung")
        self.resize(1000, 700)
        self._client_list = ClientListWidget(services)
        self.setCentralWidget(self._client_list)
        self._build_menu()
        self._build_status_bar()
        self._refresh_theme_controls()
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

    def _build_menu(self) -> None:
        settings_menu = self.menuBar().addMenu("Einstellungen")
        treatment_types_action = settings_menu.addAction("Behandlungsarten verwalten…")
        treatment_types_action.triggered.connect(self._open_treatment_type_dialog)
        media_overview_action = settings_menu.addAction("Medienübersicht…")
        media_overview_action.triggered.connect(self._open_media_overview_dialog)
        change_password_action = settings_menu.addAction("Passwort ändern…")
        change_password_action.triggered.connect(self._open_change_password_dialog)

        appearance_menu = settings_menu.addMenu("Darstellung")
        appearance_group = QActionGroup(self)
        appearance_group.setExclusive(True)

        self._theme_actions: dict[ThemeMode, QAction] = {}
        for mode in ThemeMode:
            action = appearance_menu.addAction(THEME_MODE_LABELS[mode])
            action.setCheckable(True)
            appearance_group.addAction(action)
            action.triggered.connect(
                lambda _checked=False, mode=mode: self._set_theme_mode(mode)
            )
            self._theme_actions[mode] = action

        settings_menu.addSeparator()
        about_action = settings_menu.addAction("Über")
        about_action.triggered.connect(self._open_about_dialog)

        backup_menu = self.menuBar().addMenu("Sicherung")
        backup_now_action = backup_menu.addAction("Jetzt sichern")
        backup_now_action.triggered.connect(self._on_backup_now_clicked)
        backup_menu.addSeparator()
        manage_action = backup_menu.addAction("Sicherungen verwalten…")
        manage_action.triggered.connect(self._on_manage_backups_clicked)

    def _build_status_bar(self) -> None:
        self._backup_status_label = QLabel(self)
        self._theme_switcher = ThemeSwitcher(self)
        self._theme_switcher.mode_selected.connect(self._set_theme_mode)
        self.statusBar().addPermanentWidget(self._backup_status_label)
        self.statusBar().addPermanentWidget(self._theme_switcher)
        self._update_backup_status_label()

    def _set_theme_mode(self, mode: ThemeMode) -> None:
        self._theme_mode = mode
        save_theme_mode(mode)
        apply_theme_mode(mode)
        self._refresh_theme_controls()

    def _refresh_theme_controls(self) -> None:
        self._theme_actions[self._theme_mode].setChecked(True)
        self._theme_switcher.set_mode(self._theme_mode)

    def _update_backup_status_label(self) -> None:
        """Counts only backups in the configured folder: a copy on the data
        drive itself would be lost together with the drive, so it must not
        look like a real backup here."""
        configured = config.get_backup_folder_path()
        gap = backup.backup_protection_gap(configured, self._database.drive_root)
        self._backup_status_label.setToolTip(gap or "")
        if configured is None:
            on_drive = backup.most_recent_backup([self._database.drive_root])
            self._backup_status_label.setText(
                "Keine Sicherungen eingerichtet"
                if on_drive is None
                else f"Keine Sicherungen eingerichtet - Kopie nur auf der "
                f"Datenplatte: {_format_backup_time(on_drive)}"
            )
            return
        latest = backup.most_recent_backup([configured])
        text = (
            "Letzte Sicherung: keine vorhanden"
            if latest is None
            else f"Letzte Sicherung: {_format_backup_time(latest)}"
        )
        # A folder on the data drive itself (set up before the program
        # warned about that, or despite the warning) is no real backup.
        self._backup_status_label.setText(
            text if gap is None else f"{text} (nur auf der Datenplatte)"
        )

    def remind_about_backups_if_due(self) -> None:
        """At most once a week while backups would not survive losing the
        data drive (no folder set up, or one on the data drive itself) - a
        status-bar line is easy to overlook."""
        gap = backup.backup_protection_gap(
            config.get_backup_folder_path(), self._database.drive_root
        )
        if gap is None:
            return
        settings = QSettings()
        today = date.today()
        last_shown = settings.value(_BACKUP_REMINDER_SETTINGS_KEY)
        if isinstance(last_shown, str):
            try:
                if today - date.fromisoformat(last_shown) < _BACKUP_REMINDER_INTERVAL:
                    return
            except ValueError:
                pass
        settings.setValue(_BACKUP_REMINDER_SETTINGS_KEY, today.isoformat())
        if ask_set_up_backup_folder(gap, parent=self):
            self._on_manage_backups_clicked()

    def _open_treatment_type_dialog(self) -> None:
        dialog = TreatmentTypeManagementDialog(
            self._services.treatment_types, parent=self
        )
        # The list names the treatment type of each "Nächster Termin".
        dialog.data_changed.connect(self._client_list.refresh)
        dialog.exec()

    def _open_media_overview_dialog(self) -> None:
        dialog = MediaOverviewDialog(self._services.media, parent=self)
        dialog.exec()

    def _open_change_password_dialog(self) -> None:
        dialog = ChangePasswordDialog(self._database, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            show_info(
                "Das Passwort wurde geändert. Ab sofort gilt nur noch das neue "
                "Passwort.\n\nSicherungen von vor der Änderung bleiben mit dem "
                "bisherigen Passwort verschlüsselt; beim Wiederherstellen einer "
                "solchen Sicherung fragt das Programm danach.",
                title="Passwort geändert",
                parent=self,
            )
            self._update_backup_status_label()

    def _open_about_dialog(self) -> None:
        show_about(
            "Klientenverwaltung",
            __version__,
            AUTHOR,
            load_pixmap("logo", QSize(64, 64)),
            parent=self,
        )

    def _on_backup_now_clicked(self) -> None:
        configured = config.get_backup_folder_path()
        folder = configured or self._database.drive_root
        try:
            created = backup.create_backup(self._database.engine, folder)
        except backup.BackupError as exc:
            show_error(str(exc), parent=self)
            return
        self._update_backup_status_label()
        if (
            backup.backup_protection_gap(configured, self._database.drive_root)
            is not None
        ):
            show_info(
                f"Die Sicherung wurde auf der Datenplatte abgelegt:\n{created}\n\n"
                "Sie schützt damit nicht vor dem Verlust oder Defekt der "
                "Datenplatte. Bitte unter „Sicherung → Sicherungen verwalten…“ "
                "einen Sicherungsordner auf einem anderen Datenträger wählen.",
                title="Sicherung erstellt",
                parent=self,
            )
        else:
            show_info(
                f"Die Sicherung wurde erstellt:\n{created}",
                title="Sicherung erstellt",
                parent=self,
            )

    def _on_manage_backups_clicked(self) -> None:
        dialog = BackupManagementDialog(self._database, parent=self)
        dialog.exec()
        self._update_backup_status_label()

    def closeEvent(self, event: QCloseEvent) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().closeEvent(event)
