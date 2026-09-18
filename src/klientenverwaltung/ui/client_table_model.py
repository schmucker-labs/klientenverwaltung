from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from klientenverwaltung.services import ClientListEntry

COLUMN_TITLES = (
    "Anrede",
    "Nachname",
    "Vorname",
    "Ort",
    "Telefon",
    "Letzte Sitzung",
    "Nächster Termin",
)


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
        return COLUMN_TITLES[section]

    def data(
        self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if not index.isValid() or role != Qt.ItemDataRole.DisplayRole:
            return None
        entry = self._entries[index.row()]
        column = index.column()
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
            return (
                entry.next_appointment_date.strftime("%d.%m.%Y")
                if entry.next_appointment_date
                else ""
            )
        return None
