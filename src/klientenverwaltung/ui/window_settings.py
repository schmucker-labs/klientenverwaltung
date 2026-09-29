from collections.abc import Sequence

from PySide6.QtCore import (
    QByteArray,
    QEvent,
    QObject,
    QRect,
    QSettings,
    QSignalBlocker,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHeaderView, QWidget

# Applies to every persisted table column everywhere in the app, so no
# column can ever be dragged down to zero width regardless of which dialog
# it lives in.
MIN_COLUMN_WIDTH = 30


def restore_geometry(widget: QWidget, key: str) -> None:
    """Restores a saved window size+position, or leaves the widget's own
    default (its resize() call, or its natural sizeHint) on first run, or
    when what was saved is unusable (zero size, entirely off-screen - e.g.
    after an external monitor was unplugged).

    Either way, always finishes with clamp_to_available_geometry(): a
    saved size from a larger/differently-arranged screen, or a plain
    hardcoded default, must not be allowed to leave the window partly
    hanging off-screen or taller than the current screen's available area
    (e.g. behind the taskbar) just because that is what was saved or
    originally guessed.
    """
    data = QSettings().value(key)
    if isinstance(data, QByteArray):
        probe = QWidget()
        if probe.restoreGeometry(data) and _is_usable_geometry(probe.geometry()):
            widget.restoreGeometry(data)
    clamp_to_available_geometry(widget)


def save_geometry(widget: QWidget, key: str) -> None:
    QSettings().setValue(key, widget.saveGeometry())


def clamp_to_available_geometry(widget: QWidget) -> None:
    """Shrinks and repositions widget so it fully fits its current
    screen's available area (i.e. excluding the taskbar).

    Only ever shrinks/moves, never grows a widget - a widget whose actual
    minimum size (once its layout is built) is still larger than the
    available area will be forced back up by Qt's own layout system
    regardless of anything done here; that has to be fixed at the source
    (fewer/lower fixed minimum heights, or a QScrollArea) rather than here.

    Repositioning works in frameGeometry() terms (the window's actual
    on-screen bounds, title bar included) rather than geometry() (just the
    content area): clamping geometry() alone can still leave the title bar
    itself poking out above the available area, exactly the "hangs behind
    the taskbar" problem this exists to prevent.
    """
    screen = QGuiApplication.screenAt(widget.geometry().center()) or widget.screen()
    if screen is None:
        return
    available = screen.availableGeometry()

    width = min(widget.width(), available.width())
    height = min(widget.height(), available.height())
    if (width, height) != (widget.width(), widget.height()):
        widget.resize(width, height)

    frame = widget.frameGeometry()
    dx = min(0, available.right() - frame.right())
    dx = max(dx, available.x() - frame.x())
    dy = min(0, available.bottom() - frame.bottom())
    dy = max(dy, available.y() - frame.y())
    if dx or dy:
        widget.move(widget.x() + dx, widget.y() + dy)


def _is_usable_geometry(rect: QRect) -> bool:
    if rect.width() <= 0 or rect.height() <= 0:
        return False
    return any(
        screen.availableGeometry().intersects(rect)
        for screen in QGuiApplication.screens()
    )


def _column_titles_key(key: str) -> str:
    return f"{key}/columns"


def restore_header_state(
    header: QHeaderView, key: str, column_titles: Sequence[str]
) -> bool:
    """Restores a saved column layout (widths, order, sort, resize modes).

    Always enforces MIN_COLUMN_WIDTH first, regardless of outcome. Returns
    True if a saved state was found and applied; False on first run, so the
    caller can apply its own content-based default widths instead.

    A saved state is only applied if it was saved for the exact same
    column headings, in the same order. Table models gain/lose columns
    over time (schema changes, feature work), and restoreState() otherwise
    happily reapplies a layout sized for a different column count - the
    view then addresses columns the model no longer has, which crashes
    headerData(). On a mismatch (including one saved by an older version
    of this code, before column_titles was recorded at all) the saved
    state is discarded outright (removed from QSettings, not just
    ignored) and this returns False so the caller's own default widths
    apply, exactly as on a genuine first run. Applies to every caller,
    not just one particular table.

    restoreState() also restores each section's resize mode and the
    stretchLastSection flag exactly as they were when saveState() ran. A
    caller MUST always follow this with finalize_column_widths() regardless
    of the return value - otherwise an old (possibly buggy) mode layout
    saved under a prior version of the code keeps overriding every later
    fix, for any user who already has a saved header state.
    """
    header.setMinimumSectionSize(MIN_COLUMN_WIDTH)
    settings = QSettings()
    columns_key = _column_titles_key(key)
    saved_columns = settings.value(columns_key)
    saved_columns = list(saved_columns) if saved_columns is not None else None
    if saved_columns != list(column_titles):
        settings.remove(key)
        settings.remove(columns_key)
        return False
    data = settings.value(key)
    return isinstance(data, QByteArray) and header.restoreState(data)


def save_header_state(
    header: QHeaderView, key: str, column_titles: Sequence[str]
) -> None:
    settings = QSettings()
    settings.setValue(key, header.saveState())
    settings.setValue(_column_titles_key(key), list(column_titles))


def finalize_column_widths(
    header: QHeaderView, column_count: int, fill_column: int, restored: bool
) -> None:
    """Forces every column to plain Interactive with stretchLastSection off,
    and keeps the columns filling the header's width whenever it changes
    (window resize, splitter drag, ...) from then on. Call unconditionally,
    always after restore_header_state() (see its docstring for why "always"
    matters), passing its return value as `restored`.

    Never uses ResizeMode.Stretch. A stretched column has no drag handle of
    its own - Qt shows a handle for every column boundary except the one
    belonging to the stretched section, which shifts the handle-to-border
    mapping for every column after it one column to the right (that's the
    "wrong edge moves" bug this replaces).

    On first run, the caller must already have sized every column except
    `fill_column` to its content (e.g. via resizeColumnsToContents()) before
    calling this - the very first layout tops up `fill_column` with
    whatever header width is left over. Every later header resize (and, for
    a returning user with saved widths, the first one too) redistributes
    the width change proportionally across every column instead, since by
    then every column may carry a width the user chose deliberately. If the
    window shrinks so far that every column is already at MIN_COLUMN_WIDTH,
    the table's horizontal scrollbar appears rather than shrinking further.

    Separately, a manual drag of one column's own border (its
    sectionResized signal) is compensated for immediately: the column(s) to
    its right give up or absorb exactly that much width, cascading
    rightward down to MIN_COLUMN_WIDTH, so the table's total width never
    changes just because the user dragged a column - no empty strip opens
    up on the right, and no horizontal scrollbar appears purely from
    dragging. If every column to the right is already at MIN_COLUMN_WIDTH
    and the user keeps growing a column, that column's own growth is
    clamped for the same reason.
    """
    header.setStretchLastSection(False)
    for column in range(column_count):
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
    _AutoFitColumns(header, column_count, fill_column, first_run=not restored)


class _AutoFitColumns(QObject):
    """Keeps a header's columns always summing to exactly its own width.

    Two independent triggers feed the same invariant:

    - The header's own resize event (window resize, splitter drag, ...):
      handled by _fit(), which redistributes the change proportionally
      across every column. Installed as an event filter on the header
      itself rather than the table's viewport, since the header is always
      resized in lockstep with the viewport - watching the header's own
      resize event is equivalent to watching "how much width is available
      for columns" without needing a reference to the table view.

    - A user dragging a single column's border (the sectionResized
      signal): handled by _compensate_drag(), which shifts exactly that
      much width to/from the column(s) to its right, cascading down to
      MIN_COLUMN_WIDTH, so the total never changes just because the user
      resized one column.

    Every adjustment either handler makes runs inside QSignalBlocker(header),
    so it can never re-enter this same class through the signal it would
    otherwise emit, and never reaches a caller's own sectionResized-connected
    slot (typically one that saves the header state) - only the user's
    actual drag, or the header's actual resize, is a new event to react to
    or persist; everything this class then does about it is a mechanical
    side effect of that one event, not a second one.

    Parented to the header, so it lives exactly as long as the header does.
    """

    def __init__(
        self,
        header: QHeaderView,
        column_count: int,
        fill_column: int,
        first_run: bool,
    ) -> None:
        super().__init__(header)
        self._header = header
        self._column_count = column_count
        self._fill_column = fill_column
        self._laid_out_once = not first_run
        header.installEventFilter(self)
        header.sectionResized.connect(self._compensate_drag)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize:
            self._fit(self._header.width())
        return False

    def _compensate_drag(
        self, logical_index: int, old_size: int, new_size: int
    ) -> None:
        delta = new_size - old_size
        if delta == 0:
            return
        header = self._header
        remaining = delta
        with QSignalBlocker(header):
            for column in range(logical_index + 1, self._column_count):
                if remaining == 0:
                    break
                current = header.sectionSize(column)
                if remaining > 0:
                    # The dragged column grew - shrink this one to cover as
                    # much of that as it can without going below minimum.
                    give = min(remaining, current - MIN_COLUMN_WIDTH)
                    if give > 0:
                        header.resizeSection(column, current - give)
                        remaining -= give
                else:
                    # The dragged column shrank - hand all of the freed
                    # width straight to its immediate right neighbor.
                    header.resizeSection(column, current - remaining)
                    remaining = 0
            if remaining > 0:
                # No column to the right had any room left to give up -
                # clamp the dragged column's own growth so the total still
                # can't exceed the header's width.
                header.resizeSection(logical_index, new_size - remaining)

    def _fit(self, available_width: int) -> None:
        if available_width <= 0:
            return
        header = self._header
        widths = [header.sectionSize(c) for c in range(self._column_count)]
        total = sum(widths)
        if total == available_width:
            self._laid_out_once = True
            return
        if not self._laid_out_once:
            other_columns_width = total - widths[self._fill_column]
            new_widths = list(widths)
            new_widths[self._fill_column] = max(
                MIN_COLUMN_WIDTH, available_width - other_columns_width
            )
        else:
            new_widths = _proportional_widths(widths, available_width, MIN_COLUMN_WIDTH)
        self._laid_out_once = True
        if new_widths == widths:
            return
        # sectionResized must not fire here - a caller typically saves the
        # header state on that signal, and this is an automatic layout
        # adjustment, not a user-initiated resize that should be persisted.
        with QSignalBlocker(header):
            for column, width in enumerate(new_widths):
                if width != widths[column]:
                    header.resizeSection(column, width)


def _proportional_widths(
    widths: list[int], target_total: int, min_width: int
) -> list[int]:
    """Scales `widths` so they sum to `target_total`, in proportion to each
    column's current share of the total, without going below `min_width`.

    If honoring `min_width` for every column would overshoot `target_total`
    (the available width is too small for all columns at their minimum),
    the result simply doesn't sum to `target_total` - the caller/view is
    then expected to show a horizontal scrollbar, exactly as it would for a
    manually widened column.
    """
    total = sum(widths)
    if total <= 0:
        return widths
    scaled = [max(min_width, round(width * target_total / total)) for width in widths]
    diff = target_total - sum(scaled)
    if diff == 0:
        return scaled
    # Nudge one pixel at a time, largest column first, until the total
    # matches exactly; skips columns already at min_width when shrinking.
    order = sorted(range(len(widths)), key=lambda i: scaled[i], reverse=True)
    guard = 0
    max_iterations = 10 * len(widths) + 10
    while diff != 0 and guard < max_iterations:
        index = order[guard % len(order)]
        if diff > 0:
            scaled[index] += 1
            diff -= 1
        elif scaled[index] > min_width:
            scaled[index] -= 1
            diff += 1
        guard += 1
    return scaled
