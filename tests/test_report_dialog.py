from PySide6.QtCore import QMimeData
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication

from klientenverwaltung.ui.report_dialog import (
    _GrowingTextEdit,
    strip_disallowed_formatting,
)


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


def test_strip_disallowed_formatting_removes_images_and_their_local_file_paths(
    qapp: QApplication,
) -> None:
    """Word puts pasted pictures on the clipboard as references to its temp
    folder on the laptop - stored in a report, that would keep health
    related images outside the encrypted database (and break later)."""
    document = _document_with_html(
        '<p>vor<img src="file:///C:/Users/X/AppData/Local/Temp/msohtmlclip1/01/'
        'clip_image002.png">nach</p>'
    )

    strip_disallowed_formatting(document)

    html = document.toHtml()
    assert "<img" not in html
    assert "file:///" not in html
    assert document.toPlainText() == "vornach"


def test_strip_disallowed_formatting_turns_links_into_plain_text(
    qapp: QApplication,
) -> None:
    document = _document_with_html('<p><a href="https://example.org">Link</a> Text</p>')

    strip_disallowed_formatting(document)

    html = document.toHtml()
    assert "example.org" not in html
    assert "underline" not in html
    assert document.toPlainText() == "Link Text"


def test_strip_disallowed_formatting_flattens_tables_into_paragraphs(
    qapp: QApplication,
) -> None:
    document = _document_with_html(
        "<p>vorher</p><table><tr><td><b>A</b> eins</td><td>B</td></tr>"
        "<tr><td>C</td><td></td></tr></table><p>nachher</p>"
    )

    strip_disallowed_formatting(document)

    assert "<table" not in document.toHtml()
    assert document.toPlainText() == "vorher\nA eins\nB\nC\nnachher"
    assert "font-weight:700" in document.toHtml()


def test_pasting_word_html_keeps_only_text_and_the_allowed_formatting(
    qapp: QApplication,
) -> None:
    editor = _GrowingTextEdit()
    source = QMimeData()
    source.setHtml(
        '<p style="color:red;font-family:Calibri">Befund <b>fett</b></p>'
        '<img src="file:///C:/Users/X/AppData/Local/Temp/clip.png">'
        "<table border=1><tr><td>Zelle</td></tr></table>"
        '<a href="https://example.org">Link</a>'
    )

    editor.insertFromMimeData(source)

    html = editor.toHtml()
    for leftover in ("<img", "file:///", "<table", "example.org", "Calibri"):
        assert leftover not in html
    assert "font-weight:700" in html
    assert "Zelle" in editor.toPlainText()
