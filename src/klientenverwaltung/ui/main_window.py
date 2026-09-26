from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QActionGroup, QCloseEvent
from PySide6.QtWidgets import QLabel, QMainWindow, QToolButton
from sqlalchemy import Engine

from klientenverwaltung import AUTHOR, __version__, backup, config
from klientenverwaltung.services import (
    ClientService,
    TreatmentSessionService,
    TreatmentTypeService,
)
from klientenverwaltung.ui.backup_management_dialog import BackupManagementDialog
from klientenverwaltung.ui.client_list_widget import ClientListWidget
from klientenverwaltung.ui.dialogs import show_about, show_error
from klientenverwaltung.ui.icons import get_icon, load_pixmap
from klientenverwaltung.ui.theme import (
    ThemeMode,
    apply_theme_mode,
    get_palette,
    load_theme_mode,
    save_theme_mode,
)
from klientenverwaltung.ui.treatment_type_management_dialog import (
    TreatmentTypeManagementDialog,
)
from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry

_GEOMETRY_SETTINGS_KEY = "main_window/geometry"
_THEME_ICON_SIZE = 20


class MainWindow(QMainWindow):
    def __init__(
        self,
        client_service: ClientService,
        treatment_type_service: TreatmentTypeService,
        treatment_session_service: TreatmentSessionService,
        *,
        engine: Engine,
        drive_root: Path,
    ) -> None:
        super().__init__()
        self._treatment_type_service = treatment_type_service
        self._engine = engine
        self._drive_root = drive_root
        self._theme_mode = load_theme_mode()

        self.setWindowTitle("Klientenverwaltung")
        self.resize(1000, 700)
        self.setCentralWidget(
            ClientListWidget(
                client_service, treatment_type_service, treatment_session_service
            )
        )
        self._build_menu()
        self._build_status_bar()
        self._refresh_theme_controls()
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

    def _build_menu(self) -> None:
        settings_menu = self.menuBar().addMenu("Einstellungen")
        treatment_types_action = settings_menu.addAction("Behandlungsarten verwalten…")
        treatment_types_action.triggered.connect(self._open_treatment_type_dialog)

        appearance_menu = settings_menu.addMenu("Darstellung")
        appearance_group = QActionGroup(self)
        appearance_group.setExclusive(True)

        self._light_mode_action = appearance_menu.addAction("Hell")
        self._light_mode_action.setCheckable(True)
        appearance_group.addAction(self._light_mode_action)
        self._light_mode_action.triggered.connect(
            lambda: self._set_theme_mode(ThemeMode.LIGHT)
        )

        self._dark_mode_action = appearance_menu.addAction("Dunkel")
        self._dark_mode_action.setCheckable(True)
        appearance_group.addAction(self._dark_mode_action)
        self._dark_mode_action.triggered.connect(
            lambda: self._set_theme_mode(ThemeMode.DARK)
        )

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
        self._theme_toggle_button = QToolButton(self)
        self._theme_toggle_button.setAutoRaise(True)
        self._theme_toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme_toggle_button.setIconSize(QSize(_THEME_ICON_SIZE, _THEME_ICON_SIZE))
        self._theme_toggle_button.clicked.connect(self._on_theme_toggle_clicked)
        self.statusBar().addPermanentWidget(self._backup_status_label)
        self.statusBar().addPermanentWidget(self._theme_toggle_button)
        self._update_backup_status_label()

    def _set_theme_mode(self, mode: ThemeMode) -> None:
        self._theme_mode = mode
        save_theme_mode(mode)
        apply_theme_mode(mode)
        self._refresh_theme_controls()

    def _on_theme_toggle_clicked(self) -> None:
        new_mode = (
            ThemeMode.DARK if self._theme_mode is ThemeMode.LIGHT else ThemeMode.LIGHT
        )
        self._set_theme_mode(new_mode)

    def _refresh_theme_controls(self) -> None:
        is_light = self._theme_mode is ThemeMode.LIGHT
        self._light_mode_action.setChecked(is_light)
        self._dark_mode_action.setChecked(not is_light)

        palette = get_palette(self._theme_mode)
        icon_name = "sun" if is_light else "moon"
        self._theme_toggle_button.setIcon(
            get_icon(icon_name, palette.text, _THEME_ICON_SIZE)
        )
        self._theme_toggle_button.setToolTip(
            "Zu dunklem Modus wechseln" if is_light else "Zu hellem Modus wechseln"
        )

    def _update_backup_status_label(self) -> None:
        configured = config.get_backup_folder_path()
        if configured is None:
            self._backup_status_label.setText("Keine Sicherungen eingerichtet")
            return
        latest = backup.most_recent_backup([self._drive_root, configured])
        if latest is None:
            self._backup_status_label.setText("Letzte Sicherung: keine vorhanden")
            return
        timestamp = backup.parse_backup_timestamp(latest)
        if timestamp is None:
            self._backup_status_label.setText("Letzte Sicherung: unbekannt")
            return
        self._backup_status_label.setText(
            f"Letzte Sicherung: {timestamp.strftime('%d.%m.%Y %H:%M')}"
        )

    def _open_treatment_type_dialog(self) -> None:
        dialog = TreatmentTypeManagementDialog(
            self._treatment_type_service, parent=self
        )
        dialog.exec()

    def _open_about_dialog(self) -> None:
        show_about(
            "Klientenverwaltung",
            __version__,
            AUTHOR,
            load_pixmap("logo", QSize(64, 64)),
            parent=self,
        )

    def _on_backup_now_clicked(self) -> None:
        folder = config.get_backup_folder_path() or self._drive_root
        try:
            backup.create_backup(self._engine, folder)
        except backup.BackupError as exc:
            show_error(str(exc), parent=self)
            return
        self._update_backup_status_label()

    def _on_manage_backups_clicked(self) -> None:
        dialog = BackupManagementDialog(self._engine, self._drive_root, parent=self)
        dialog.exec()
        self._update_backup_status_label()

    def closeEvent(self, event: QCloseEvent) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().closeEvent(event)
