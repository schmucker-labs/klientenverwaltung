from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from klientenverwaltung.services.media_service import MediaPickerEntry
from klientenverwaltung.ui.media_table_model import KIND_LABELS, format_size_bytes

COLUMN_TITLES = ("Name", "Art", "Größe")


class MediaPickerTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._entries: list[MediaPickerEntry] = []

    def set_entries(self, entries: list[MediaPickerEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def entry_at(self, row: int) -> MediaPickerEntry:
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
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        entry = self._entries[index.row()]
        column = index.column()
        if column == 0:
            return entry.original_filename
        if column == 1:
            return KIND_LABELS[entry.media_kind]
        if column == 2:
            return format_size_bytes(entry.size_bytes)
        return None
