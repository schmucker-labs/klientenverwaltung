from PySide6.QtWidgets import QApplication

from klientenverwaltung.ui.growing_text_edit import MIN_VISIBLE_LINES, GrowingTextEdit


def test_growing_text_edit_defaults_to_min_visible_lines(qapp: QApplication) -> None:
    edit = GrowingTextEdit()
    edit.setPlainText("Eine Zeile")
    min_height = edit.fontMetrics().lineSpacing() * MIN_VISIBLE_LINES
    assert edit.height() >= min_height


def test_growing_text_edit_min_visible_lines_can_be_overridden(
    qapp: QApplication,
) -> None:
    """A read-only display (Auftrag B2's Berichtsverlauf) must be exactly as
    tall as its content, not padded to an editor's comfortable minimum -
    passing a smaller min_visible_lines must produce a shorter box for the
    same short content."""
    small = GrowingTextEdit(min_visible_lines=1)
    small.setPlainText("Eine Zeile")
    default = GrowingTextEdit()
    default.setPlainText("Eine Zeile")

    assert small.height() < default.height()
