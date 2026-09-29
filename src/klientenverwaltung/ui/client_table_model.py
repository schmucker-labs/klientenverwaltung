from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from klientenverwaltung.services import ClientListEntry, UpcomingAppointment
from klientenverwaltung.ui.sorting import german_sort_key
from klientenverwaltung.ui.theme import current_palette

COLUMN_TITLES = (
    "Anrede",
    "Nachname",
    "Vorname",
    "Ort",
    "Telefon",
    "Letzte Sitzung",
    "Nächster Termin",
)


def _format_appointment(appointment: UpcomingAppointment) -> str:
    return (
        f"{appointment.date.strftime('%d.%m.%Y %H:%M')} Uhr, "
        f"{appointment.duration_minutes} Min., {appointment.treatment_type_name}"
    )


def _format_next_appointment(appointments: list[UpcomingAppointment]) -> str:
    if not appointments:
        return ""
    text = _format_appointment(appointments[0])
    if len(appointments) > 1:
        text += f" (+{len(appointments) - 1})"
    return text


def _next_appointment_tooltip(appointments: list[UpcomingAppointment]) -> str | None:
    if not appointments:
        return None
    return "\n".join(_format_appointment(a) for a in appointments)


def _text_key(value: str | None) -> object:
    return german_sort_key(value)


def _date_key(value: datetime | None) -> tuple[bool, datetime]:
    """None-safe sort key: entries without a date sort after ones that have one."""
    return (value is None, value or datetime.min)


def _next_appointment_key(entry: ClientListEntry) -> tuple[bool, datetime]:
    appointments = entry.upcoming_appointments
    return (not appointments, appointments[0].date if appointments else datetime.min)


_SORT_KEYS: dict[int, Callable[[ClientListEntry], object]] = {
    0: lambda entry: _text_key(entry.salutation),
    1: lambda entry: _text_key(entry.last_name),
    2: lambda entry: _text_key(entry.first_name),
    3: lambda entry: _text_key(entry.city),
    4: lambda entry: _text_key(entry.phone),
    5: lambda entry: _date_key(entry.last_session_date),
    6: _next_appointment_key,
}


class ClientTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._entries: list[ClientListEntry] = []

    def set_entries(self, entries: list[ClientListEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def entry_at(self, row: int) -> ClientListEntry:
        return self._entries[row]

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._entries)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(COLUMN_TITLES)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if (
            role != Qt.ItemDataRole.DisplayRole
            or orientation != Qt.Orientation.Horizontal
        ):
            return None
        if 0 <= section < len(COLUMN_TITLES):
            return COLUMN_TITLES[section]
        return None

    def data(
        self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if not index.isValid():
            return None
        entry = self._entries[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.ToolTipRole:
            if column == 6:
                return _next_appointment_tooltip(entry.upcoming_appointments)
            return None

        if role == Qt.ItemDataRole.FontRole and entry.archived:
            font = QFont()
            font.setItalic(True)
            return font

        if role == Qt.ItemDataRole.ForegroundRole and entry.archived:
            return QColor(current_palette().text_archived)

        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if column == 0:
            return entry.salutation or ""
        if column == 1:
            return entry.last_name
        if column == 2:
            return entry.first_name
        if column == 3:
            return entry.city or ""
        if column == 4:
            return entry.phone or ""
        if column == 5:
            return (
                entry.last_session_date.strftime("%d.%m.%Y")
                if entry.last_session_date
                else ""
            )
        if column == 6:
            return _format_next_appointment(entry.upcoming_appointments)
        return None

    def sort(
        self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
    ) -> None:
        key = _SORT_KEYS.get(column)
        if key is None:
            return
        self.layoutAboutToBeChanged.emit()
        self._entries.sort(key=key, reverse=order == Qt.SortOrder.DescendingOrder)
        self.layoutChanged.emit()
