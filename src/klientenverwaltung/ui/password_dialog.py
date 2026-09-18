from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry

_GEOMETRY_SETTINGS_KEY = "password/geometry"


class PasswordDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Passwort eingeben")
        self.setModal(True)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        label = QLabel("Bitte Passwort für die Datenplatte eingeben:", self)

        self._password_edit = QLineEdit(self)
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_edit.setMinimumWidth(280)

        button_box = QDialogButtonBox(self)
        ok_button = button_box.addButton("OK", QDialogButtonBox.ButtonRole.AcceptRole)
        button_box.addButton("Abbrechen", QDialogButtonBox.ButtonRole.RejectRole)
        ok_button.setDefault(True)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(label)
        layout.addWidget(self._password_edit)
        layout.addWidget(button_box)

        self._password_edit.setFocus()

    def password(self) -> str:
        return self._password_edit.text()

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)


def ask_for_password(parent: QWidget | None = None) -> str | None:
    """Shows the password dialog; returns None if the user cancelled."""
    dialog = PasswordDialog(parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.password()
    return None
