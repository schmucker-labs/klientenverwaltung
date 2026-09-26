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


def test_strip_disallowed_formatting_survives_multiple_runs_in_one_paragraph(
    qapp: QApplication,
) -> None:
    """Regression: pasting real formatted text from Word - many
    differently-colored/fonted runs packed into one paragraph, exactly
    what Word's clipboard HTML produces - hung (and, with more runs,
    segfaulted) the previous implementation. Mutating a fragment's
    format while a QTextBlock/fragment iterator from the same pass was
    still live invalidated it; this must now read the whole structure
    first and only mutate afterward, via stable character positions."""
    document = _document_with_html(
        '<p><span style="color:#ff0000; font-family:Calibri; font-size:12pt;">'
        "Rot </span>"
        '<span style="color:#00ff00; font-family:Arial; font-size:14pt;">'
        "<b>Gruen fett</b> </span>"
        '<span style="color:#0000ff; background-color:#ffff00; '
        'font-family:Cambria;">Blau auf Gelb </span>'
        '<span style="font-family:Times New Roman; font-size:16pt;">'
        "<i>Kursiv</i> </span>"
        '<span style="color:#123456;">Noch mehr Text </span>'
        '<span style="color:#654321; font-weight:700;">Und noch mehr</span>'
        "</p>"
    )

    strip_disallowed_formatting(document)

    html = document.toHtml()
    for forbidden in (
        "color:#ff0000",
        "color:#00ff00",
        "color:#0000ff",
        "color:#123456",
        "color:#654321",
        "background-color",
        "Calibri",
        "Arial",
        "Cambria",
        "Times New Roman",
        "12pt",
        "14pt",
        "16pt",
    ):
        assert forbidden.replace(" ", "") not in html.replace(" ", ""), (
            f"{forbidden!r} leaked: {html}"
        )
    assert "font-weight:700" in html or "font-weight:600" in html
    assert "font-style:italic" in html
