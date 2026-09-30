from datetime import datetime

from PySide6.QtCore import QDateTime
from PySide6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.services import (
    ServiceError,
    SessionEntry,
    TreatmentSessionService,
    TreatmentTypeService,
)
from klientenverwaltung.services.treatment_session_service import (
    MAX_SESSION_DURATION_MINUTES,
)
from klientenverwaltung.ui.dialogs import ask_save_discard_cancel, show_error
from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry

_DEFAULT_DURATION_MINUTES = 60
_MIN_DURATION_MINUTES = 5
_GEOMETRY_SETTINGS_KEY = "session_dialog/geometry"


def _default_start_time() -> datetime:
    """ "Now", rounded down to the quarter hour - sessions usually start on
    one, and the value then carries no seconds the HH:mm display would
    hide (the service stores whole minutes regardless)."""
    now = datetime.now()
    return now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)


class SessionDialog(QDialog):
    def __init__(
        self,
        treatment_type_service: TreatmentTypeService,
        treatment_session_service: TreatmentSessionService,
        client_id: int,
        session: SessionEntry | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._treatment_type_service = treatment_type_service
        self._treatment_session_service = treatment_session_service
        self._client_id = client_id
        self._session_id = session.id if session is not None else None

        self.setWindowTitle(
            "Sitzung bearbeiten" if session is not None else "Neue Sitzung"
        )
        self.setModal(True)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        self._date_edit = QDateTimeEdit(self)
        self._date_edit.setDisplayFormat("dd.MM.yyyy HH:mm")
        self._date_edit.setCalendarPopup(True)

        self._treatment_type_combo = QComboBox(self)
        current_treatment_type_id = (
            session.treatment_type_id if session is not None else None
        )
        for treatment_type in treatment_type_service.list_selectable_for_session(
            current_treatment_type_id=current_treatment_type_id
        ):
            self._treatment_type_combo.addItem(treatment_type.name, treatment_type.id)

        self._duration_spinbox = QSpinBox(self)
        self._duration_spinbox.setRange(
            _MIN_DURATION_MINUTES, MAX_SESSION_DURATION_MINUTES
        )
        self._duration_spinbox.setValue(_DEFAULT_DURATION_MINUTES)
        self._duration_spinbox.setSuffix(" Min.")

        form = QFormLayout()
        form.addRow("Datum/Uhrzeit:", self._date_edit)
        form.addRow("Behandlungsart:", self._treatment_type_combo)
        form.addRow("Dauer:", self._duration_spinbox)

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

        if session is not None:
            self._date_edit.setDateTime(QDateTime(session.date))
            index = self._treatment_type_combo.findData(session.treatment_type_id)
            if index >= 0:
                self._treatment_type_combo.setCurrentIndex(index)
            self._duration_spinbox.setValue(session.duration_minutes)
        else:
            self._date_edit.setDateTime(QDateTime(_default_start_time()))

        self._original_values = self._collect_values()

    @property
    def session_id(self) -> int | None:
        """The session shown - also set once a new session was saved."""
        return self._session_id

    def _collect_values(self) -> dict[str, object]:
        return {
            "date": self._date_edit.dateTime().toPython(),
            "treatment_type_id": self._treatment_type_combo.currentData(),
            "duration_minutes": self._duration_spinbox.value(),
        }

    def _is_dirty(self) -> bool:
        return self._collect_values() != self._original_values

    def _on_save_clicked(self) -> None:
        values = self._collect_values()
        try:
            if self._session_id is None:
                treatment_session = self._treatment_session_service.create_session(
                    client_id=self._client_id,
                    treatment_type_id=values["treatment_type_id"],
                    date=values["date"],
                    duration_minutes=values["duration_minutes"],
                )
                self._session_id = treatment_session.id
            else:
                self._treatment_session_service.update_session(
                    self._session_id,
                    treatment_type_id=values["treatment_type_id"],
                    date=values["date"],
                    duration_minutes=values["duration_minutes"],
                )
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
            "Es gibt ungespeicherte Änderungen an dieser Sitzung.", parent=self
        )
        if choice == "cancel":
            return
        if choice == "discard":
            super().reject()
            return
        self._on_save_clicked()

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)
