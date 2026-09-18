from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QCheckBox, QDateEdit, QHBoxLayout, QWidget


class OptionalDateEdit(QWidget):
    """A date picker with a checkbox to represent "kein Datum angegeben" (None)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._checkbox = QCheckBox("angegeben", self)
        self._date_edit = QDateEdit(self)
        self._date_edit.setDisplayFormat("dd.MM.yyyy")
        self._date_edit.setCalendarPopup(True)
        self._date_edit.setDate(QDate.currentDate())
        self._date_edit.setEnabled(False)

        self._checkbox.toggled.connect(self._date_edit.setEnabled)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._checkbox)
        layout.addWidget(self._date_edit)

    def value(self) -> date | None:
        if not self._checkbox.isChecked():
            return None
        return self._date_edit.date().toPython()

    def set_value(self, value: date | None) -> None:
        if value is None:
            self._checkbox.setChecked(False)
        else:
            self._checkbox.setChecked(True)
            self._date_edit.setDate(QDate(value.year, value.month, value.day))
