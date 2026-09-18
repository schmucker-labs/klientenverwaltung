from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow

from klientenverwaltung.services import (
    ClientService,
    TreatmentSessionService,
    TreatmentTypeService,
)
from klientenverwaltung.ui.client_list_widget import ClientListWidget
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
    ) -> None:
        super().__init__()
        self._treatment_type_service = treatment_type_service

        self.setWindowTitle("Klientenverwaltung")
        self.resize(1000, 700)
        self.setCentralWidget(
            ClientListWidget(
                client_service, treatment_type_service, treatment_session_service
            )
        )
        self._build_menu()
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

    def _build_menu(self) -> None:
        settings_menu = self.menuBar().addMenu("Einstellungen")
        treatment_types_action = settings_menu.addAction("Behandlungsarten verwalten…")
        treatment_types_action.triggered.connect(self._open_treatment_type_dialog)

    def _open_treatment_type_dialog(self) -> None:
        dialog = TreatmentTypeManagementDialog(
            self._treatment_type_service, parent=self
        )
        dialog.exec()

    def closeEvent(self, event: QCloseEvent) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().closeEvent(event)
