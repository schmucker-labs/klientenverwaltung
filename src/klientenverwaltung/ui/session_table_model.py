from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QFont

from klientenverwaltung.services import SessionEntry
from klientenverwaltung.ui.sorting import german_sort_key

COLUMN_TITLES = ("Datum", "Behandlungsart", "Dauer (Min.)", "Medien", "Bericht")
DATE_COLUMN = 0
MEDIA_COLUMN = 3
REPORT_COLUMN = 4
_REPORT_CHECK = "✓"  # check mark


class SessionTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._sessions: list[SessionEntry] = []
        self._media_counts: dict[int, int] = {}

    def set_sessions(
        self, sessions: list[SessionEntry], media_counts: dict[int, int]
    ) -> None:
        self.beginResetModel()
        self._sessions = sessions
        self._media_counts = media_counts
        self.endResetModel()

    def session_at(self, row: int) -> SessionEntry:
        return self._sessions[row]

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._sessions)

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
        session = self._sessions[index.row()]
        column = index.column()

        if role == Qt.ItemDataRole.FontRole:
            if session.date > datetime.now():
                font = QFont()
                font.setBold(True)
                return font
            return None

        if role == Qt.ItemDataRole.TextAlignmentRole and column in (
            MEDIA_COLUMN,
            REPORT_COLUMN,
        ):
            return Qt.AlignmentFlag.AlignCenter

        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if column == 0:
            return session.date.strftime("%d.%m.%Y %H:%M")
        if column == 1:
            return session.treatment_type_name
        if column == 2:
            return str(session.duration_minutes)
        if column == MEDIA_COLUMN:
            count = self._media_counts.get(session.id, 0)
            return str(count) if count else ""
        if column == REPORT_COLUMN:
            return _REPORT_CHECK if (session.report or session.impulses) else ""
        return None

    def sort(
        self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
    ) -> None:
        """Sorts by any column; sessions equal in it are ordered by date.

        Unlike a plain re-sort, this moves Qt's persistent indexes along, so
        the selection stays on the same session rather than on whichever one
        lands in its row - "Löschen" must never silently point at another
        session than the one that was clicked.
        """
        if not 0 <= column < len(COLUMN_TITLES):
            return
        self.layoutAboutToBeChanged.emit()
        old_indexes = self.persistentIndexList()
        indexed_session_ids = [self._sessions[index.row()].id for index in old_indexes]
        self._sessions.sort(
            key=lambda session: (self._sort_value(session, column), session.date),
            reverse=order == Qt.SortOrder.DescendingOrder,
        )
        rows = {session.id: row for row, session in enumerate(self._sessions)}
        self.changePersistentIndexList(
            old_indexes,
            [
                self.index(rows[session_id], index.column())
                for session_id, index in zip(
                    indexed_session_ids, old_indexes, strict=True
                )
            ],
        )
        self.layoutChanged.emit()

    def _sort_value(self, session: SessionEntry, column: int) -> object:
        if column == 1:
            return german_sort_key(session.treatment_type_name)
        if column == 2:
            return session.duration_minutes
        if column == MEDIA_COLUMN:
            return self._media_counts.get(session.id, 0)
        if column == REPORT_COLUMN:
            return bool(session.report or session.impulses)
        return session.date
