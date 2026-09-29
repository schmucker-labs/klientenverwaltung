from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QWidget


class _ToggleLabel(QLabel):
    """Word-wrapping label that toggles its checkbox when clicked."""

    def __init__(self, text: str, checkbox: QCheckBox, parent: QWidget) -> None:
        super().__init__(text, parent)
        self._checkbox = checkbox
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._checkbox.toggle()
        super().mousePressEvent(event)


class WrappingCheckBox(QWidget):
    """A checkbox whose text wraps onto several lines.

    QCheckBox never wraps its own text (it clips at the widget edge), so
    the checkbox here carries no text of its own - a label next to it shows
    it, and a click on that label toggles the checkbox just like a click on
    the box itself. The text is also set as the checkbox's accessible name,
    so a screen reader still announces what is being confirmed.
    """

    toggled = Signal(bool)

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._checkbox = QCheckBox(self)
        self._checkbox.setAccessibleName(text)
        self._checkbox.toggled.connect(self.toggled)
        label = _ToggleLabel(text, self._checkbox, self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._checkbox, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(label, 1)
        self.setFocusProxy(self._checkbox)

    def isChecked(self) -> bool:
        return self._checkbox.isChecked()

    def setChecked(self, checked: bool) -> None:
        self._checkbox.setChecked(checked)
