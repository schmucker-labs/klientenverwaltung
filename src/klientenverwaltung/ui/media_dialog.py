from pathlib import Path

from PySide6.QtCore import Qt, QThread, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.services import ServiceError, SessionEntry
from klientenverwaltung.services.media_service import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    ImportOutcome,
    MediaService,
    SessionMediaEntry,
)
from klientenverwaltung.ui.buttons import CreateButton, action_row, window_row
from klientenverwaltung.ui.dialogs import (
    ask_confirm_delete,
    ask_use_existing_file,
    show_error,
    show_info,
)
from klientenverwaltung.ui.loading_dialog import LoadingDialog
from klientenverwaltung.ui.media_cleanup import offer_to_delete_now_unused_media
from klientenverwaltung.ui.media_import_worker import MediaImportWorker
from klientenverwaltung.ui.media_table_model import COLUMN_TITLES, MediaTableModel
from klientenverwaltung.ui.rename_media_dialog import RenameMediaDialog
from klientenverwaltung.ui.select_existing_media_dialog import SelectExistingMediaDialog
from klientenverwaltung.ui.table_selection import select_rows_where
from klientenverwaltung.ui.window_settings import (
    finalize_column_widths,
    restore_geometry,
    restore_header_state,
    save_geometry,
    save_header_state,
)

_GEOMETRY_SETTINGS_KEY = "media_dialog/geometry"
_TABLE_HEADER_SETTINGS_KEY = "media_dialog/header_state"
_NAME_COLUMN = 0


def _build_file_filter() -> str:
    extensions = sorted(IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS)
    patterns = " ".join(f"*{ext}" for ext in extensions)
    return f"Medien ({patterns});;Alle Dateien (*)"


_FILE_FILTER = _build_file_filter()


class MediaDialog(QDialog):
    """Medien zur Sitzung (Auftrag C1) - list/attach/open/unlink files
    copied onto the data drive for one session. No in-app viewer: "Öffnen"
    always defers to Windows' own default program for the file type.
    """

    def __init__(
        self,
        media_service: MediaService,
        session: SessionEntry,
        client_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._media_service = media_service
        self._session_id = session.id
        self._thread: QThread | None = None
        self._worker: MediaImportWorker | None = None
        self._loading_dialog: LoadingDialog | None = None
        self._pending_source_path: Path | None = None
        self._importing = False

        self.setWindowTitle(f"Medien: {client_name}")
        self.setModal(True)
        self.resize(650, 450)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        heading = QLabel(
            "Medien zur Sitzung vom "
            f"{session.date.strftime('%d.%m.%Y, %H:%M')} Uhr – "
            f"{session.treatment_type_name}",
            self,
        )
        heading.setWordWrap(True)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading.setFont(heading_font)

        self._table_model = MediaTableModel()
        self._table_view = QTableView(self)
        self._table_view.setModel(self._table_model)
        self._table_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table_view.verticalHeader().setVisible(False)
        self._table_view.doubleClicked.connect(self._on_open_clicked)

        self._attach_button = CreateButton("Neue Datei …", self)
        self._select_existing_button = QPushButton("Aus vorhandenen Medien …", self)
        self._open_button = QPushButton("Öffnen", self)
        self._rename_button = QPushButton("Umbenennen", self)
        self._remove_link_button = QPushButton("Verknüpfung entfernen", self)
        self._open_button.setEnabled(False)
        self._rename_button.setEnabled(False)
        self._remove_link_button.setEnabled(False)
        self._attach_button.clicked.connect(self._on_attach_clicked)
        self._select_existing_button.clicked.connect(self._on_select_existing_clicked)
        self._open_button.clicked.connect(self._on_open_clicked)
        self._rename_button.clicked.connect(self._on_rename_clicked)
        self._remove_link_button.clicked.connect(self._on_remove_link_clicked)
        QShortcut(QKeySequence("F2"), self, activated=self._on_rename_clicked)

        button_row = action_row(
            independent=[self._attach_button, self._select_existing_button],
            on_selection=[
                self._open_button,
                self._rename_button,
                self._remove_link_button,
            ],
        )

        self._close_button = QPushButton("Schließen", self)
        self._close_button.setDefault(True)
        self._close_button.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(self._table_view, 1)
        layout.addWidget(button_row)
        layout.addWidget(window_row(self._close_button))

        self._reload_media()

        header = self._table_view.horizontalHeader()
        restored = restore_header_state(
            header, _TABLE_HEADER_SETTINGS_KEY, COLUMN_TITLES
        )
        if not restored:
            self._table_view.resizeColumnsToContents()
        finalize_column_widths(
            header, self._table_model.columnCount(), _NAME_COLUMN, restored
        )
        header.sectionResized.connect(self._save_table_header_state)
        self._table_view.selectionModel().selectionChanged.connect(
            self._update_button_states
        )

    def _save_table_header_state(self) -> None:
        save_header_state(
            self._table_view.horizontalHeader(),
            _TABLE_HEADER_SETTINGS_KEY,
            COLUMN_TITLES,
        )

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)

    def _reload_media(self, select_media_id: int | None = None) -> None:
        """Reloads the list, keeping the marked file marked (or marking
        select_media_id, e.g. a file just added)."""
        if select_media_id is None:
            selected = self._selected_entry()
            select_media_id = selected.media_id if selected is not None else None
        entries = self._media_service.list_media_for_session(self._session_id)
        self._table_model.set_entries(entries)
        if select_media_id is not None:
            select_rows_where(
                self._table_view,
                lambda row: self._table_model.entry_at(row).media_id == select_media_id,
            )
        self._update_button_states()

    def _selected_entry(self) -> SessionMediaEntry | None:
        rows = self._table_view.selectionModel().selectedRows()
        if len(rows) != 1:
            return None
        return self._table_model.entry_at(rows[0].row())

    def _update_button_states(self) -> None:
        has_selection = self._selected_entry() is not None
        self._open_button.setEnabled(has_selection and not self._importing)
        self._rename_button.setEnabled(has_selection and not self._importing)
        self._remove_link_button.setEnabled(has_selection and not self._importing)

    def _on_attach_clicked(self) -> None:
        path_str, _selected_filter = QFileDialog.getOpenFileName(
            self, "Datei anfügen", "", _FILE_FILTER
        )
        if not path_str:
            return
        self._start_import(Path(path_str))

    def _on_select_existing_clicked(self) -> None:
        dialog = SelectExistingMediaDialog(
            self._media_service, self._session_id, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload_media()

    def _on_rename_clicked(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        usage_count = self._media_service.count_sessions_for_media(entry.media_id)
        dialog = RenameMediaDialog(
            self._media_service,
            entry.media_id,
            entry.original_filename,
            usage_count,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload_media()

    def _start_import(self, source_path: Path) -> None:
        self._pending_source_path = source_path
        self._set_busy(True)
        self._loading_dialog = LoadingDialog(self)
        self._thread = QThread(self)
        self._worker = MediaImportWorker(
            self._media_service, self._session_id, source_path
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._loading_dialog.set_progress)
        # DirectConnection, deliberately: the worker thread spends the whole
        # import inside run(), so its event loop never runs and a queued
        # connection here would only ever be delivered after the copy has
        # already finished on its own - "Abbrechen" would do nothing. A
        # direct cross-thread call is safe because cancel() only sets a
        # threading.Event, which is thread-safe by design.
        self._loading_dialog.cancelled.connect(
            self._worker.cancel, Qt.ConnectionType.DirectConnection
        )
        self._worker.duplicate_found.connect(
            self._on_duplicate_found, Qt.ConnectionType.BlockingQueuedConnection
        )
        # Bound methods (not lambdas): a lambda has no receiver QObject, so
        # AutoConnection cannot resolve it to a queued connection and calls
        # it directly on the emitting (worker) thread instead - which then
        # touches this dialog's widgets, a GUI-thread QTimer and a
        # QMessageBox from off-thread. Bound methods of this QObject carry
        # a receiver context, so AutoConnection correctly queues them onto
        # the GUI thread.
        self._worker.finished.connect(self._on_import_finished)
        self._worker.failed.connect(self._on_import_failed)
        self._thread.start()

    def _on_duplicate_found(self, original_filename: str) -> None:
        answer = ask_use_existing_file(original_filename, parent=self)
        assert self._worker is not None
        self._worker.set_duplicate_answer(answer)

    def _cleanup_thread(self) -> None:
        assert self._thread is not None
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self._worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self._importing = busy
        self._attach_button.setEnabled(not busy)
        self._select_existing_button.setEnabled(not busy)
        self._close_button.setEnabled(not busy)
        self._table_view.setEnabled(not busy)
        self._update_button_states()

    def reject(self) -> None:
        if self._importing:
            return
        super().reject()

    def _on_import_finished(self, outcome: ImportOutcome) -> None:
        assert self._loading_dialog is not None
        source_path = self._pending_source_path
        self._loading_dialog.finish()
        self._cleanup_thread()
        # The file just added gets marked, so it can be found.
        self._reload_media(
            select_media_id=outcome.media.id if outcome.media is not None else None
        )
        if outcome.status == "imported":
            show_info(
                "Die Datei wurde auf die Datenplatte übernommen. Das Original "
                f"liegt weiterhin unter {source_path}. Es kann Gesundheitsdaten "
                "enthalten – bitte löschen Sie es selbst, wenn es nicht mehr "
                "gebraucht wird.",
                parent=self,
            )
        elif outcome.status == "already_linked":
            show_info("Diese Datei ist dieser Sitzung bereits zugeordnet.", parent=self)

    def _on_import_failed(self, message: str) -> None:
        assert self._loading_dialog is not None
        self._loading_dialog.finish()
        self._cleanup_thread()
        show_error(message, parent=self)

    def _on_open_clicked(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        path = self._media_service.resolve_media_path_for_entry(entry)
        if not path.exists():
            show_error(
                "Die Datei wurde auf der Datenplatte nicht gefunden.", parent=self
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            show_error(
                "Für diese Datei ist auf diesem Computer kein Programm zum "
                "Öffnen hinterlegt.",
                parent=self,
            )

    def _on_remove_link_clicked(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        confirmed = ask_confirm_delete(
            f'Verknüpfung von "{entry.original_filename}" zu dieser Sitzung '
            "entfernen? Die Datei selbst bleibt erhalten.",
            title="Verknüpfung entfernen",
            parent=self,
        )
        if not confirmed:
            return
        try:
            self._media_service.remove_link(self._session_id, entry.media_id)
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return
        offer_to_delete_now_unused_media(
            self._media_service, [entry.media_id], parent=self
        )
        self._reload_media()
