from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.services import MediaService, ServiceError
from klientenverwaltung.ui.buttons import window_row
from klientenverwaltung.ui.dialogs import show_error
from klientenverwaltung.ui.media_picker_table_model import (
    COLUMN_TITLES,
    MediaPickerTableModel,
)
from klientenverwaltung.ui.table_selection import select_rows_where
from klientenverwaltung.ui.window_settings import (
    finalize_column_widths,
    restore_geometry,
    restore_header_state,
    save_geometry,
    save_header_state,
)

_GEOMETRY_SETTINGS_KEY = "select_existing_media/geometry"
_HEADER_STATE_SETTINGS_KEY = "select_existing_media/header_state"
_SEARCH_DEBOUNCE_MS = 250
_NAME_COLUMN = 0


class SelectExistingMediaDialog(QDialog):
    """ "Aus vorhandenen Medien …" (Auftrag C2) - links files already on
    the drive to a session without copying anything. Lists every media
    file not yet linked to this particular session.
    """

    def __init__(
        self,
        media_service: MediaService,
        session_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._media_service = media_service
        self._session_id = session_id

        self.setWindowTitle("Aus vorhandenen Medien")
        self.setModal(True)
        self.resize(550, 450)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        self._search_edit = QLineEdit(self)
        self._search_edit.setPlaceholderText("Suche nach Name …")

        self._table_model = MediaPickerTableModel()
        self._table_view = QTableView(self)
        self._table_view.setModel(self._table_model)
        self._table_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table_view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table_view.verticalHeader().setVisible(False)

        self._table_model.set_entries(
            self._media_service.list_unlinked_media_for_session(session_id)
        )
        header = self._table_view.horizontalHeader()
        restored = restore_header_state(
            header, _HEADER_STATE_SETTINGS_KEY, COLUMN_TITLES
        )
        if not restored:
            self._table_view.resizeColumnsToContents()
        finalize_column_widths(
            header, self._table_model.columnCount(), _NAME_COLUMN, restored
        )
        header.sectionResized.connect(self._save_header_state)
        self._table_view.selectionModel().selectionChanged.connect(
            self._update_button_states
        )

        self._add_button = QPushButton("Hinzufügen", self)
        self._add_button.setEnabled(False)
        self._add_button.setDefault(True)
        self._add_button.clicked.connect(self._on_add_clicked)
        cancel_button = QPushButton("Abbrechen", self)
        cancel_button.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._search_edit)
        layout.addWidget(self._table_view, 1)
        layout.addWidget(window_row(self._add_button, cancel_button))

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(_SEARCH_DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._reload)
        self._search_edit.textChanged.connect(lambda _: self._debounce_timer.start())

    def _save_header_state(self) -> None:
        save_header_state(
            self._table_view.horizontalHeader(),
            _HEADER_STATE_SETTINGS_KEY,
            COLUMN_TITLES,
        )

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)

    def _reload(self) -> None:
        """Reloads the list for the search text, keeping marked files
        marked as long as they still match it."""
        selected = {
            self._table_model.entry_at(index.row()).media_id
            for index in self._table_view.selectionModel().selectedRows()
        }
        search = self._search_edit.text().strip() or None
        self._table_model.set_entries(
            self._media_service.list_unlinked_media_for_session(
                self._session_id, search=search
            )
        )
        if selected:
            select_rows_where(
                self._table_view,
                lambda row: self._table_model.entry_at(row).media_id in selected,
            )
        self._update_button_states()

    def _update_button_states(self) -> None:
        has_selection = bool(self._table_view.selectionModel().selectedRows())
        self._add_button.setEnabled(has_selection)

    def _on_add_clicked(self) -> None:
        rows = self._table_view.selectionModel().selectedRows()
        media_ids = [self._table_model.entry_at(row.row()).media_id for row in rows]
        if not media_ids:
            return
        try:
            self._media_service.link_existing_media(self._session_id, media_ids)
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return
        self.accept()
