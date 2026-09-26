import os
from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import Engine

from klientenverwaltung import backup, config, storage
from klientenverwaltung.ui.backup_table_model import BackupEntry, BackupTableModel
from klientenverwaltung.ui.dialogs import (
    ask_confirm_delete,
    ask_confirm_restore,
    show_error,
    show_info,
)
from klientenverwaltung.ui.window_settings import (
    finalize_column_widths,
    restore_geometry,
    restore_header_state,
    save_geometry,
    save_header_state,
)

_ORIGIN_CONFIGURED_FOLDER = "Sicherungsordner"
_ORIGIN_DRIVE = "Datenplatte"
_GEOMETRY_SETTINGS_KEY = "backup_management/geometry"
_HEADER_STATE_SETTINGS_KEY = "backup_management/header_state"
_FILENAME_COLUMN = 1


class BackupManagementDialog(QDialog):
    def __init__(
        self, engine: Engine, drive_root: Path, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._engine = engine
        self._drive_root = drive_root
        self.setWindowTitle("Sicherungen verwalten")
        self.setModal(True)
        # Wide enough that a full backup filename plus the other three
        # columns are readable without scrolling on first run.
        self.resize(900, 500)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        self._folder_edit = QLineEdit(self)
        configured = config.get_backup_folder_path()
        if configured is not None:
            self._folder_edit.setText(str(configured))
        self._folder_edit.editingFinished.connect(self._on_folder_edited)

        browse_button = QPushButton("Durchsuchen…", self)
        browse_button.clicked.connect(self._on_browse_clicked)

        self._folder_error_label = QLabel(self)
        self._folder_error_label.setWordWrap(True)
        # Always visible (text just switches between empty and a message)
        # so the reserved space never appears/disappears and shifts the
        # rows above it.
        self._folder_error_label.setMinimumHeight(
            self._folder_error_label.fontMetrics().height() * 2
        )

        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel("Sicherungsordner:", self))
        folder_row.addWidget(self._folder_edit, 1)
        folder_row.addWidget(browse_button)

        self._table_model = BackupTableModel()
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
        restored = restore_header_state(header, _HEADER_STATE_SETTINGS_KEY)
        if not restored:
            # Datum, Größe and Herkunft only need their content's width on
            # first run; Dateiname is the one open-ended column, so it gets
            # whatever space is left over.
            self._table_view.resizeColumnsToContents()
        finalize_column_widths(
            header, self._table_model.columnCount(), _FILENAME_COLUMN, restored
        )
        header.sectionResized.connect(self._save_header_state)
        self._table_view.selectionModel().selectionChanged.connect(
            self._update_button_states
        )

        self._restore_button = QPushButton("Wiederherstellen", self)
        self._backup_now_button = QPushButton("Jetzt sichern", self)
        self._delete_button = QPushButton("Löschen", self)
        self._open_folder_button = QPushButton("Ordner öffnen", self)
        self._restore_button.setEnabled(False)
        self._delete_button.setEnabled(False)
        self._restore_button.clicked.connect(self._on_restore_clicked)
        self._backup_now_button.clicked.connect(self._on_backup_now_clicked)
        self._delete_button.clicked.connect(self._on_delete_clicked)
        self._open_folder_button.clicked.connect(self._on_open_folder_clicked)

        button_row = QHBoxLayout()
        button_row.addWidget(self._restore_button)
        button_row.addWidget(self._backup_now_button)
        button_row.addWidget(self._delete_button)
        button_row.addWidget(self._open_folder_button)
        button_row.addStretch()

        close_button = QPushButton("Schließen", self)
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addLayout(folder_row)
        layout.addWidget(self._folder_error_label)
        layout.addWidget(self._table_view)
        layout.addLayout(button_row)
        layout.addLayout(close_row)

        self._reload_table()

    def _save_header_state(self) -> None:
        save_header_state(
            self._table_view.horizontalHeader(), _HEADER_STATE_SETTINGS_KEY
        )

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)

    def _current_folder(self) -> Path:
        return config.get_backup_folder_path() or self._drive_root

    def _reload_table(self) -> None:
        entries = [
            BackupEntry(path=path, origin=_ORIGIN_DRIVE)
            for path in backup.list_backups(self._drive_root)
        ]
        configured = config.get_backup_folder_path()
        if configured is not None:
            entries.extend(
                BackupEntry(path=path, origin=_ORIGIN_CONFIGURED_FOLDER)
                for path in backup.list_backups(configured)
            )
        entries.sort(key=lambda entry: entry.path.name, reverse=True)
        self._table_model.set_entries(entries)
        self._update_button_states()

    def _update_button_states(self) -> None:
        has_selection = self._selected_entry() is not None
        self._restore_button.setEnabled(has_selection)
        self._delete_button.setEnabled(has_selection)

    def _selected_entry(self) -> BackupEntry | None:
        rows = self._table_view.selectionModel().selectedRows()
        if len(rows) != 1:
            return None
        return self._table_model.entry_at(rows[0].row())

    def _on_browse_clicked(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Sicherungsordner wählen")
        if not chosen:
            return
        self._folder_edit.setText(chosen)
        self._apply_folder(Path(chosen))

    def _on_folder_edited(self) -> None:
        text = self._folder_edit.text().strip()
        if not text:
            return
        self._apply_folder(Path(text))

    def _apply_folder(self, path: Path) -> None:
        if not path.exists() or not path.is_dir():
            self._reject_folder(f"Der Ordner existiert nicht: {path}")
            return
        if not backup.is_writable_directory(path):
            self._reject_folder(
                f"In diesen Ordner kann nicht geschrieben werden: {path}"
            )
            return
        self._folder_error_label.setText("")
        config.set_backup_folder_path(path)
        self._reload_table()

    def _reject_folder(self, message: str) -> None:
        self._folder_error_label.setText(message)
        configured = config.get_backup_folder_path()
        self._folder_edit.setText(str(configured) if configured else "")

    def _on_backup_now_clicked(self) -> None:
        try:
            backup.create_backup(self._engine, self._current_folder())
        except backup.BackupError as exc:
            show_error(str(exc), parent=self)
            return
        self._reload_table()

    def _on_delete_clicked(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        confirmed = ask_confirm_delete(
            f"Sicherung {entry.path.name} unwiderruflich löschen?",
            title="Sicherung löschen",
            parent=self,
        )
        if not confirmed:
            return
        try:
            backup.delete_backup(entry.path)
        except backup.BackupError as exc:
            show_error(str(exc), parent=self)
            return
        self._reload_table()

    def _on_open_folder_clicked(self) -> None:
        try:
            os.startfile(self._current_folder())
        except OSError as exc:
            show_error(f"Ordner konnte nicht geöffnet werden: {exc}", parent=self)

    def _on_restore_clicked(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return

        timestamp = backup.parse_backup_timestamp(entry.path)
        label = timestamp.strftime("%d.%m.%Y %H:%M") if timestamp else entry.path.name
        confirmed = ask_confirm_restore(
            f"Die aktuelle Datenbank wird durch die Sicherung vom {label} "
            "ersetzt. Die aktuelle Datenbank wird vorher zusätzlich "
            "gesichert. Dieser Vorgang kann nicht rückgängig gemacht "
            "werden. Die Anwendung wird danach beendet und muss "
            "anschließend von Hand neu gestartet werden.",
            title="Sicherung wiederherstellen",
            parent=self,
        )
        if not confirmed:
            return

        try:
            backup.create_pre_restore_backup(self._engine, self._current_folder())
        except backup.BackupError as exc:
            show_error(
                "Die aktuelle Datenbank konnte vor der Wiederherstellung "
                f"nicht gesichert werden, die Wiederherstellung wurde "
                f"abgebrochen: {exc}",
                parent=self,
            )
            return

        db_path = self._drive_root / storage.DB_FILENAME
        self._engine.dispose()
        try:
            backup.restore_backup(entry.path, db_path)
        except backup.BackupError as exc:
            show_error(
                f"{exc}\n\nDie vorhandene Datenbank wurde nicht verändert. "
                "Bitte die Anwendung neu starten.",
                parent=self,
            )
            # done() (not a bare quit) so geometry/column widths are still
            # saved even though the app is about to exit.
            self.done(QDialog.DialogCode.Rejected)
            self._quit_application()
            return

        show_info(
            "Die Sicherung wurde wiederhergestellt. Das Programm wird jetzt "
            "beendet. Bitte starten Sie es danach von Hand neu.",
            title="Wiederherstellung erfolgreich",
            parent=self,
        )
        self.done(QDialog.DialogCode.Accepted)
        self._quit_application()

    @staticmethod
    def _quit_application() -> None:
        """Closes every window (not just quit()) so MainWindow's own
        closeEvent - geometry saving - still runs even though this exit
        was triggered from a dialog rather than the user closing the main
        window directly, then ends the application. The DB engine is
        expected to already be disposed by the caller before this runs.
        """
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.closeAllWindows()
            app.quit()
