"""Central loading point for every icon used in the UI.

Icons are placeholder PNGs under ui/icons/ - swap the files there for real
artwork later, no code changes needed. get_icon() loads a PNG and tints
every opaque pixel with the given color, so an icon always matches the
active theme without needing separate light/dark icon files.

The PNGs are generated from SVG sources (also under ui/icons/) by
scripts/generate_icons.py - regenerate them whenever a source SVG changes.
Only PNG/ICO is ever loaded at runtime: PySide6.QtSvg cannot be bundled
reliably with PyInstaller.
"""

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

_ICONS_DIR = Path(__file__).parent / "icons"


def get_icon(name: str, color: str, size: int = 20) -> QIcon:
    """Loads ui/icons/<name>.png, tinted to `color` at `size` x `size` px."""
    source = QPixmap(str(_ICONS_DIR / f"{name}.png"))
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.drawPixmap(pixmap.rect(), source, source.rect())
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor(color))
    painter.end()
    return QIcon(pixmap)


def load_pixmap(name: str, size: QSize | None = None) -> QPixmap:
    """Loads ui/icons/<name>.png as-is (its own colors, no tinting).

    For branded, multi-color artwork (the logo, the splash image) rather
    than a monochrome icon meant to match the theme - use get_icon() for
    that. Loads at the PNG's own size unless `size` is given, in which
    case it is scaled smoothly, keeping aspect ratio.
    """
    pixmap = QPixmap(str(_ICONS_DIR / f"{name}.png"))
    if size is not None and size != pixmap.size():
        pixmap = pixmap.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return pixmap


def get_app_icon() -> QIcon:
    """The application/window icon - a pre-rendered multi-resolution .ico.

    Regenerate it from ui/icons/logo.svg with
    `uv run python scripts/generate_icons.py` whenever the logo changes.
    """
    return QIcon(str(_ICONS_DIR / "app.ico"))
