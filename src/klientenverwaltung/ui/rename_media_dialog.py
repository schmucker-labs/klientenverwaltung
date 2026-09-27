from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.services import MediaService, ServiceError
from klientenverwaltung.ui.dialogs import show_error
from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry

_GEOMETRY_SETTINGS_KEY = "rename_media/geometry"


class RenameMediaDialog(QDialog):
    """Umbenennen (Auftrag C2) - changes only Media.original_filename; the
    file on disk (stored_filename) never changes. The extension is fixed
    and shown but not editable.
    """

    def __init__(
        self,
        media_service: MediaService,
        media_id: int,
        current_name: str,
        usage_count: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._media_service = media_service
        self._media_id = media_id
        self._extension = Path(current_name).suffix
        stem = Path(current_name).stem

        self.setWindowTitle("Datei umbenennen")
        self.setModal(True)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        self._name_edit = QLineEdit(stem, self)
        self._name_edit.selectAll()

        form = QFormLayout()
        form.addRow("Name:", self._name_edit)
        form.addRow("Endung:", QLabel(self._extension, self))

        layout = QVBoxLayout(self)
        layout.addLayout(form)

        if usage_count > 1:
            hint = QLabel(
                f"Der neue Name gilt für alle {usage_count} Sitzungen, denen diese "
                "Datei zugeordnet ist.",
                self,
            )
            hint.setWordWrap(True)
            layout.addWidget(hint)

        button_box = QDialogButtonBox(self)
        save_button = button_box.addButton(
            "Speichern", QDialogButtonBox.ButtonRole.AcceptRole
        )
        button_box.addButton("Abbrechen", QDialogButtonBox.ButtonRole.RejectRole)
        save_button.setDefault(True)
        button_box.accepted.connect(self._on_save_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_save_clicked(self) -> None:
        new_name = self._name_edit.text().strip() + self._extension
        try:
            self._media_service.rename_media(self._media_id, new_name)
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return
        self.accept()

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)
