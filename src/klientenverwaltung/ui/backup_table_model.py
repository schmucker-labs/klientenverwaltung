from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from klientenverwaltung.backup import (
    BackupOrigin,
    RestorableBackup,
    parse_backup_timestamp,
)
from klientenverwaltung.ui.media_table_model import format_size_bytes

COLUMN_TITLES = ("Datum", "Dateiname", "Größe", "Herkunft")

ORIGIN_LABELS: dict[BackupOrigin, str] = {
    BackupOrigin.DATA_DRIVE: "Datenplatte",
    BackupOrigin.BACKUP_FOLDER: "Sicherungsordner",
    BackupOrigin.PRE_RESTORE_DATA_DRIVE: "Vor Wiederherstellung (Datenplatte)",
    BackupOrigin.PRE_RESTORE_BACKUP_FOLDER: "Vor Wiederherstellung (Sicherungsordner)",
}


class BackupTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._entries: list[RestorableBackup] = []

    def set_entries(self, entries: list[RestorableBackup]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def entry_at(self, row: int) -> RestorableBackup:
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
            return (
                format_size_bytes(entry.size_bytes)
                if entry.size_bytes is not None
                else ""
            )
        if column == 3:
            return ORIGIN_LABELS[entry.origin]
        return None
