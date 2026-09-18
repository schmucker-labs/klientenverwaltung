from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QFont

from klientenverwaltung.models import TreatmentSession

COLUMN_TITLES = ("Datum", "Behandlungsart", "Dauer (Min.)", "Notiz")
NOTE_COLUMN = 3
_NOTE_ICON = "\U0001f441"  # eye symbol


class SessionTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._sessions: list[TreatmentSession] = []

    def set_sessions(self, sessions: list[TreatmentSession]) -> None:
        self.beginResetModel()
        self._sessions = sessions
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
        return COLUMN_TITLES[section]

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

        if role == Qt.ItemDataRole.TextAlignmentRole and column == NOTE_COLUMN:
            return Qt.AlignmentFlag.AlignCenter

        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if column == 0:
            return session.date.strftime("%d.%m.%Y %H:%M")
        if column == 1:
            return session.treatment_type.name
        if column == 2:
            return str(session.duration_minutes)
        if column == NOTE_COLUMN:
            return _NOTE_ICON if session.notes else ""
        return None
