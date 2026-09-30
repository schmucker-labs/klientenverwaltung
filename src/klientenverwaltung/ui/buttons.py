"""Buttons and button rows built the same way in every window (docs/ui-regeln.md).

The size of a button comes from the theme (32 px tall, at least 96 px wide);
this module fixes where buttons go:

- action_row(): the row under a table - on the left what needs no selection
  (creating something first, with a plus), on the right what acts on the
  selected row, "Löschen" last.
- window_row(): the window's own buttons in the bottom right corner -
  "Schließen", or "Speichern" and "Schließen"/"Abbrechen".
"""

from collections.abc import Sequence

from PySide6.QtCore import QEvent, QSize
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from klientenverwaltung.ui.icons import get_icon
from klientenverwaltung.ui.theme import current_palette

_PLUS_ICON_SIZE = 14


class CreateButton(QPushButton):
    """A button that creates something new ("Neuer Klient", "Neue Sitzung"):
    a plus in front of its text, in the active theme's text color."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setIconSize(QSize(_PLUS_ICON_SIZE, _PLUS_ICON_SIZE))
        self._tint_icon()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        # A theme switch re-applies the style sheet to every widget - the
        # main window's button is on screen while that happens.
        if event.type() == QEvent.Type.StyleChange:
            self._tint_icon()

    def _tint_icon(self) -> None:
        self.setIcon(get_icon("plus", current_palette().text, _PLUS_ICON_SIZE))


class ToolbarButton(QPushButton):
    """An icon-only button next to another control (e.g. bold/italic/
    underline beside the report window's style box): a square exactly as
    tall as that control.

    The size is a size hint rather than setFixedSize(): the theme's rule
    for these buttons (QPushButton[toolbarButton="true"], which undoes a
    dialog button's padding and minimum size) resets a widget's fixed
    minimum whenever the style is applied.
    """

    def __init__(self, beside: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._beside = beside
        self.setProperty("toolbarButton", True)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        side = self._beside.sizeHint().height()
        return QSize(side, side)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()


class ButtonRow(QWidget):
    """Buttons on the left and on the right of one row, which is never
    narrower than all of them need.

    A widget rather than a bare layout for that last part: the theme's
    minimum button width is, to Qt, a button's whole minimum - a layout
    would squeeze longer labels down to it and cut them off before it made
    the window any wider.
    """

    def __init__(
        self,
        left: Sequence[QPushButton] = (),
        right: Sequence[QPushButton] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for button in left:
            layout.addWidget(button)
        layout.addStretch()
        for button in right:
            layout.addWidget(button)

    def minimumSizeHint(self) -> QSize:
        layout = self.layout()
        return QSize(layout.sizeHint().width(), layout.minimumSize().height())


def action_row(
    *,
    independent: Sequence[QPushButton] = (),
    on_selection: Sequence[QPushButton] = (),
) -> ButtonRow:
    """The row under a table. `independent`: what works without a selected
    row, creating something first. `on_selection`: what acts on the selected
    row, in the order open/view, edit, archive/deactivate, delete."""
    return ButtonRow(left=independent, right=on_selection)


def window_row(*buttons: QPushButton) -> ButtonRow:
    """The window's own buttons, right-aligned in its last row."""
    return ButtonRow(right=buttons)
