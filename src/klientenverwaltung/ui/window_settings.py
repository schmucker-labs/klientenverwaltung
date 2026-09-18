from PySide6.QtCore import QByteArray, QRect, QSettings
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHeaderView, QWidget

# Applies to every persisted table column everywhere in the app, so no
# column can ever be dragged down to zero width regardless of which dialog
# it lives in.
MIN_COLUMN_WIDTH = 30


def restore_geometry(widget: QWidget, key: str) -> None:
    """Restores a saved window size+position; does nothing on first run.

    Leaves whatever default the widget already has (e.g. its own resize()
    call, or its natural sizeHint) untouched when no value was saved yet,
    or when what was saved is unusable (zero size, entirely off-screen -
    e.g. after an external monitor was unplugged).
    """
    data = QSettings().value(key)
    if not isinstance(data, QByteArray):
        return
    probe = QWidget()
    if not probe.restoreGeometry(data) or not _is_usable_geometry(probe.geometry()):
        return
    widget.restoreGeometry(data)


def save_geometry(widget: QWidget, key: str) -> None:
    QSettings().setValue(key, widget.saveGeometry())


def _is_usable_geometry(rect: QRect) -> bool:
    if rect.width() <= 0 or rect.height() <= 0:
        return False
    return any(
        screen.availableGeometry().intersects(rect)
        for screen in QGuiApplication.screens()
    )


def restore_header_state(header: QHeaderView, key: str) -> bool:
    """Restores a saved column layout (widths, order, sort, resize modes).

    Always enforces MIN_COLUMN_WIDTH first, regardless of outcome. Returns
    True if a saved state was found and applied; False on first run, so the
    caller can apply its own content-based default layout instead.
    """
    header.setMinimumSectionSize(MIN_COLUMN_WIDTH)
    data = QSettings().value(key)
    return isinstance(data, QByteArray) and header.restoreState(data)


def save_header_state(header: QHeaderView, key: str) -> None:
    QSettings().setValue(key, header.saveState())
