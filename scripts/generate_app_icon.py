"""Regenerates the Windows application icon from ui/icons/logo.svg.

Run this after changing logo.svg - nothing else needs to change, the
PyInstaller build and every window icon load the generated file:

    uv run python scripts/generate_app_icon.py

Builds the .ico by hand (ICONDIR + ICONDIRENTRY, PNG-compressed frames)
instead of depending on Pillow just for this one script: modern .ico files
may embed PNG data directly, and Qt already gives us PNG encoding via
QPixmap.save(), so no extra dependency is needed.
"""

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice, QSize, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

_ICON_SIZES = (16, 32, 48, 64, 128, 256)
_ICONS_DIR = Path(__file__).resolve().parent.parent / "src/klientenverwaltung/ui/icons"
_LOGO_SVG = _ICONS_DIR / "logo.svg"
_ICON_OUTPUT = _ICONS_DIR / "app.ico"


def _render_png_bytes(renderer: QSvgRenderer, size: int) -> bytes:
    pixmap = QPixmap(QSize(size, size))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return bytes(buffer.data())


def _write_ico(frames: list[tuple[int, bytes]], output_path: Path) -> None:
    # ICONDIR: reserved(2)=0, type(2)=1 (icon), count(2)
    header = struct.pack("<HHH", 0, 1, len(frames))

    directory = b""
    images = b""
    offset = len(header) + len(frames) * 16  # each ICONDIRENTRY is 16 bytes
    for size, data in frames:
        dimension_byte = size if size < 256 else 0  # 0 means 256 in ICO format
        directory += struct.pack(
            "<BBBBHHII",
            dimension_byte,  # width
            dimension_byte,  # height
            0,  # color count (0 = no palette, i.e. PNG/32-bit)
            0,  # reserved
            1,  # color planes
            32,  # bits per pixel
            len(data),  # size of image data
            offset,  # offset of image data from file start
        )
        images += data
        offset += len(data)

    output_path.write_bytes(header + directory + images)


def main() -> None:
    QApplication(sys.argv)  # QPixmap/QPainter need an application instance

    renderer = QSvgRenderer(str(_LOGO_SVG))
    if not renderer.isValid():
        raise SystemExit(f"Ungültige oder fehlende SVG-Datei: {_LOGO_SVG}")

    frames = [(size, _render_png_bytes(renderer, size)) for size in _ICON_SIZES]
    _write_ico(frames, _ICON_OUTPUT)
    print(f"Geschrieben: {_ICON_OUTPUT}")


if __name__ == "__main__":
    main()
