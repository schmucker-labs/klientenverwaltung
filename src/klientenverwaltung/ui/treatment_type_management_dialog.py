from PySide6.QtCore import QModelIndex, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.services import (
    ServiceError,
    TreatmentTypeEntry,
    TreatmentTypeService,
)
from klientenverwaltung.ui.buttons import CreateButton, action_row, window_row
from klientenverwaltung.ui.dialogs import (
    ask_confirm_deactivate,
    ask_confirm_delete,
    show_error,
)
from klientenverwaltung.ui.table_selection import select_rows_where
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
    # The list was reloaded after a treatment type may have changed - the
    # client list behind this modal window names them (docs/ui-regeln.md).
    data_changed = Signal()

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

        self._new_button = CreateButton("Neue Behandlungsart", self)
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

        button_row = action_row(
            independent=[self._new_button],
            on_selection=[
                self._edit_button,
                self._toggle_active_button,
                self._delete_button,
            ],
        )

        close_button = QPushButton("Schließen", self)
        close_button.setDefault(True)
        close_button.clicked.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table_view)
        layout.addWidget(button_row)
        layout.addWidget(window_row(close_button))

        self._reload()

    def _selected_type(self) -> TreatmentTypeEntry | None:
        rows = self._table_view.selectionModel().selectedRows()
        if len(rows) != 1:
            return None
        return self._table_model.type_at(rows[0].row())

    def _update_button_states(self) -> None:
        treatment_type = self._selected_type()
        has_selection = treatment_type is not None
        self._edit_button.setEnabled(has_selection)
        self._toggle_active_button.setEnabled(has_selection)
        # A type used by sessions can only be deactivated (CLAUDE.md) - say
        # so up front instead of offering a delete that then fails.
        usage_count = (
            self._service.count_sessions_using(treatment_type.id)
            if treatment_type is not None
            else 0
        )
        self._delete_button.setEnabled(has_selection and usage_count == 0)
        self._delete_button.setToolTip(
            f"Wird {_session_count_phrase(usage_count)} - bitte stattdessen "
            "deaktivieren."
            if usage_count
            else ""
        )
        if treatment_type is not None:
            self._toggle_active_button.setText(
                "Aktivieren" if not treatment_type.active else "Deaktivieren"
            )
        else:
            self._toggle_active_button.setText("Deaktivieren")

    def _reload(self, select_type_id: int | None = None) -> None:
        """Reloads the list, keeping the marked treatment type marked (or
        marking select_type_id, e.g. one just created)."""
        if select_type_id is None:
            selected = self._selected_type()
            select_type_id = selected.id if selected is not None else None
        types = self._service.list_treatment_types(include_inactive=True)
        self._table_model.set_types(types)
        if select_type_id is not None:
            select_rows_where(
                self._table_view,
                lambda row: self._table_model.type_at(row).id == select_type_id,
            )
        self._update_button_states()
        self.data_changed.emit()

    def _on_new_clicked(self) -> None:
        dialog = TreatmentTypeEditDialog(
            self._service, treatment_type_id=None, parent=self
        )
        # Strg+S saves without closing: the list follows right away. The
        # new treatment type gets marked, so it can be found.
        dialog.saved.connect(
            lambda: self._reload(select_type_id=dialog.treatment_type_id)
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload(select_type_id=dialog.treatment_type_id)

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
        dialog.saved.connect(self._reload)
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
