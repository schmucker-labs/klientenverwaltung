from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtWidgets import QWidget


def restore_geometry(widget: QWidget, key: str) -> None:
    """Restores a saved window size+position; does nothing on first run.

    Leaves whatever default the widget already has (e.g. its own resize()
    call, or its natural sizeHint) untouched when no value was saved yet.
    """
    geometry = QSettings().value(key)
    if isinstance(geometry, QByteArray):
        widget.restoreGeometry(geometry)


def save_geometry(widget: QWidget, key: str) -> None:
    QSettings().setValue(key, widget.saveGeometry())
