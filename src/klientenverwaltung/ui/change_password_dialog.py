from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung import storage
from klientenverwaltung.app_context import OpenDatabase
from klientenverwaltung.ui.dialogs import show_error
from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry
from klientenverwaltung.ui.wrapping_checkbox import WrappingCheckBox

_GEOMETRY_SETTINGS_KEY = "change_password/geometry"


class ChangePasswordDialog(QDialog):
    """Einstellungen → Passwort ändern: re-encrypts the database with a new
    password (see OpenDatabase.change_password)."""

    def __init__(self, database: OpenDatabase, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._database = database
        self.setWindowTitle("Passwort ändern")
        self.setModal(True)
        self.setMinimumWidth(520)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        warning = QLabel(
            "Wichtig: Ohne das neue Passwort können die Daten NICHT "
            "wiederhergestellt werden. Es gibt keine Möglichkeit, ein "
            "vergessenes Passwort zurückzusetzen.",
            self,
        )
        warning.setWordWrap(True)
        bold_font = warning.font()
        bold_font.setBold(True)
        warning.setFont(bold_font)

        backup_note = QLabel(
            "Vorher wird automatisch eine Sicherung erstellt. Sicherungen von vor "
            "der Änderung bleiben mit dem bisherigen Passwort verschlüsselt - "
            "beim Wiederherstellen einer solchen Sicherung fragt das Programm "
            "danach.",
            self,
        )
        backup_note.setWordWrap(True)

        self._current_edit = self._password_edit()
        self._new_edit = self._password_edit()
        self._repeat_edit = self._password_edit()
        form = QFormLayout()
        form.addRow("Bisheriges Passwort:", self._current_edit)
        form.addRow("Neues Passwort:", self._new_edit)
        form.addRow("Neues Passwort wiederholen:", self._repeat_edit)

        self._confirm_checkbox = WrappingCheckBox(
            "Ich habe verstanden: Ohne das neue Passwort sind die Daten "
            "unwiederbringlich verloren.",
            self,
        )

        self._error_label = QLabel(self)
        self._error_label.setWordWrap(True)
        # Always present (text switches between empty and a message), so
        # nothing above it jumps when a message appears.
        self._error_label.setMinimumHeight(self._error_label.fontMetrics().height() * 2)

        button_box = QDialogButtonBox(self)
        self._change_button: QPushButton = button_box.addButton(
            "Passwort ändern", QDialogButtonBox.ButtonRole.AcceptRole
        )
        button_box.addButton("Abbrechen", QDialogButtonBox.ButtonRole.RejectRole)
        self._change_button.setDefault(True)
        button_box.accepted.connect(self._on_change_clicked)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(warning)
        layout.addLayout(form)
        layout.addWidget(backup_note)
        layout.addWidget(self._confirm_checkbox)
        layout.addWidget(self._error_label)
        layout.addWidget(button_box)

        for edit in (self._current_edit, self._new_edit, self._repeat_edit):
            edit.textChanged.connect(self._update_state)
        self._confirm_checkbox.toggled.connect(self._update_state)
        self._update_state()
        self._current_edit.setFocus()

    def _password_edit(self) -> QLineEdit:
        edit = QLineEdit(self)
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        return edit

    def _validation_message(self) -> str | None:
        new_password = self._new_edit.text()
        if not new_password and not self._repeat_edit.text():
            return None
        if len(new_password) < storage.MIN_PASSWORD_LENGTH:
            return (
                f"Das neue Passwort muss mindestens {storage.MIN_PASSWORD_LENGTH} "
                "Zeichen lang sein."
            )
        if new_password != self._repeat_edit.text():
            return "Die beiden neuen Passwörter stimmen nicht überein."
        if new_password == self._current_edit.text():
            return "Das neue Passwort muss sich vom bisherigen unterscheiden."
        return None

    def _update_state(self) -> None:
        message = self._validation_message()
        self._error_label.setText(message or "")
        self._change_button.setEnabled(
            message is None
            and bool(self._current_edit.text())
            and bool(self._new_edit.text())
            and self._confirm_checkbox.isChecked()
        )

    def _on_change_clicked(self) -> None:
        if not self._change_button.isEnabled():
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self._database.change_password(
                self._current_edit.text(), self._new_edit.text()
            )
        except storage.IncorrectPasswordError:
            self._error_label.setText("Das bisherige Passwort ist falsch.")
            self._current_edit.clear()
            self._current_edit.setFocus()
            return
        except storage.StorageError as exc:
            show_error(str(exc), parent=self)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.accept()

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)
