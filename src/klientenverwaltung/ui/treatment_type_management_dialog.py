from PySide6.QtCore import QModelIndex
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.models import TreatmentType
from klientenverwaltung.services import ServiceError, TreatmentTypeService
from klientenverwaltung.ui.dialogs import (
    ask_confirm_deactivate,
    ask_confirm_delete,
    show_error,
)
from klientenverwaltung.ui.treatment_type_edit_dialog import TreatmentTypeEditDialog
from klientenverwaltung.ui.treatment_type_table_model import (
    COLUMN_TITLES,
    TreatmentTypeTableModel,
)
from klientenverwaltung.ui.window_settings import (
    finalize_column_widths,
    restore_geometry,
    restore_header_state,
    save_geometry,
    save_header_state,
)

_GEOMETRY_SETTINGS_KEY = "treatment_type_management/geometry"
_HEADER_STATE_SETTINGS_KEY = "treatment_type_management/header_state"


def _session_count_phrase(count: int) -> str:
    if count == 0:
        return "in keiner Sitzung verwendet"
    if count == 1:
        return "in einer Sitzung verwendet"
    return f"in {count} Sitzungen verwendet"


class TreatmentTypeManagementDialog(QDialog):
    def __init__(
        self,
        treatment_type_service: TreatmentTypeService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = treatment_type_service
        self.setWindowTitle("Behandlungsarten verwalten")
        self.resize(600, 500)
        self.setModal(True)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        self._table_model = TreatmentTypeTableModel()
        self._table_view = QTableView(self)
        self._table_view.setModel(self._table_model)
        self._table_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        header = self._table_view.horizontalHeader()
        self._table_view.verticalHeader().setVisible(False)
        restored = restore_header_state(
            header, _HEADER_STATE_SETTINGS_KEY, COLUMN_TITLES
        )
        if not restored:
            self._table_view.resizeColumnsToContents()
        # Beschreibung is the one open-ended, variable-length column.
        finalize_column_widths(header, self._table_model.columnCount(), 1, restored)
        header.sectionResized.connect(self._save_header_state)
        self._table_view.selectionModel().selectionChanged.connect(
            self._update_button_states
        )
        self._table_view.doubleClicked.connect(self._on_row_double_clicked)

        self._new_button = QPushButton("Neu", self)
        self._edit_button = QPushButton("Bearbeiten", self)
        self._toggle_active_button = QPushButton("Deaktivieren", self)
        self._delete_button = QPushButton("Löschen", self)
        self._edit_button.setEnabled(False)
        self._toggle_active_button.setEnabled(False)
        self._delete_button.setEnabled(False)
        self._new_button.clicked.connect(self._on_new_clicked)
        self._edit_button.clicked.connect(self._on_edit_clicked)
        self._toggle_active_button.clicked.connect(self._on_toggle_active_clicked)
        self._delete_button.clicked.connect(self._on_delete_clicked)

        button_row = QHBoxLayout()
        button_row.addWidget(self._new_button)
        button_row.addStretch()
        button_row.addWidget(self._edit_button)
        button_row.addWidget(self._toggle_active_button)
        button_row.addWidget(self._delete_button)

        close_button = QPushButton("Schließen", self)
        close_button.clicked.connect(self.close)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table_view)
        layout.addLayout(button_row)
        layout.addLayout(close_row)

        self._reload()

    def _selected_type(self) -> TreatmentType | None:
        rows = self._table_view.selectionModel().selectedRows()
        if len(rows) != 1:
            return None
        return self._table_model.type_at(rows[0].row())

    def _update_button_states(self) -> None:
        treatment_type = self._selected_type()
        has_selection = treatment_type is not None
        self._edit_button.setEnabled(has_selection)
        self._toggle_active_button.setEnabled(has_selection)
        self._delete_button.setEnabled(has_selection)
        if treatment_type is not None:
            self._toggle_active_button.setText(
                "Aktivieren" if not treatment_type.active else "Deaktivieren"
            )
        else:
            self._toggle_active_button.setText("Deaktivieren")

    def _reload(self) -> None:
        types = self._service.list_treatment_types(include_inactive=True)
        self._table_model.set_types(types)
        self._update_button_states()

    def _on_new_clicked(self) -> None:
        dialog = TreatmentTypeEditDialog(
            self._service, treatment_type_id=None, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        if index.isValid():
            self._on_edit_clicked()

    def _on_edit_clicked(self) -> None:
        treatment_type = self._selected_type()
        if treatment_type is None:
            return
        dialog = TreatmentTypeEditDialog(
            self._service, treatment_type_id=treatment_type.id, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _on_toggle_active_clicked(self) -> None:
        treatment_type = self._selected_type()
        if treatment_type is None:
            return

        if treatment_type.active:
            usage_count = self._service.count_sessions_using(treatment_type.id)
            confirmed = ask_confirm_deactivate(
                f'Die Behandlungsart "{treatment_type.name}" wird '
                f"{_session_count_phrase(usage_count)}. Bereits erfasste Sitzungen "
                "bleiben unverändert. Trotzdem deaktivieren?",
                title="Behandlungsart deaktivieren",
                parent=self,
            )
            if not confirmed:
                return
            try:
                self._service.deactivate_treatment_type(treatment_type.id)
            except ServiceError as exc:
                show_error(str(exc), parent=self)
                return
        else:
            try:
                self._service.activate_treatment_type(treatment_type.id)
            except ServiceError as exc:
                show_error(str(exc), parent=self)
                return
        self._reload()

    def _on_delete_clicked(self) -> None:
        treatment_type = self._selected_type()
        if treatment_type is None:
            return
        confirmed = ask_confirm_delete(
            f'Behandlungsart "{treatment_type.name}" unwiderruflich löschen?',
            title="Behandlungsart löschen",
            parent=self,
        )
        if not confirmed:
            return
        try:
            self._service.delete_treatment_type(treatment_type.id)
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return
        self._reload()

    def _save_header_state(self) -> None:
        save_header_state(
            self._table_view.horizontalHeader(),
            _HEADER_STATE_SETTINGS_KEY,
            COLUMN_TITLES,
        )

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)
