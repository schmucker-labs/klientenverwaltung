from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from klientenverwaltung.services.media_service import MediaKind, SessionMediaEntry

COLUMN_TITLES = ("Name", "Art", "Größe", "Hinzugefügt am")
_KIND_LABELS: dict[MediaKind, str] = {
    "image": "Bild",
    "video": "Video",
    "audio": "Audio",
    "other": "Sonstige",
}


def format_size_bytes(size_bytes: int) -> str:
    """Human-readable size with a German comma decimal separator, e.g.
    "1,4 GB" - distinct from backup_table_model._format_size (MB/KB only,
    period separator), since backups stay in the low-MB range while media
    files routinely reach several GB.
    """
    for suffix, factor in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if size_bytes >= factor:
            return f"{size_bytes / factor:.1f}".replace(".", ",") + f" {suffix}"
    return f"{size_bytes} B"


class MediaTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._entries: list[SessionMediaEntry] = []

    def set_entries(self, entries: list[SessionMediaEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def entry_at(self, row: int) -> SessionMediaEntry:
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
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        column = index.column()
        if column == 0:
            return entry.original_filename
        if column == 1:
            return _KIND_LABELS[entry.media_kind]
        if column == 2:
            return format_size_bytes(entry.size_bytes)
        if column == 3:
            return entry.added_at.strftime("%d.%m.%Y %H:%M")
        return None
