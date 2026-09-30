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

from klientenverwaltung import backup, config, storage
from klientenverwaltung.app_context import OpenDatabase
from klientenverwaltung.backup import RestorableBackup
from klientenverwaltung.ui.backup_table_model import COLUMN_TITLES, BackupTableModel
from klientenverwaltung.ui.buttons import action_row, window_row
from klientenverwaltung.ui.dialogs import (
    ask_confirm_delete,
    ask_confirm_restore,
    ask_use_questionable_backup_folder,
    show_error,
    show_info,
)
from klientenverwaltung.ui.password_dialog import ask_for_password
from klientenverwaltung.ui.table_selection import select_rows_where
from klientenverwaltung.ui.window_settings import (
    finalize_column_widths,
    restore_geometry,
    restore_header_state,
    save_geometry,
    save_header_state,
)

_GEOMETRY_SETTINGS_KEY = "backup_management/geometry"
_HEADER_STATE_SETTINGS_KEY = "backup_management/header_state"
_FILENAME_COLUMN = 1


class BackupManagementDialog(QDialog):
    def __init__(self, database: OpenDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._database = database
        self._drive_root = database.drive_root
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
        restored = restore_header_state(
            header, _HEADER_STATE_SETTINGS_KEY, COLUMN_TITLES
        )
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

        button_row = action_row(
            independent=[self._backup_now_button, self._open_folder_button],
            on_selection=[self._restore_button, self._delete_button],
        )

        close_button = QPushButton("Schließen", self)
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)

        media_note = QLabel(
            "Hinweis: Sicherungen enthalten die Datenbank (Klienten, Sitzungen, "
            "Berichte), nicht die Mediendateien im Ordner „medien“ auf der "
            "Datenplatte. Diese bitte bei Bedarf selbst zusätzlich kopieren.",
            self,
        )
        media_note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(folder_row)
        layout.addWidget(self._folder_error_label)
        layout.addWidget(self._table_view)
        layout.addWidget(media_note)
        layout.addWidget(button_row)
        layout.addWidget(window_row(close_button))

        self._reload_table()

    def _save_header_state(self) -> None:
        save_header_state(
            self._table_view.horizontalHeader(),
            _HEADER_STATE_SETTINGS_KEY,
            COLUMN_TITLES,
        )

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)

    def _current_folder(self) -> Path:
        return config.get_backup_folder_path() or self._drive_root

    def _reload_table(self) -> None:
        """Reloads the list, keeping the marked backup marked."""
        selected = self._selected_entry()
        self._table_model.set_entries(
            backup.list_restorable_backups(
                self._drive_root, config.get_backup_folder_path()
            )
        )
        if selected is not None:
            select_rows_where(
                self._table_view,
                lambda row: self._table_model.entry_at(row).path == selected.path,
            )
        self._update_button_states()

    def _update_button_states(self) -> None:
        has_selection = self._selected_entry() is not None
        self._restore_button.setEnabled(has_selection)
        self._delete_button.setEnabled(has_selection)

    def _selected_entry(self) -> RestorableBackup | None:
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
        # editingFinished also fires when focus merely leaves the field.
        if path == config.get_backup_folder_path():
            return
        if not path.exists() or not path.is_dir():
            self._reject_folder(f"Der Ordner existiert nicht: {path}")
            return
        if not backup.is_writable_directory(path):
            self._reject_folder(
                f"In diesen Ordner kann nicht geschrieben werden: {path}"
            )
            return
        warning = backup.backup_folder_warning(path, self._drive_root)
        if warning is not None and not ask_use_questionable_backup_folder(
            warning, parent=self
        ):
            self._reject_folder("")
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
            backup.create_backup(self._database.engine, self._current_folder())
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
            "ersetzt. Die aktuelle Datenbank wird vorher gesichert und erscheint "
            "danach in dieser Liste mit der Herkunft „Vor Wiederherstellung“ - "
            "von dort lässt sie sich bei Bedarf zurückholen. Die Anwendung wird "
            "danach beendet und muss anschließend von Hand neu gestartet werden.",
            title="Sicherung wiederherstellen",
            parent=self,
        )
        if not confirmed:
            return

        current_password = self._database.password
        backup_password = self._verified_backup_password(entry, current_password)
        if backup_password is None:
            return

        try:
            backup.create_pre_restore_backup(
                self._database.engine, self._current_folder()
            )
        except backup.BackupError as exc:
            show_error(
                "Die aktuelle Datenbank konnte vor der Wiederherstellung "
                f"nicht gesichert werden, die Wiederherstellung wurde "
                f"abgebrochen: {exc}",
                parent=self,
            )
            return

        def _reencrypt_with_current_password(copy: Path) -> None:
            storage.rekey_database_file(copy, backup_password, current_password)

        db_path = self._database.db_path
        self._database.engine.dispose()
        try:
            backup.restore_backup(
                entry.path,
                db_path,
                prepare=(
                    None
                    if backup_password == current_password
                    else _reencrypt_with_current_password
                ),
            )
        except (backup.BackupError, storage.StorageError) as exc:
            # The live database was not touched, and a disposed engine
            # simply opens fresh connections - the program keeps working.
            show_error(
                f"{exc}\n\nDie vorhandene Datenbank wurde nicht verändert.",
                parent=self,
            )
            self._reload_table()
            return

        # The file under this run's engine was just replaced: nothing may
        # touch it again before the restart (not even a backup on exit).
        self._database.close()
        show_info(
            "Die Sicherung wurde wiederhergestellt. Das Programm wird jetzt "
            "beendet. Bitte starten Sie es danach von Hand neu.",
            title="Wiederherstellung erfolgreich",
            parent=self,
        )
        self.done(QDialog.DialogCode.Accepted)
        self._quit_application()

    def _verified_backup_password(
        self, entry: RestorableBackup, current_password: str
    ) -> str | None:
        """The password that opens entry's backup - normally the current
        one; for a backup from before a password change, the one the user
        then enters. None if it cannot be restored (message already shown)
        or the user cancelled."""
        password = current_password
        while True:
            try:
                storage.verify_database_file(entry.path, password)
            except storage.IncorrectPasswordError:
                if password != current_password:
                    show_error("Das Passwort ist falsch.", parent=self)
                password = ask_for_password(
                    self,
                    title="Passwort der Sicherung",
                    prompt=(
                        "Diese Sicherung lässt sich mit dem aktuellen Passwort nicht "
                        "öffnen - vermutlich stammt sie aus der Zeit vor einer "
                        "Passwortänderung. Bitte das damalige Passwort eingeben. "
                        "Die wiederhergestellten Daten werden dabei auf das aktuelle "
                        "Passwort umgestellt."
                    ),
                )
                if password is None:
                    return None
                continue
            except storage.StorageError as exc:
                show_error(
                    f"Diese Sicherung kann nicht wiederhergestellt werden: {exc}",
                    parent=self,
                )
                return None
            return password

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
