from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QCheckBox, QDateEdit, QDateTimeEdit, QHBoxLayout, QWidget


class OptionalDateEdit(QWidget):
    """A date picker with a checkbox to represent "kein Datum angegeben" (None).

    initial_date is what the picker shows before any value was set - for a
    birth date a plausible past date rather than today, so neither typing
    nor the calendar starts decades away. With not_in_future, dates after
    today cannot be picked at all (the service rejects them regardless).
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        initial_date: date | None = None,
        not_in_future: bool = False,
    ) -> None:
        super().__init__(parent)

        self._checkbox = QCheckBox("angegeben", self)
        self._date_edit = QDateEdit(self)
        self._date_edit.setDisplayFormat("dd.MM.yyyy")
        self._date_edit.setCalendarPopup(True)
        if not_in_future:
            self._date_edit.setMaximumDate(QDate.currentDate())
        start = initial_date or date.today()
        self._date_edit.setDate(QDate(start.year, start.month, start.day))
        self._date_edit.setEnabled(False)

        self._checkbox.toggled.connect(self._on_toggled)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._checkbox)
        layout.addWidget(self._date_edit)

    def _on_toggled(self, checked: bool) -> None:
        self._date_edit.setEnabled(checked)
        if checked and self._checkbox.hasFocus():
            # Ticked by the user: go straight on to typing the date.
            self._date_edit.setFocus()
            self._date_edit.setCurrentSection(QDateTimeEdit.Section.DaySection)

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
