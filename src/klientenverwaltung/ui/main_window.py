from pathlib import Path

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QMainWindow
from sqlalchemy import Engine

from klientenverwaltung import backup, config
from klientenverwaltung.services import (
    ClientService,
    TreatmentSessionService,
    TreatmentTypeService,
)
from klientenverwaltung.ui.backup_management_dialog import BackupManagementDialog
from klientenverwaltung.ui.client_list_widget import ClientListWidget
from klientenverwaltung.ui.dialogs import show_error
from klientenverwaltung.ui.treatment_type_management_dialog import (
    TreatmentTypeManagementDialog,
)
from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry

_GEOMETRY_SETTINGS_KEY = "main_window/geometry"


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

        self.setWindowTitle("Klientenverwaltung")
        self.resize(1000, 700)
        self.setCentralWidget(
            ClientListWidget(
                client_service, treatment_type_service, treatment_session_service
            )
        )
        self._build_menu()
        self._build_status_bar()
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

    def _build_menu(self) -> None:
        settings_menu = self.menuBar().addMenu("Einstellungen")
        treatment_types_action = settings_menu.addAction("Behandlungsarten verwalten…")
        treatment_types_action.triggered.connect(self._open_treatment_type_dialog)

        backup_menu = self.menuBar().addMenu("Sicherung")
        backup_now_action = backup_menu.addAction("Jetzt sichern")
        backup_now_action.triggered.connect(self._on_backup_now_clicked)
        backup_menu.addSeparator()
        manage_action = backup_menu.addAction("Sicherungen verwalten…")
        manage_action.triggered.connect(self._on_manage_backups_clicked)

    def _build_status_bar(self) -> None:
        self._backup_status_label = QLabel(self)
        self.statusBar().addPermanentWidget(self._backup_status_label)
        self._update_backup_status_label()

    def _update_backup_status_label(self) -> None:
        folders = [self._drive_root]
        configured = config.get_backup_folder_path()
        if configured is not None:
            folders.append(configured)
        latest = backup.most_recent_backup(folders)
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
