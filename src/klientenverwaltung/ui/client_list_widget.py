from PySide6.QtCore import QModelIndex, QPoint, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.services import (
    ClientListEntry,
    ClientService,
    MediaService,
    ServiceError,
    TreatmentSessionService,
    TreatmentTypeService,
)
from klientenverwaltung.ui.client_detail_dialog import ClientDetailDialog
from klientenverwaltung.ui.client_overview_dialog import ClientOverviewDialog
from klientenverwaltung.ui.client_table_model import COLUMN_TITLES, ClientTableModel
from klientenverwaltung.ui.dialogs import ask_confirm_delete, show_error
from klientenverwaltung.ui.window_settings import (
    finalize_column_widths,
    restore_header_state,
    save_header_state,
)

SEARCH_DEBOUNCE_MS = 250
_HEADER_STATE_SETTINGS_KEY = "client_list/header_state"


class ClientListWidget(QWidget):
    def __init__(
        self,
        client_service: ClientService,
        treatment_type_service: TreatmentTypeService,
        treatment_session_service: TreatmentSessionService,
        media_service: MediaService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._client_service = client_service
        self._treatment_type_service = treatment_type_service
        self._treatment_session_service = treatment_session_service
        self._media_service = media_service

        self._search_edit = QLineEdit(self)
        self._search_edit.setPlaceholderText("Suche nach Name oder Ort …")

        self._show_archived_checkbox = QCheckBox("Archivierte anzeigen", self)

        self._table_model = ClientTableModel()
        self._table_view = QTableView(self)
        self._table_view.setModel(self._table_model)
        self._table_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table_view.setSortingEnabled(True)
        header = self._table_view.horizontalHeader()
        self._table_view.verticalHeader().setVisible(False)
        restored = restore_header_state(
            header, _HEADER_STATE_SETTINGS_KEY, COLUMN_TITLES
        )
        if not restored:
            self._table_view.setColumnWidth(0, 80)
        # Nächster Termin is the one open-ended column, so it gets whatever
        # space is left over.
        finalize_column_widths(header, self._table_model.columnCount(), 6, restored)
        header.sectionResized.connect(self._save_header_state)
        header.sortIndicatorChanged.connect(self._save_header_state)

        self._new_button = QPushButton("Neu", self)
        self._edit_button = QPushButton("Bearbeiten", self)
        self._archive_button = QPushButton("Archivieren", self)
        self._delete_button = QPushButton("Löschen", self)
        self._edit_button.setEnabled(False)
        self._archive_button.setEnabled(False)
        self._delete_button.setEnabled(False)

        search_row = QHBoxLayout()
        search_row.addWidget(self._search_edit)
        search_row.addWidget(self._show_archived_checkbox)

        button_row = QHBoxLayout()
        button_row.addWidget(self._new_button)
        button_row.addStretch()
        button_row.addWidget(self._edit_button)
        button_row.addWidget(self._archive_button)
        button_row.addWidget(self._delete_button)

        layout = QVBoxLayout(self)
        layout.addLayout(search_row)
        layout.addWidget(self._table_view)
        layout.addLayout(button_row)

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._reload)

        self._search_edit.textChanged.connect(lambda _: self._debounce_timer.start())
        self._show_archived_checkbox.stateChanged.connect(lambda _: self._reload())
        self._table_view.selectionModel().selectionChanged.connect(
            self._update_button_states
        )
        self._table_view.doubleClicked.connect(self._on_row_double_clicked)
        self._table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table_view.customContextMenuRequested.connect(self._show_context_menu)
        self._new_button.clicked.connect(self._on_new_clicked)
        self._edit_button.clicked.connect(self._on_edit_clicked)
        self._archive_button.clicked.connect(self._on_archive_clicked)
        self._delete_button.clicked.connect(self._on_delete_clicked)

        self._reload()

    def _save_header_state(self) -> None:
        save_header_state(
            self._table_view.horizontalHeader(),
            _HEADER_STATE_SETTINGS_KEY,
            COLUMN_TITLES,
        )

    def _apply_current_sort(self) -> None:
        """Re-sort after reloading entries: a model reset forgets prior sort()."""
        header = self._table_view.horizontalHeader()
        section = header.sortIndicatorSection()
        if section >= 0:
            self._table_view.sortByColumn(section, header.sortIndicatorOrder())

    def _selected_entry(self) -> ClientListEntry | None:
        rows = self._table_view.selectionModel().selectedRows()
        if len(rows) != 1:
            return None
        return self._table_model.entry_at(rows[0].row())

    def _update_button_states(self) -> None:
        entry = self._selected_entry()
        has_selection = entry is not None
        self._edit_button.setEnabled(has_selection)
        self._archive_button.setEnabled(has_selection)
        self._delete_button.setEnabled(has_selection)
        if entry is not None:
            self._archive_button.setText(
                "Wiederherstellen" if entry.archived else "Archivieren"
            )
        else:
            self._archive_button.setText("Archivieren")

    def _reload(self) -> None:
        search = self._search_edit.text().strip() or None
        entries = self._client_service.list_clients_with_last_session(
            include_archived=self._show_archived_checkbox.isChecked(), search=search
        )
        self._table_model.set_entries(entries)
        self._apply_current_sort()
        self._update_button_states()

    def _open_detail_dialog(self, client_id: int | None) -> None:
        dialog = ClientDetailDialog(
            self._client_service,
            self._treatment_type_service,
            self._treatment_session_service,
            self._media_service,
            client_id,
            parent=self,
        )
        dialog.exec()
        self._reload()

    def _on_new_clicked(self) -> None:
        self._open_detail_dialog(None)

    def _on_edit_clicked(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        self._open_detail_dialog(entry.id)

    def _open_overview_dialog(self, client_id: int) -> None:
        dialog = ClientOverviewDialog(
            self._client_service,
            self._treatment_type_service,
            self._treatment_session_service,
            self._media_service,
            client_id,
            parent=self,
        )
        dialog.exec()
        self._reload()

    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        entry = self._table_model.entry_at(index.row())
        self._open_overview_dialog(entry.id)

    def _show_context_menu(self, pos: QPoint) -> None:
        index = self._table_view.indexAt(pos)
        if not index.isValid():
            return
        self._table_view.selectRow(index.row())
        entry = self._table_model.entry_at(index.row())

        menu = QMenu(self)
        view_action = menu.addAction("Ansicht")
        edit_action = menu.addAction("Bearbeiten")
        menu.addSeparator()
        archive_action = menu.addAction(
            "Wiederherstellen" if entry.archived else "Archivieren"
        )
        delete_action = menu.addAction("Löschen")

        chosen = menu.exec(self._table_view.viewport().mapToGlobal(pos))
        if chosen is view_action:
            self._open_overview_dialog(entry.id)
        elif chosen is edit_action:
            self._open_detail_dialog(entry.id)
        elif chosen is archive_action:
            self._on_archive_clicked()
        elif chosen is delete_action:
            self._on_delete_clicked()

    def _on_archive_clicked(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        try:
            if entry.archived:
                self._client_service.unarchive_client(entry.id)
            else:
                self._client_service.archive_client(entry.id)
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return
        self._reload()

    def _on_delete_clicked(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        confirmed = ask_confirm_delete(
            f'Klient "{entry.first_name} {entry.last_name}" und alle zugehörigen '
            "Sitzungen unwiderruflich löschen?\n\nDies kann nicht rückgängig gemacht werden.",
            title="Klient löschen",
            parent=self,
        )
        if not confirmed:
            return
        try:
            self._client_service.delete_client(entry.id)
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return
        self._reload()
