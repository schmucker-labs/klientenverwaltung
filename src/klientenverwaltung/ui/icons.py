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
