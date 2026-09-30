"""Keeping a table's marked rows across a reload (docs/ui-regeln.md).

Every table model here reloads with a model reset, which drops the view's
selection - the buttons below the table would go grey and the user would
have to click the same row again. So a reload notes which entries were
marked (by their id, never by row number: rows move when the list is
re-sorted) and marks them again afterwards with select_rows_where().
"""

from collections.abc import Callable

from PySide6.QtCore import QItemSelectionModel
from PySide6.QtWidgets import QTableView


def select_rows_where(view: QTableView, matches: Callable[[int], bool]) -> None:
    """Marks every row of view's model for which matches(row) is true and
    scrolls the first of them into view. No match (e.g. the entry was just
    deleted) leaves nothing marked."""
    model = view.model()
    selection_model = view.selectionModel()
    rows = QItemSelectionModel.SelectionFlag.Rows
    first = True
    for row in range(model.rowCount()):
        if not matches(row):
            continue
        index = model.index(row, 0)
        if first:
            selection_model.setCurrentIndex(
                index, QItemSelectionModel.SelectionFlag.ClearAndSelect | rows
            )
            view.scrollTo(index)
            first = False
        else:
            selection_model.select(
                index, QItemSelectionModel.SelectionFlag.Select | rows
            )
