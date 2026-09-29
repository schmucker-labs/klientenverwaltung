from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QHideEvent, QPainter, QPaintEvent, QPen, QShowEvent
from PySide6.QtWidgets import QWidget

_WIDGET_SIZE = 72
_TICK_INTERVAL_MS = 30
_OUTER_DEGREES_PER_TICK = 6
_INNER_DEGREES_PER_TICK = 8
# Degrees drawn out of 360, mirroring ui/icons/logo.svg's two arcs (dasharray
# "382 96" / circumference ~478 -> ~80%; "202 88" / circumference ~289 ->
# ~70%) - not copied exactly, close enough to read as "the same two arcs".
_OUTER_ARC_SPAN_DEGREES = 288
_INNER_ARC_SPAN_DEGREES = 252
_OUTER_PEN_WIDTH = 7
_INNER_PEN_WIDTH = 5
_OUTER_MARGIN = 4
_INNER_MARGIN = 20


class LoadingSpinnerWidget(QWidget):
    """The two half-circles from the app logo, counter-rotating - used by
    LoadingDialog while a media import runs. Colors must be set explicitly
    via set_colors() (normally the theme's accent/accent_secondary) before
    it looks right; it starts with a plausible fallback so it never paints
    literally colorless if a caller forgets.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_WIDGET_SIZE, _WIDGET_SIZE)
        self._outer_angle = 0
        self._inner_angle = 0
        self._outer_color = QColor("#A7654F")
        self._inner_color = QColor("#B89A67")
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._advance)

    def set_colors(self, outer: str, inner: str) -> None:
        self._outer_color = QColor(outer)
        self._inner_color = QColor(inner)
        self.update()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event: QHideEvent) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _advance(self) -> None:
        self._outer_angle = (self._outer_angle + _OUTER_DEGREES_PER_TICK) % 360
        self._inner_angle = (self._inner_angle - _INNER_DEGREES_PER_TICK) % 360
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        outer_pen = QPen(self._outer_color)
        outer_pen.setWidth(_OUTER_PEN_WIDTH)
        outer_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(outer_pen)
        outer_rect = self.rect().adjusted(
            _OUTER_MARGIN, _OUTER_MARGIN, -_OUTER_MARGIN, -_OUTER_MARGIN
        )
        painter.drawArc(
            outer_rect, self._outer_angle * 16, _OUTER_ARC_SPAN_DEGREES * 16
        )

        inner_pen = QPen(self._inner_color)
        inner_pen.setWidth(_INNER_PEN_WIDTH)
        inner_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(inner_pen)
        inner_rect = self.rect().adjusted(
            _INNER_MARGIN, _INNER_MARGIN, -_INNER_MARGIN, -_INNER_MARGIN
        )
        painter.drawArc(
            inner_rect, self._inner_angle * 16, _INNER_ARC_SPAN_DEGREES * 16
        )
        painter.end()
