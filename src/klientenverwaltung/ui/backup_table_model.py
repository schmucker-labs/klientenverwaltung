from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from klientenverwaltung.backup import parse_backup_timestamp

COLUMN_TITLES = ("Datum", "Dateiname", "Größe", "Herkunft")


@dataclass(frozen=True)
class BackupEntry:
    path: Path
    origin: str


def _format_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes} Bytes"


class BackupTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._entries: list[BackupEntry] = []

    def set_entries(self, entries: list[BackupEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def entry_at(self, row: int) -> BackupEntry:
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
            timestamp = parse_backup_timestamp(entry.path)
            return timestamp.strftime("%d.%m.%Y %H:%M") if timestamp else "unbekannt"
        if column == 1:
            return entry.path.name
        if column == 2:
            try:
                return _format_size(entry.path.stat().st_size)
            except OSError:
                return ""
        if column == 3:
            return entry.origin
        return None
