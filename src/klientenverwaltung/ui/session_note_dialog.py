from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class SessionNoteDialog(QDialog):
    """Read-only popup showing a session's note.

    "Bearbeiten" accepts the dialog so the caller can open the full session
    edit dialog; "Schließen" just dismisses the popup.
    """

    def __init__(self, notes: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Notiz")
        self.setModal(True)
        self.resize(400, 300)

        self._notes_edit = QTextEdit(self)
        self._notes_edit.setPlainText(notes)
        self._notes_edit.setReadOnly(True)

        edit_button = QPushButton("Bearbeiten", self)
        edit_button.clicked.connect(self.accept)
        close_button = QPushButton("Schließen", self)
        close_button.setDefault(True)
        close_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(edit_button)
        button_row.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._notes_edit)
        layout.addLayout(button_row)
