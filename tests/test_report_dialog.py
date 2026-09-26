from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication

from klientenverwaltung.ui.report_dialog import strip_disallowed_formatting


def _document_with_html(html: str) -> QTextDocument:
    document = QTextDocument()
    document.setHtml(html)
    return document


def test_strip_disallowed_formatting_removes_color_background_and_font(
    qapp: QApplication,
) -> None:
    document = _document_with_html(
        '<p><span style="color:#ff0000; background-color:#00ff00; '
        'font-family:Arial; font-size:20pt;">colored text</span></p>'
    )

    strip_disallowed_formatting(document)

    html = document.toHtml()
    assert "color:#ff0000" not in html.replace(" ", "")
    assert "background-color" not in html
    assert "Arial" not in html
    assert "20pt" not in html


def test_strip_disallowed_formatting_keeps_bold_italic_underline(
    qapp: QApplication,
) -> None:
    document = _document_with_html(
        '<p><span style="color:#ff0000; font-weight:700; font-style:italic; '
        'text-decoration:underline;">styled text</span></p>'
    )

    strip_disallowed_formatting(document)

    html = document.toHtml()
    assert "color:#ff0000" not in html.replace(" ", "")
    assert "font-weight:700" in html
    assert "font-style:italic" in html
    assert "text-decoration: underline" in html or "text-decoration:underline" in html


def test_strip_disallowed_formatting_keeps_heading_level_and_its_relative_size(
    qapp: QApplication,
) -> None:
    """Heading size comes from Qt's relative FontSizeAdjustment, a
    different property than the absolute FontPointSize/FontFamily this
    strips - so an already-applied heading must survive untouched."""
    document = _document_with_html(
        '<h1 style="color:#ff0000;"><span style="font-size:xx-large; '
        'font-weight:700;">Überschrift</span></h1><p>Text darunter</p>'
    )

    strip_disallowed_formatting(document)

    html = document.toHtml()
    assert "<h1" in html
    assert "font-size:xx-large" in html
    assert "color:#ff0000" not in html.replace(" ", "")


def test_strip_disallowed_formatting_is_idempotent_on_plain_content(
    qapp: QApplication,
) -> None:
    document = _document_with_html("<p>Ganz normaler Text ohne Formatierung.</p>")
    before = document.toHtml()

    strip_disallowed_formatting(document)

    assert document.toHtml() == before
