from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QFont, QPalette
from PySide6.QtWidgets import QApplication

from klientenverwaltung.models import TreatmentType

COLUMN_TITLES = ("Name", "Beschreibung", "Status")


class TreatmentTypeTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._types: list[TreatmentType] = []

    def set_types(self, types: list[TreatmentType]) -> None:
        self.beginResetModel()
        self._types = types
        self.endResetModel()

    def type_at(self, row: int) -> TreatmentType:
        return self._types[row]

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._types)

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
        treatment_type = self._types[index.row()]

        if role == Qt.ItemDataRole.FontRole and not treatment_type.active:
            font = QFont()
            font.setItalic(True)
            return font

        if role == Qt.ItemDataRole.ForegroundRole and not treatment_type.active:
            return QApplication.palette().color(
                QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text
            )

        if role != Qt.ItemDataRole.DisplayRole:
            return None
        column = index.column()
        if column == 0:
            return treatment_type.name
        if column == 1:
            return treatment_type.description or ""
        if column == 2:
            return "Aktiv" if treatment_type.active else "Inaktiv"
        return None
