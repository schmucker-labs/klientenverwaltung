from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class PasswordDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Passwort eingeben")
        self.setModal(True)

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


def ask_for_password(parent: QWidget | None = None) -> str | None:
    """Shows the password dialog; returns None if the user cancelled."""
    dialog = PasswordDialog(parent)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.password()
    return None
