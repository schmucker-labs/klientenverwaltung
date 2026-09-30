"""The theme buttons in the main window's status bar."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QToolButton, QWidget

from klientenverwaltung.ui.icons import get_icon
from klientenverwaltung.ui.theme import THEME_MODE_LABELS, ThemeMode, get_palette

_ICON_SIZE = 16
_ICON_NAMES = {
    ThemeMode.LIGHT: "sun",
    ThemeMode.DAWN: "dawn",
    ThemeMode.GRAPHITE: "moon",
}


class ThemeSwitcher(QFrame):
    """One button per theme in a single pill: the active theme's button is
    filled with the accent color, a click on another switches to it at once.

    Rather than one button stepping through the themes - with three of
    them, that would not show where the next click leads.
    """

    # Carries the ThemeMode of the clicked button.
    mode_selected = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("themeSwitcher", True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        group = QButtonGroup(self)
        group.setExclusive(True)
        self._buttons: dict[ThemeMode, QToolButton] = {}
        for mode in ThemeMode:
            button = QToolButton(self)
            button.setProperty("themeSwitch", True)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setIconSize(QSize(_ICON_SIZE, _ICON_SIZE))
            button.setToolTip(THEME_MODE_LABELS[mode])
            button.clicked.connect(
                lambda _checked=False, mode=mode: self.mode_selected.emit(mode)
            )
            group.addButton(button)
            layout.addWidget(button)
            self._buttons[mode] = button

    def set_mode(self, active: ThemeMode) -> None:
        """Marks the button of `active` and tints every icon for that
        theme - on the accent fill, the icon takes the panel color (as the
        text of any other checked button does)."""
        palette = get_palette(active)
        for mode, button in self._buttons.items():
            is_active = mode is active
            button.setChecked(is_active)
            color = palette.surface_panel if is_active else palette.text
            button.setIcon(get_icon(_ICON_NAMES[mode], color, _ICON_SIZE))
