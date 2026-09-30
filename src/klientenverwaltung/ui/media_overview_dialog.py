from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QLabel,
    QListWidget,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.services import MediaOverviewEntry, MediaService, ServiceError
from klientenverwaltung.ui.buttons import action_row, window_row
from klientenverwaltung.ui.dialogs import (
    ask_confirm_delete,
    show_error,
    summarize_names,
)
from klientenverwaltung.ui.media_overview_table_model import (
    COLUMN_TITLES,
    USED_COLUMN,
    MediaOverviewTableModel,
    display_name,
)
from klientenverwaltung.ui.media_table_model import format_size_bytes
from klientenverwaltung.ui.rename_media_dialog import RenameMediaDialog
from klientenverwaltung.ui.table_selection import select_rows_where
from klientenverwaltung.ui.window_settings import (
    finalize_column_widths,
    restore_geometry,
    restore_header_state,
    save_geometry,
    save_header_state,
)

_GEOMETRY_SETTINGS_KEY = "media_overview/geometry"
_HEADER_STATE_SETTINGS_KEY = "media_overview/header_state"
_NAME_COLUMN = 0


class MediaOverviewDialog(QDialog):
    """Medienübersicht (Auftrag C2) - every media file on the drive, its
    usage count, and detection of the two mismatch cases between the
    medien folder and the database (a missing file, an untracked file).
    """

    def __init__(
        self, media_service: MediaService, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._media_service = media_service
        self._entries: list[MediaOverviewEntry] = []

        self.setWindowTitle("Medienübersicht")
        self.setModal(True)
        self.resize(800, 560)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        self._table_model = MediaOverviewTableModel()
        self._table_view = QTableView(self)
        self._table_view.setModel(self._table_model)
        self._table_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table_view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table_view.setSortingEnabled(True)
        self._table_view.verticalHeader().setVisible(False)
        self._table_view.doubleClicked.connect(self._on_open_clicked)

        # Populated before resizeColumnsToContents() below, which otherwise
        # only has the (much shorter) column headers to measure against on
        # an empty model.
        self._entries = self._media_service.list_all_media()
        self._table_model.set_entries(self._entries)

        header = self._table_view.horizontalHeader()
        restored = restore_header_state(
            header, _HEADER_STATE_SETTINGS_KEY, COLUMN_TITLES
        )
        if not restored:
            self._table_view.resizeColumnsToContents()
            self._table_view.sortByColumn(USED_COLUMN, Qt.SortOrder.AscendingOrder)
        finalize_column_widths(
            header, self._table_model.columnCount(), _NAME_COLUMN, restored
        )
        header.sectionResized.connect(self._save_header_state)
        header.sortIndicatorChanged.connect(self._save_header_state)
        self._table_view.selectionModel().selectionChanged.connect(
            self._update_button_states
        )
        self._table_view.selectionModel().selectionChanged.connect(
            self._update_usage_panel
        )

        self._usage_heading = QLabel("Verwendet in:", self)
        usage_font = self._usage_heading.font()
        usage_font.setBold(True)
        self._usage_heading.setFont(usage_font)
        self._usage_list = QListWidget(self)
        self._usage_list.setMaximumHeight(90)
        self._usage_panel = QWidget(self)
        usage_layout = QVBoxLayout(self._usage_panel)
        usage_layout.setContentsMargins(0, 0, 0, 0)
        usage_layout.addWidget(self._usage_heading)
        usage_layout.addWidget(self._usage_list)
        self._usage_panel.setVisible(False)

        self._footer_label = QLabel(self)

        self._open_button = QPushButton("Öffnen", self)
        self._rename_button = QPushButton("Umbenennen", self)
        self._delete_button = QPushButton("Löschen", self)
        self._open_button.setEnabled(False)
        self._rename_button.setEnabled(False)
        self._delete_button.setEnabled(False)
        self._open_button.clicked.connect(self._on_open_clicked)
        self._rename_button.clicked.connect(self._on_rename_clicked)
        self._delete_button.clicked.connect(self._on_delete_clicked)
        QShortcut(QKeySequence("F2"), self, activated=self._on_rename_clicked)

        button_row = action_row(
            on_selection=[
                self._open_button,
                self._rename_button,
                self._delete_button,
            ]
        )

        close_button = QPushButton("Schließen", self)
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table_view, 1)
        layout.addWidget(self._usage_panel)
        layout.addWidget(self._footer_label)
        layout.addWidget(button_row)
        layout.addWidget(window_row(close_button))

        self._update_footer()
        self._update_button_states()
        self._update_usage_panel()

    def _save_header_state(self) -> None:
        save_header_state(
            self._table_view.horizontalHeader(),
            _HEADER_STATE_SETTINGS_KEY,
            COLUMN_TITLES,
        )

    def _apply_current_sort(self) -> None:
        header = self._table_view.horizontalHeader()
        section = header.sortIndicatorSection()
        if section >= 0:
            self._table_view.sortByColumn(section, header.sortIndicatorOrder())

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)

    def _reload(self) -> None:
        """Reloads the list, keeping the marked files marked."""
        # By stored filename: an unknown file has no media id.
        selected = {entry.stored_filename for entry in self._selected_entries()}
        self._entries = self._media_service.list_all_media()
        self._table_model.set_entries(self._entries)
        self._apply_current_sort()
        if selected:
            select_rows_where(
                self._table_view,
                lambda row: self._table_model.entry_at(row).stored_filename in selected,
            )
        self._update_footer()
        self._update_button_states()
        self._update_usage_panel()

    def _update_footer(self) -> None:
        total_size = sum(e.size_bytes for e in self._entries)
        unused = [e for e in self._entries if e.usage_count == 0]
        unused_size = sum(e.size_bytes for e in unused)
        self._footer_label.setText(
            f"{len(self._entries)} Dateien, {format_size_bytes(total_size)} insgesamt – "
            f"davon nicht verwendet: {len(unused)} Dateien, {format_size_bytes(unused_size)}"
        )

    def _selected_entries(self) -> list[MediaOverviewEntry]:
        rows = self._table_view.selectionModel().selectedRows()
        return [self._table_model.entry_at(row.row()) for row in rows]

    def _single_selected_entry(self) -> MediaOverviewEntry | None:
        entries = self._selected_entries()
        return entries[0] if len(entries) == 1 else None

    def _update_button_states(self) -> None:
        single = self._single_selected_entry()
        self._open_button.setEnabled(single is not None)
        self._rename_button.setEnabled(
            single is not None and single.media_id is not None
        )

        entries = self._selected_entries()
        if not entries:
            self._delete_button.setEnabled(False)
            self._delete_button.setToolTip("")
            return
        blocking = next((e for e in entries if e.usage_count > 0), None)
        if blocking is not None:
            self._delete_button.setEnabled(False)
            suffix = "en" if blocking.usage_count != 1 else ""
            self._delete_button.setToolTip(
                f"Wird noch in {blocking.usage_count} Sitzung{suffix} verwendet"
            )
        else:
            self._delete_button.setEnabled(True)
            self._delete_button.setToolTip("")

    def _update_usage_panel(self) -> None:
        entry = self._single_selected_entry()
        if entry is None or entry.media_id is None or entry.usage_count == 0:
            self._usage_panel.setVisible(False)
            return
        usages = self._media_service.list_usages(entry.media_id)
        self._usage_list.clear()
        for usage in usages:
            self._usage_list.addItem(
                f"{usage.client_name} – {usage.session_date.strftime('%d.%m.%Y, %H:%M')} Uhr"
            )
        self._usage_panel.setVisible(True)

    def _on_open_clicked(self) -> None:
        entry = self._single_selected_entry()
        if entry is None:
            return
        path = self._media_service.resolve_media_path_for_stored_filename(
            entry.stored_filename
        )
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

    def _on_rename_clicked(self) -> None:
        entry = self._single_selected_entry()
        if entry is None or entry.media_id is None:
            return
        dialog = RenameMediaDialog(
            self._media_service,
            entry.media_id,
            entry.original_filename or "",
            entry.usage_count,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _on_delete_clicked(self) -> None:
        entries = self._selected_entries()
        if not entries or any(e.usage_count > 0 for e in entries):
            return
        total_size = format_size_bytes(sum(entry.size_bytes for entry in entries))
        count_phrase = (
            "1 Datei wird" if len(entries) == 1 else f"{len(entries)} Dateien werden"
        )
        confirmed = ask_confirm_delete(
            f"{count_phrase} ({total_size}) endgültig von der Datenplatte gelöscht: "
            f"{summarize_names([display_name(entry) for entry in entries])}.",
            title="Mediendateien löschen",
            parent=self,
        )
        if not confirmed:
            return
        known_ids = [e.media_id for e in entries if e.media_id is not None]
        unknown_names = [e.stored_filename for e in entries if e.media_id is None]
        try:
            failures = self._media_service.delete_unused_media(known_ids)
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return
        failed_unknown = [
            name
            for name in unknown_names
            if not self._media_service.delete_unknown_file(name)
        ]
        if failures or failed_unknown:
            names = [f.original_filename for f in failures] + failed_unknown
            show_error(
                "Folgende Dateien konnten nicht gelöscht werden, vermutlich weil "
                "sie gerade geöffnet sind: " + summarize_names(names),
                parent=self,
            )
        self._reload()
