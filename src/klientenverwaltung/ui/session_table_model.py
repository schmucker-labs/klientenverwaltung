from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QFont

from klientenverwaltung.models import TreatmentSession

COLUMN_TITLES = ("Datum", "Behandlungsart", "Dauer (Min.)", "Medien", "Bericht")
MEDIA_COLUMN = 3
REPORT_COLUMN = 4
_REPORT_CHECK = "✓"  # check mark


class SessionTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._sessions: list[TreatmentSession] = []
        self._media_counts: dict[int, int] = {}

    def set_sessions(
        self, sessions: list[TreatmentSession], media_counts: dict[int, int]
    ) -> None:
        self.beginResetModel()
        self._sessions = sessions
        self._media_counts = media_counts
        self.endResetModel()

    def session_at(self, row: int) -> TreatmentSession:
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
            return session.treatment_type.name
        if column == 2:
            return str(session.duration_minutes)
        if column == MEDIA_COLUMN:
            count = self._media_counts.get(session.id, 0)
            return str(count) if count else ""
        if column == REPORT_COLUMN:
            return _REPORT_CHECK if (session.report or session.impulses) else ""
        return None
