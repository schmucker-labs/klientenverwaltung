"""Central loading point for every icon used in the UI.

Icons are placeholder SVGs under ui/icons/ - swap the files there for real
artwork later, no code changes needed. get_icon() renders the SVG and
tints every opaque pixel with the given color, so an icon always matches
the active theme without needing separate light/dark icon files.
"""

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_ICONS_DIR = Path(__file__).parent / "icons"


def get_icon(name: str, color: str, size: int = 20) -> QIcon:
    """Loads ui/icons/<name>.svg, tinted to `color` at `size` x `size` px."""
    renderer = QSvgRenderer(str(_ICONS_DIR / f"{name}.svg"))
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return QIcon(pixmap)


def load_svg_pixmap(name: str, size: QSize | None = None) -> QPixmap:
    """Loads ui/icons/<name>.svg as-is (its own colors, no tinting).

    For branded, multi-color artwork (the logo, the splash image) rather
    than a monochrome icon meant to match the theme - use get_icon() for
    that. Renders at the SVG's own size unless `size` is given.
    """
    renderer = QSvgRenderer(str(_ICONS_DIR / f"{name}.svg"))
    target_size = size or renderer.defaultSize()
    pixmap = QPixmap(target_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def get_app_icon() -> QIcon:
    """The application/window icon - a pre-rendered multi-resolution .ico.

    Regenerate it from ui/icons/logo.svg with
    `uv run python scripts/generate_app_icon.py` whenever the logo changes.
    """
    return QIcon(str(_ICONS_DIR / "app.ico"))
