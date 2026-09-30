"""Central color definitions and theme switching for the app.

Every color used anywhere in the UI must be a named field on ColorPalette,
set here and nowhere else. UI code builds a style sheet from a palette via
build_stylesheet() and never embeds a hex value directly.

The style sheet is applied to the whole QApplication (see apply_theme_mode),
not to individual windows, so a mode switch reaches every open window and
dialog immediately, with no restart needed.
"""

import tempfile
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPixmap, QPolygon
from PySide6.QtWidgets import QApplication, QSpinBox

# QCheckBox::indicator loses Qt's native checkmark glyph as soon as any of
# its properties are styled via QSS, so :checked draws this fixed white
# icon instead. A PNG rather than SVG, so PyInstaller never needs to bundle
# the Qt SVG plugin just for a checkbox tick.
_CHECKMARK_ICON_PATH = (Path(__file__).parent / "assets" / "checkmark.png").as_posix()

_ARROW_SIZE = 10


def _triangle_icon_path(direction: str, color: str) -> str:
    """A small triangle pointing "up" or "down" in `color`, cached to a
    temp PNG.

    QComboBox::down-arrow and QAbstractSpinBox::up-arrow/down-arrow need an
    actual image - the usual QSS trick of faking a triangle with
    transparent/solid borders does not render as a triangle in this app's
    active style, it just shows a solid block - and the color has to track
    the palette (text_secondary/text_disabled), which rules out a single
    fixed asset like the checkbox checkmark uses. Not client data, so a
    temp file is fine here (see storage rules).
    """
    path = (
        Path(tempfile.gettempdir())
        / f"klientenverwaltung_{direction}_arrow_{color.lstrip('#')}.png"
    )
    if not path.exists():
        pixmap = QPixmap(_ARROW_SIZE, _ARROW_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        tip_y = _ARROW_SIZE - 2 if direction == "down" else 2
        base_y = 2 if direction == "down" else _ARROW_SIZE - 2
        painter.drawPolygon(
            QPolygon(
                [
                    QPoint(0, base_y),
                    QPoint(_ARROW_SIZE, base_y),
                    QPoint(_ARROW_SIZE // 2, tip_y),
                ]
            )
        )
        painter.end()
        pixmap.save(str(path))
    return path.as_posix()


def _spin_button_height() -> int:
    """QAbstractSpinBox's natural full height minus its 1px top/bottom
    border - the up/down button pair's combined height (split in half
    between them below), so together they fill it edge to edge.

    Styling QAbstractSpinBox::up-button/down-button at all switches Qt
    from its native Windows spin-button rendering (a style this app can
    otherwise keep unstyled everywhere else) to drawing plain boxes from
    these rules - required because the native rendering's up-button hit
    area breaks entirely under a QSS border (confirmed with real click
    probes: literally no pixel in the up-button's visible area registers
    a click, while down-button's still does). They must stay stacked
    top/bottom rather than side by side like the native rendering: Qt's
    styled subcontrol-position for CC_SpinBox only differentiates up vs.
    down vertically - `margin-right` does not shift a "top right"-anchored
    box sideways, it only pads its own already-full-width rect, so two
    side-by-side boxes placed that way overlap and one swallows the
    other's clicks (confirmed the same way).

    Measured from a real probe widget rather than computed by hand from
    the font-metrics/padding/border literals below, so it can't quietly
    drift out of sync with them, and keeps tracking correctly if the
    app's global font size ever changes.
    """
    probe = QSpinBox()
    return max(probe.sizeHint().height() - 2, 10)


@dataclass(frozen=True)
class ColorPalette:
    # Window background, behind every panel.
    background: str
    # Menu bar / status bar / table header background.
    surface_toolbar: str
    # Table body, dialogs, buttons, cards.
    surface_panel: str
    # Text inputs: QLineEdit, QComboBox, QDateEdit, ...
    surface_input: str
    # Hover feedback on rows, buttons and menu items.
    hover: str
    # Primary text.
    text: str
    # De-emphasized text: table header labels, status bar, hints.
    text_secondary: str
    # Disabled controls and their labels.
    text_disabled: str
    # Archived clients in the client list.
    text_archived: str
    # Borders, gridlines, separators.
    lines: str
    # Primary brand color: default buttons, links, primary emphasis.
    accent: str
    # Secondary brand color: pressed state, minor emphasis.
    accent_secondary: str
    # Selected table row background.
    selection_background: str
    # Selected table row text.
    selection_text: str
    # Error text and borders (e.g. invalid form fields) - deliberately a
    # true red, distinct from the terracotta accent, so it's never mistaken
    # for a normal call-to-action color.
    error: str
    # Focus ring around the currently focused input.
    focus: str
    # What floats above a window: menus, combo box lists, tooltips. In a
    # theme that layers its surfaces by brightness this is the topmost one.
    surface_floating: str
    # The edge of a floating surface - where that surface is lifted, a
    # hairline lighter than `lines`, so it stands out from what is below.
    lines_floating: str


LIGHT_PALETTE = ColorPalette(
    background="#F5F1EB",
    surface_toolbar="#FFFFFF",
    surface_panel="#FFFFFF",
    surface_input="#FFFFFF",
    # Proposed: a shade between background and lines, so hover reads as a
    # subtle darkening rather than a new surface.
    hover="#EFE7DB",
    text="#302C28",
    text_secondary="#766E65",
    # Proposed: muted further than text_secondary, low enough contrast to
    # read as "unavailable" without becoming illegible.
    text_disabled="#ABA399",
    # Proposed: same as text_secondary - archived clients are de-emphasized,
    # not disabled, so they reuse the existing secondary-text role rather
    # than adding another near-duplicate gray. Combined with italic in the
    # client list model, matching how inactive treatment types are shown.
    text_archived="#766E65",
    lines="#DDD5CA",
    accent="#A7654F",
    accent_secondary="#B89A67",
    # Proposed: a light tint of accent over the background.
    selection_background="#E7D8CF",
    # Proposed: reuse normal text - the tinted background alone is enough
    # to mark the row as selected without needing separate text handling.
    selection_text="#302C28",
    # Proposed: a clear red, chosen to sit well apart from the terracotta
    # accent (more saturated, cooler) so it can't be mistaken for it.
    error="#C0392B",
    # Proposed: reuse accent - a colored focus ring in the brand color is
    # the standard pattern, so it gets its own name here rather than being
    # written as `accent` at every call site.
    focus="#A7654F",
    surface_floating="#FFFFFF",
    lines_floating="#DDD5CA",
)

# The warm dark theme ("Dämmerung") - the only dark theme until the graphite
# one was added, and called "dark" back then (see load_theme_mode).
DAWN_PALETTE = ColorPalette(
    background="#211C18",
    surface_toolbar="#29231E",
    surface_panel="#302923",
    surface_input="#27211D",
    hover="#3A312A",
    text="#E8DED2",
    text_secondary="#B5A79A",
    # Proposed: muted further than text_secondary, mirroring the light mode.
    text_disabled="#6B6055",
    # Proposed: same as text_secondary, for the same reason as in Light.
    text_archived="#B5A79A",
    lines="#453B33",
    accent="#B86D50",
    accent_secondary="#B99A68",
    # Proposed: a stronger tint than Light's, since it sits on a dark panel
    # rather than a light background.
    selection_background="#604133",
    selection_text="#E8DED2",
    # Proposed: brighter/more saturated than Light's error red, for contrast
    # against the dark background.
    error="#E5534A",
    focus="#B86D50",
    surface_floating="#302923",
    lines_floating="#453B33",
)

# The neutral dark theme ("Dunkel"): near-black, slightly cool grays layered
# by brightness (the lighter a surface, the higher it sits), with Dämmerung's
# accent - on gray it needs no brightening, its contrast is higher here.
GRAPHITE_PALETTE = ColorPalette(
    background="#16171A",
    surface_toolbar="#1A1B1F",
    surface_panel="#1C1D21",
    surface_input="#121316",
    hover="#2A2C32",
    text="#E6E7E9",
    text_secondary="#9BA1A9",
    text_disabled="#5C6068",
    text_archived="#9BA1A9",
    lines="#2E3036",
    accent="#B86D50",
    accent_secondary="#B99A68",
    # A dark tint of accent over the panel, as in Dämmerung.
    selection_background="#47332D",
    selection_text="#E6E7E9",
    error="#E5534A",
    focus="#B86D50",
    surface_floating="#212226",
    lines_floating="#3A3D44",
)


class ThemeMode(StrEnum):
    LIGHT = "light"
    DAWN = "dawn"
    GRAPHITE = "graphite"


# What the user sees for each theme: menu entries and tooltips.
THEME_MODE_LABELS = {
    ThemeMode.LIGHT: "Hell",
    ThemeMode.DAWN: "Dämmerung",
    ThemeMode.GRAPHITE: "Dunkel",
}

_PALETTES = {
    ThemeMode.LIGHT: LIGHT_PALETTE,
    ThemeMode.DAWN: DAWN_PALETTE,
    ThemeMode.GRAPHITE: GRAPHITE_PALETTE,
}

# Light or dark window title bars - the one part of a window Windows draws.
_COLOR_SCHEMES = {
    ThemeMode.LIGHT: Qt.ColorScheme.Light,
    ThemeMode.DAWN: Qt.ColorScheme.Dark,
    ThemeMode.GRAPHITE: Qt.ColorScheme.Dark,
}

_THEME_MODE_SETTINGS_KEY = "appearance/theme_mode"
# Saved by versions with only two themes, where "dark" was today's Dämmerung.
_LEGACY_DARK_VALUE = "dark"


def get_palette(mode: ThemeMode) -> ColorPalette:
    return _PALETTES[mode]


def load_theme_mode() -> ThemeMode:
    value = QSettings().value(_THEME_MODE_SETTINGS_KEY)
    if value == _LEGACY_DARK_VALUE:
        return ThemeMode.DAWN
    try:
        return ThemeMode(value)
    except ValueError:
        return ThemeMode.LIGHT


def save_theme_mode(mode: ThemeMode) -> None:
    QSettings().setValue(_THEME_MODE_SETTINGS_KEY, mode.value)


_current_mode = ThemeMode.LIGHT


def current_palette() -> ColorPalette:
    """The palette of the theme applied last - for colors that code sets
    directly (e.g. a table model's ForegroundRole) rather than via the
    style sheet. Read on every paint, so a theme switch reaches them with
    the repaint the style sheet change triggers anyway."""
    return get_palette(_current_mode)


def apply_theme_mode(mode: ThemeMode) -> None:
    """Applies `mode` to the whole application, live.

    Set on QApplication rather than on any one window, so every currently
    open window and dialog re-polishes with the new colors immediately -
    no restart, and no per-window wiring needed as new dialogs are added.
    The title bars follow via Qt's color scheme: a dark theme under a
    white title bar (or the reverse, with Windows itself set to dark)
    would not look like one window.
    """
    global _current_mode
    _current_mode = mode
    app = QApplication.instance()
    if isinstance(app, QApplication):
        QGuiApplication.styleHints().setColorScheme(_COLOR_SCHEMES[mode])
        app.setStyleSheet(build_stylesheet(get_palette(mode)))


def build_stylesheet(palette: ColorPalette) -> str:
    p = palette
    return f"""
        QMainWindow, QWidget, QWizard {{
            background-color: {p.background};
            color: {p.text};
        }}

        QMenuBar {{
            background-color: {p.surface_toolbar};
            color: {p.text};
            border-bottom: 1px solid {p.lines};
        }}
        QMenuBar::item {{
            background: transparent;
        }}
        QMenuBar::item:selected {{
            background-color: {p.hover};
        }}
        QMenu {{
            background-color: {p.surface_floating};
            color: {p.text};
            border: 1px solid {p.lines_floating};
            border-radius: 8px;
            padding: 4px;
        }}
        QMenu::item {{
            padding: 6px 20px;
            border-radius: 4px;
        }}
        QMenu::item:selected {{
            background-color: {p.hover};
        }}
        QMenu::item:disabled {{
            color: {p.text_disabled};
        }}
        QMenu::separator {{
            height: 1px;
            background-color: {p.lines_floating};
            margin: 4px 8px;
        }}
        QToolTip {{
            background-color: {p.surface_floating};
            color: {p.text};
            border: 1px solid {p.lines_floating};
            padding: 4px 6px;
        }}

        QStatusBar {{
            background-color: {p.surface_toolbar};
            color: {p.text_secondary};
            border-top: 1px solid {p.lines};
        }}
        /* Without these, each widget in the bar sits between two native
           separator lines (white in a dark theme), and a label or the
           size grip shows the window background instead of the bar's. */
        QStatusBar::item {{
            border: none;
        }}
        QStatusBar QLabel, QStatusBar QSizeGrip {{
            background-color: transparent;
        }}

        QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QAbstractSpinBox {{
            background-color: {p.surface_input};
            color: {p.text};
            border: 1px solid {p.lines};
            border-radius: 4px;
            padding: 4px 8px;
            /* Selected text like a selected table row - unset, it is the
               Windows system blue, the one color not from the theme. */
            selection-background-color: {p.selection_background};
            selection-color: {p.selection_text};
        }}
        QLineEdit:focus, QComboBox:focus,
        QTextEdit:focus, QPlainTextEdit:focus, QAbstractSpinBox:focus {{
            border: 1px solid {p.focus};
            color: {p.text};
        }}
        QLineEdit:disabled, QComboBox:disabled,
        QTextEdit:disabled, QAbstractSpinBox:disabled {{
            color: {p.text_disabled};
        }}
        QComboBox::drop-down {{
            border: none;
            width: 22px;
        }}
        QComboBox::down-arrow {{
            image: url({_triangle_icon_path("down", p.text_secondary)});
            width: {_ARROW_SIZE}px;
            height: {_ARROW_SIZE}px;
            margin-right: 6px;
        }}
        QComboBox::down-arrow:disabled {{
            image: url({_triangle_icon_path("down", p.text_disabled)});
        }}
        QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
            subcontrol-origin: border;
            width: 20px;
            height: {_spin_button_height() // 2}px;
            background-color: {p.surface_panel};
            border-left: 1px solid {p.lines};
        }}
        QAbstractSpinBox::up-button {{
            subcontrol-position: top right;
            border-top-right-radius: 4px;
        }}
        QAbstractSpinBox::down-button {{
            subcontrol-position: bottom right;
            border-top: 1px solid {p.lines};
            border-bottom-right-radius: 4px;
        }}
        QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
            background-color: {p.hover};
        }}
        QAbstractSpinBox::up-button:pressed, QAbstractSpinBox::down-button:pressed {{
            background-color: {p.accent_secondary};
        }}
        QAbstractSpinBox::up-button:disabled, QAbstractSpinBox::down-button:disabled {{
            background-color: {p.surface_panel};
        }}
        QAbstractSpinBox::up-arrow {{
            image: url({_triangle_icon_path("up", p.text_secondary)});
            width: {_ARROW_SIZE}px;
            height: {_ARROW_SIZE}px;
        }}
        QAbstractSpinBox::down-arrow {{
            image: url({_triangle_icon_path("down", p.text_secondary)});
            width: {_ARROW_SIZE}px;
            height: {_ARROW_SIZE}px;
        }}
        QAbstractSpinBox::up-arrow:disabled {{
            image: url({_triangle_icon_path("up", p.text_disabled)});
        }}
        QAbstractSpinBox::down-arrow:disabled {{
            image: url({_triangle_icon_path("down", p.text_disabled)});
        }}
        QComboBox QAbstractItemView {{
            background-color: {p.surface_floating};
            color: {p.text};
            border: 1px solid {p.lines_floating};
            selection-background-color: {p.selection_background};
            selection-color: {p.selection_text};
        }}

        QPushButton {{
            background-color: {p.surface_panel};
            color: {p.text};
            border: 1px solid {p.lines};
            border-radius: 5px;
            /* One size for every button (docs/ui-regeln.md): 32 px
               tall like the input fields (22 + 2x4 padding + 2x1
               border), at least 96 px wide (66 + 2x14 + 2x1) so
               short labels like "OK" do not make stubs. */
            padding: 4px 14px;
            min-height: 22px;
            min-width: 66px;
        }}
        /* The default button (what Enter triggers) is tinted; the focused
           one gets a thicker ring - so both stay tellable apart, also when
           they are the same button. Rules of equal specificity: the later
           one wins, hence hover/pressed/focus/disabled after default. */
        QPushButton:default {{
            background-color: {p.selection_background};
            border: 1px solid {p.accent};
            color: {p.text};
        }}
        QPushButton:hover {{
            background-color: {p.hover};
            color: {p.text};
        }}
        QPushButton:pressed {{
            background-color: {p.accent_secondary};
            color: {p.surface_panel};
            border: 1px solid {p.accent_secondary};
        }}
        QPushButton:focus {{
            border: 2px solid {p.focus};
            padding: 3px 13px;
            color: {p.text};
        }}
        QPushButton:disabled {{
            background-color: {p.surface_panel};
            color: {p.text_disabled};
            border: 1px solid {p.lines};
            padding: 4px 14px;
        }}
        QPushButton:checked {{
            background-color: {p.accent};
            color: {p.surface_panel};
            border: 1px solid {p.accent};
        }}
        QPushButton:checked:hover {{
            background-color: {p.accent_secondary};
            color: {p.surface_panel};
            border: 1px solid {p.accent_secondary};
        }}
        QPushButton:checked:pressed {{
            background-color: {p.accent_secondary};
            color: {p.surface_panel};
            border: 1px solid {p.accent_secondary};
        }}
        QPushButton:checked:disabled {{
            background-color: {p.text_disabled};
            color: {p.surface_panel};
            border: 1px solid {p.text_disabled};
        }}
        /* Icon-only toolbar buttons next to another control (see
           docs/ui-regeln.md): without the padding and minimum size of a
           dialog button - their own size hint makes them a square as
           tall as that control. After the rules above - equal
           specificity, so this one wins in every state. */
        QPushButton[toolbarButton="true"] {{
            padding: 0;
            min-height: 0;
            min-width: 0;
        }}

        /* The theme buttons in the status bar (ui/theme_switcher.py): one
           pill, the active theme's button filled with the accent. */
        QFrame[themeSwitcher="true"] {{
            background-color: {p.surface_input};
            border: 1px solid {p.lines};
            border-radius: 6px;
        }}
        QToolButton[themeSwitch="true"] {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 4px;
            padding: 2px 6px;
        }}
        QToolButton[themeSwitch="true"]:hover {{
            background-color: {p.hover};
        }}
        QToolButton[themeSwitch="true"]:pressed {{
            background-color: {p.accent_secondary};
        }}
        QToolButton[themeSwitch="true"]:focus {{
            border: 1px solid {p.focus};
        }}
        QToolButton[themeSwitch="true"]:checked {{
            background-color: {p.accent};
            border: 1px solid {p.accent};
        }}
        QToolButton[themeSwitch="true"]:checked:hover,
        QToolButton[themeSwitch="true"]:checked:pressed {{
            background-color: {p.accent_secondary};
            border: 1px solid {p.accent_secondary};
        }}
        QToolButton[themeSwitch="true"]:disabled {{
            background-color: transparent;
            border: 1px solid transparent;
        }}
        QToolButton[themeSwitch="true"]:checked:disabled {{
            background-color: {p.text_disabled};
            border: 1px solid {p.text_disabled};
        }}

        QCheckBox {{
            color: {p.text};
            spacing: 8px;
        }}
        QCheckBox:disabled {{
            color: {p.text_disabled};
        }}
        QCheckBox::indicator {{
            width: 18px;
            height: 18px;
            border: 1px solid {p.lines};
            border-radius: 3px;
            background-color: {p.surface_input};
        }}
        QCheckBox::indicator:hover {{
            border: 1px solid {p.accent};
        }}
        QCheckBox::indicator:checked {{
            background-color: {p.accent};
            border: 1px solid {p.accent};
            image: url({_CHECKMARK_ICON_PATH});
        }}
        QCheckBox::indicator:disabled {{
            background-color: {p.surface_panel};
            border: 1px solid {p.lines};
        }}

        QAbstractItemView {{
            background-color: {p.surface_panel};
            alternate-background-color: {p.surface_panel};
            color: {p.text};
            selection-background-color: {p.selection_background};
            selection-color: {p.selection_text};
            border: 1px solid {p.lines};
            outline: none;
        }}
        QAbstractItemView:focus {{
            border: 1px solid {p.focus};
        }}
        QTableView {{
            gridline-color: {p.lines};
        }}
        QAbstractItemView::item {{
            border: none;
        }}
        QAbstractItemView::item:hover {{
            background-color: {p.hover};
        }}
        QAbstractItemView::item:selected {{
            background-color: {p.selection_background};
            color: {p.selection_text};
        }}
        QAbstractItemView::item:selected:hover {{
            background-color: {p.selection_background};
            color: {p.selection_text};
        }}
        QHeaderView::section {{
            background-color: {p.surface_toolbar};
            color: {p.text_secondary};
            border: none;
            border-bottom: 1px solid {p.lines};
            border-right: 1px solid {p.lines};
            padding: 4px 6px;
        }}

        QScrollBar:vertical {{
            background-color: {p.surface_toolbar};
            width: 14px;
            margin: 0;
            border: none;
        }}
        QScrollBar:horizontal {{
            background-color: {p.surface_toolbar};
            height: 14px;
            margin: 0;
            border: none;
        }}
        QScrollBar::handle {{
            background-color: {p.text_disabled};
            border-radius: 5px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical {{
            min-height: 32px;
        }}
        QScrollBar::handle:horizontal {{
            min-width: 32px;
        }}
        QScrollBar::handle:hover {{
            background-color: {p.text_secondary};
        }}
        QScrollBar::handle:pressed {{
            background-color: {p.accent_secondary};
        }}
        /* Unstyled, these fall back to a dithered pattern and fixed-size
           arrow areas - the groove must be plain, the arrows gone. */
        QScrollBar::add-page, QScrollBar::sub-page {{
            background: none;
        }}
        QScrollBar::add-line, QScrollBar::sub-line {{
            width: 0;
            height: 0;
            border: none;
            background: none;
        }}

        /* A caption that ranks below the heading it belongs to, e.g.
           "Bericht"/"Impulse" under a session of the Berichtsverlauf. */
        QLabel[secondary="true"] {{
            color: {p.text_secondary};
        }}

        /* A hairline between sections, e.g. the sessions of the
           Berichtsverlauf - the same color as the borders around it. Its
           height is set in code. */
        QFrame[divider="true"] {{
            background-color: {p.lines};
            border: none;
        }}

        QSplitter::handle {{
            background-color: {p.lines};
            height: 6px;
            width: 6px;
        }}
        QSplitter::handle:hover {{
            background-color: {p.text_secondary};
        }}
    """
