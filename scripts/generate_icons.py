"""Regenerates every PNG/ICO icon asset from their SVG sources under
ui/icons/. Run this after changing any of those SVGs - nothing else needs
to change, the PyInstaller build and every window load the generated
files:

    uv run python scripts/generate_icons.py

The application loads only PNG/ICO at runtime (see icons.py) - PySide6.QtSvg
cannot be bundled reliably with PyInstaller. The SVGs stay the source
format and are only ever rendered by this dev-time script, which runs in
the full environment (QtSvg installed) and never ships in the frozen app.

Builds app.ico by hand (ICONDIR + ICONDIRENTRY, PNG-compressed frames)
instead of depending on Pillow just for this one file: modern .ico files
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

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
from klientenverwaltung import AUTHOR_SHORT

_ICON_SIZES = (16, 32, 48, 64, 128, 256)
_LOGO_BASE_SIZE = 256
_ICONS_DIR = _REPO_ROOT / "src/klientenverwaltung/ui/icons"
_MONOCHROME_ICON_BASE_SIZE = 64


def _render_pixmap(renderer: QSvgRenderer, size: QSize | None = None) -> QPixmap:
    target_size = size or renderer.defaultSize()
    pixmap = QPixmap(target_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def _render_png_bytes(renderer: QSvgRenderer, size: int) -> bytes:
    pixmap = _render_pixmap(renderer, QSize(size, size))
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


def _load_renderer(
    svg_path: Path, substitutions: dict[str, str] | None = None
) -> QSvgRenderer:
    if substitutions:
        svg_source = svg_path.read_text(encoding="utf-8")
        for placeholder, value in substitutions.items():
            svg_source = svg_source.replace(placeholder, value)
        renderer = QSvgRenderer(svg_source.encode("utf-8"))
    else:
        renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise SystemExit(f"Ungültige oder fehlende SVG-Datei: {svg_path}")
    return renderer


def _generate_app_icon() -> None:
    renderer = _load_renderer(_ICONS_DIR / "logo.svg")
    frames = [(size, _render_png_bytes(renderer, size)) for size in _ICON_SIZES]
    output_path = _ICONS_DIR / "app.ico"
    _write_ico(frames, output_path)
    print(f"Geschrieben: {output_path}")


def _generate_png(
    svg_name: str,
    png_name: str,
    *,
    size: QSize | None = None,
    substitutions: dict[str, str] | None = None,
) -> None:
    renderer = _load_renderer(_ICONS_DIR / f"{svg_name}.svg", substitutions)
    pixmap = _render_pixmap(renderer, size)
    output_path = _ICONS_DIR / png_name
    if not pixmap.save(str(output_path), "PNG"):
        raise SystemExit(f"Konnte PNG nicht schreiben: {output_path}")
    print(f"Geschrieben: {output_path}")


def main() -> None:
    QApplication(sys.argv)  # QPixmap/QPainter need an application instance

    _generate_app_icon()
    _generate_png("logo", "logo.png", size=QSize(_LOGO_BASE_SIZE, _LOGO_BASE_SIZE))
    _generate_png(
        "splash", "splash.png", substitutions={"__AUTHOR_SHORT__": AUTHOR_SHORT}
    )
    _generate_png(
        "sun",
        "sun.png",
        size=QSize(_MONOCHROME_ICON_BASE_SIZE, _MONOCHROME_ICON_BASE_SIZE),
    )
    _generate_png(
        "moon",
        "moon.png",
        size=QSize(_MONOCHROME_ICON_BASE_SIZE, _MONOCHROME_ICON_BASE_SIZE),
    )


if __name__ == "__main__":
    main()
