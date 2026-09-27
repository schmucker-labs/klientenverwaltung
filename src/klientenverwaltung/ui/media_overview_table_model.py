from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from klientenverwaltung.services.media_service import MediaOverviewEntry
from klientenverwaltung.ui.media_table_model import KIND_LABELS, format_size_bytes

COLUMN_TITLES = ("Name", "Art", "Größe", "Hinzugefügt am", "Verwendet")
USED_COLUMN = 4


def _display_name(entry: MediaOverviewEntry) -> str:
    if entry.media_id is None:
        return "Unbekannte Datei"
    if entry.file_missing:
        return f"{entry.original_filename} (Datei fehlt)"
    return entry.original_filename or ""


def _name_sort_key(entry: MediaOverviewEntry) -> str:
    return _display_name(entry).casefold()


_SORT_KEYS: dict[int, Callable[[MediaOverviewEntry], object]] = {
    0: _name_sort_key,
    1: lambda e: e.media_kind,
    2: lambda e: e.size_bytes,
    3: lambda e: e.created_at or datetime.min,
    USED_COLUMN: lambda e: (e.usage_count, _name_sort_key(e)),
}


class MediaOverviewTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._entries: list[MediaOverviewEntry] = []

    def set_entries(self, entries: list[MediaOverviewEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def entry_at(self, row: int) -> MediaOverviewEntry:
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
        if role == Qt.ItemDataRole.TextAlignmentRole and column == USED_COLUMN:
            return Qt.AlignmentFlag.AlignCenter
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if column == 0:
            return _display_name(entry)
        if column == 1:
            return KIND_LABELS[entry.media_kind]
        if column == 2:
            return format_size_bytes(entry.size_bytes)
        if column == 3:
            return entry.created_at.strftime("%d.%m.%Y %H:%M") if entry.created_at else ""
        if column == USED_COLUMN:
            return f"{entry.usage_count}×"
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
