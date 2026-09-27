from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QSizePolicy, QTextEdit, QWidget

MIN_VISIBLE_LINES = 8


class GrowingTextEdit(QTextEdit):
    """A QTextEdit with no scrollbar of its own: it grows vertically to fit
    its content - never below MIN_VISIBLE_LINES worth of height - so only
    an enclosing QScrollArea ever scrolls.

    Shared by the Bericht editor (Auftrag A2, which subclasses this to add
    editing-specific behavior - see report_dialog._GrowingTextEdit) and the
    read-only Berichtsverlauf (Auftrag B2, used as-is with setReadOnly(True)).
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        min_visible_lines: int = MIN_VISIBLE_LINES,
    ) -> None:
        super().__init__(parent)
        self._min_visible_lines = min_visible_lines
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.document().documentLayout().documentSizeChanged.connect(
            self._update_height
        )
        self._update_height()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        # A width change re-wraps the text, which changes its height too -
        # documentSizeChanged alone does not reliably fire for that.
        self._update_height()

    def _update_height(self, *_args: object) -> None:
        margins = self.contentsMargins()
        frame = 2 * self.frameWidth()
        extra = (
            2 * self.document().documentMargin()
            + margins.top()
            + margins.bottom()
            + frame
        )
        min_height = self.fontMetrics().lineSpacing() * self._min_visible_lines + extra
        content_height = self.document().size().height() + extra
        self.setFixedHeight(int(max(min_height, content_height)))
