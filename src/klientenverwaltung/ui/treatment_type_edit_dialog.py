from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.services import ServiceError, TreatmentTypeService
from klientenverwaltung.ui.dialogs import ask_save_discard_cancel, show_error


class TreatmentTypeEditDialog(QDialog):
    def __init__(
        self,
        treatment_type_service: TreatmentTypeService,
        treatment_type_id: int | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = treatment_type_service
        self._treatment_type_id = treatment_type_id
        self.setModal(True)

        self._name_edit = QLineEdit(self)
        self._description_edit = QTextEdit(self)

        form = QFormLayout()
        form.addRow("Name:", self._name_edit)
        form.addRow("Beschreibung:", self._description_edit)

        button_box = QDialogButtonBox(self)
        save_button = button_box.addButton(
            "Speichern", QDialogButtonBox.ButtonRole.AcceptRole
        )
        button_box.addButton("Abbrechen", QDialogButtonBox.ButtonRole.RejectRole)
        save_button.setDefault(True)
        button_box.accepted.connect(self._on_save_clicked)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(button_box)

        if treatment_type_id is not None:
            treatment_type = treatment_type_service.get_treatment_type(
                treatment_type_id
            )
            self._name_edit.setText(treatment_type.name)
            self._description_edit.setPlainText(treatment_type.description or "")
            self.setWindowTitle(f"Behandlungsart bearbeiten: {treatment_type.name}")
        else:
            self.setWindowTitle("Neue Behandlungsart")

        self._original_values = self._collect_values()

    def _collect_values(self) -> dict[str, object]:
        return {
            "name": self._name_edit.text().strip(),
            "description": self._description_edit.toPlainText().strip() or None,
        }

    def _is_dirty(self) -> bool:
        return self._collect_values() != self._original_values

    def _on_save_clicked(self) -> None:
        values = self._collect_values()
        try:
            if self._treatment_type_id is None:
                treatment_type = self._service.create_treatment_type(**values)
                self._treatment_type_id = treatment_type.id
            else:
                self._service.update_treatment_type(self._treatment_type_id, **values)
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return
        self._original_values = values
        self.accept()

    def reject(self) -> None:
        if not self._is_dirty():
            super().reject()
            return
        choice = ask_save_discard_cancel(
            "Es gibt ungespeicherte Änderungen an dieser Behandlungsart.", parent=self
        )
        if choice == "cancel":
            return
        if choice == "discard":
            super().reject()
            return
        self._on_save_clicked()
