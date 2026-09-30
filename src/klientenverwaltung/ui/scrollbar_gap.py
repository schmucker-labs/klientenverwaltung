"""The gap between a QScrollArea's content and its scrollbar (docs/ui-regeln.md).

For content that, without a scrollbar, reaches the dialog's edge in line
with everything above and below the scroll area: it gets a right margin
only while there is a scrollbar to keep clear of.
"""

from PySide6.QtWidgets import QScrollArea


def apply_scrollbar_gap(scroll_area: QScrollArea, gap: int) -> None:
    """Sets the right margin of the scrolled content's layout: `gap` while
    the vertical scrollbar has something to scroll, none otherwise. Call it
    after setWidget() - new content starts without the margin, and the
    scrollbar does not report a range that stayed the same."""
    content = scroll_area.widget()
    layout = content.layout() if content is not None else None
    if layout is None:
        return
    margins = layout.contentsMargins()
    margins.setRight(gap if scroll_area.verticalScrollBar().maximum() > 0 else 0)
    layout.setContentsMargins(margins)


def keep_clear_of_scrollbar(scroll_area: QScrollArea, gap: int) -> None:
    """Applies the gap now and whenever the scrollbar appears or goes."""
    scroll_area.verticalScrollBar().rangeChanged.connect(
        lambda _minimum, _maximum: apply_scrollbar_gap(scroll_area, gap)
    )
    apply_scrollbar_gap(scroll_area, gap)
