from collections.abc import Iterator

from PySide6.QtCore import QMimeData, QSignalBlocker, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFocusEvent,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPixmap,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextDocumentFragment,
    QTextFormat,
    QTextFragment,
    QTextFrame,
    QTextTable,
)
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.services import (
    ServiceError,
    SessionEntry,
    TreatmentSessionService,
)
from klientenverwaltung.ui.dialogs import ask_save_discard_cancel, show_error
from klientenverwaltung.ui.growing_text_edit import GrowingTextEdit
from klientenverwaltung.ui.theme import ColorPalette, get_palette, load_theme_mode
from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry

_GEOMETRY_SETTINGS_KEY = "report/geometry"
_TOOLBAR_ICON_SIZE = 20
_STYLE_NAMES = ("Normal", "Überschrift 1", "Überschrift 2", "Überschrift 3")
_MAX_HEADING_LEVEL = len(_STYLE_NAMES) - 1
# A relative size step per heading level, not a stored point size - see
# _apply_heading_level(). Mirrors Qt's own rich-text editor example.
_HEADING_SIZE_ADJUSTMENT = {0: 0, 1: 3, 2: 2, 3: 1}

# Only bold/italic/underline and the heading level (via _apply_heading_level)
# are supported formatting - see docs/ui-regeln.md. Everything else a paste
# might bring in is stripped from every character format, here and before
# saving, so the text always renders in the active theme's one text color
# regardless of what was pasted.
_STRIPPED_CHAR_PROPERTIES = (
    QTextFormat.Property.ForegroundBrush,
    QTextFormat.Property.BackgroundBrush,
    QTextFormat.Property.FontFamilies,
    QTextFormat.Property.FontFamily,
    QTextFormat.Property.FontPointSize,
    QTextFormat.Property.FontPixelSize,
)


_ANCHOR_PROPERTIES = (
    QTextFormat.Property.IsAnchor,
    QTextFormat.Property.AnchorHref,
    QTextFormat.Property.AnchorName,
    # Qt styles a pasted link as underlined - that is link styling, not
    # an underline the user chose, so it goes with the link.
    QTextFormat.Property.FontUnderline,
    QTextFormat.Property.TextUnderlineStyle,
)


def strip_disallowed_formatting(document: QTextDocument) -> None:
    """Reduces `document` in place to text with bold, italic, underline and
    heading levels - everything a paste (typically from Word) may bring in
    beyond that is removed:

    - tables are flattened into one paragraph per non-empty cell, keeping
      their text and its allowed formatting;
    - images are removed: a picture pasted from Word is only a reference to
      a file in Word's temp folder on the laptop - stored in a report it
      would keep health-related images outside the encrypted database, and
      break as soon as Word cleans up;
    - links become plain text;
    - foreground/background color and any explicit font family or
      point/pixel size are cleared from every character.

    The heading level's visual size comes from a relative FontSizeAdjustment
    (see _apply_heading_level()), a different QTextFormat property than
    the absolute FontPointSize/FontPixelSize cleared here, so clearing the
    latter never undoes a heading's size. Lists are kept.

    Every step first only reads the block/fragment structure and collects
    positions, then changes the document via a plain QTextCursor - never
    interleaved. Changing a format or the text while a QTextBlock/fragment
    iterator is still in use invalidates that iterator - Qt restructures
    the block's internal fragment map on every change - which hung
    (observed) or crashed (reported with real, multi-run Word paste
    content) rather than raising a catchable Python exception.
    """
    _flatten_tables(document)
    _remove_images(document)

    ranges_to_clear: list[tuple[int, int, QTextCharFormat]] = []
    for fragment in _fragments(document):
        fmt = fragment.charFormat()
        is_link = fmt.isAnchor() or fmt.hasProperty(QTextFormat.Property.AnchorHref)
        if is_link or any(fmt.hasProperty(prop) for prop in _STRIPPED_CHAR_PROPERTIES):
            for prop in _STRIPPED_CHAR_PROPERTIES:
                fmt.clearProperty(prop)
            if is_link:
                for prop in _ANCHOR_PROPERTIES:
                    fmt.clearProperty(prop)
            ranges_to_clear.append(
                (fragment.position(), fragment.position() + fragment.length(), fmt)
            )

    # Format-only changes: character positions stay valid throughout.
    cursor = QTextCursor(document)
    for start, end, fmt in ranges_to_clear:
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(fmt)


def _fragments(document: QTextDocument) -> list[QTextFragment]:
    fragments: list[QTextFragment] = []
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid():
                fragments.append(fragment)
            it += 1
        block = block.next()
    return fragments


def _remove_images(document: QTextDocument) -> None:
    image_ranges = [
        (fragment.position(), fragment.length())
        for fragment in _fragments(document)
        if fragment.charFormat().isImageFormat()
    ]
    cursor = QTextCursor(document)
    # Back to front, so removing one never shifts the ones still to come.
    for start, length in reversed(image_ranges):
        cursor.setPosition(start)
        cursor.setPosition(start + length, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()


def _tables(frame: QTextFrame) -> Iterator[QTextTable]:
    for child in frame.childFrames():
        if isinstance(child, QTextTable):
            yield child
        yield from _tables(child)


def _flatten_tables(document: QTextDocument) -> None:
    """Replaces every table - nested ones first - by one paragraph per
    non-empty cell (row by row), keeping the cells' text and formatting."""
    # Bounded by the number of tables at the start - each pass removes one,
    # so this can never spin forever should a removal ever not take effect.
    for _ in range(len(list(_tables(document.rootFrame())))):
        tables = list(_tables(document.rootFrame()))
        if not tables:
            break
        table = max(tables, key=lambda candidate: candidate.firstPosition())
        cell_contents: list[QTextDocumentFragment] = []
        for row in range(table.rows()):
            for column in range(table.columns()):
                cell = table.cellAt(row, column)
                cell_cursor = cell.firstCursorPosition()
                cell_cursor.setPosition(
                    cell.lastPosition(), QTextCursor.MoveMode.KeepAnchor
                )
                if cell_cursor.selectedText().strip():
                    cell_contents.append(cell_cursor.selection())

        cursor = QTextCursor(document)
        # The table's frame starts one position before its first cell and
        # ends one after its last - that whole range is the table.
        cursor.setPosition(table.firstPosition() - 1)
        cursor.setPosition(table.lastPosition() + 1, QTextCursor.MoveMode.KeepAnchor)
        cursor.beginEditBlock()
        cursor.removeSelectedText()
        # Removing the frame joins the paragraphs around it - separate them
        # again from the flattened cells.
        if not cursor.atBlockStart():
            cursor.insertBlock()
        for index, content in enumerate(cell_contents):
            if index:
                cursor.insertBlock()
            cursor.insertFragment(content)
        if not cursor.atBlockEnd():
            cursor.insertBlock()
        cursor.endEditBlock()


class _GrowingTextEdit(GrowingTextEdit):
    """Adds editing-only behavior on top of GrowingTextEdit: a focus
    signal for toolbar active-editor tracking, and paste-format
    stripping. Only ever gains formatting through the toolbar
    (bold/italic/underline/heading) - insertFromMimeData() strips
    everything else straight away, same as the pre-save cleanup in
    ReportDialog._save().
    """

    focused = Signal()

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.focused.emit()

    def insertFromMimeData(self, source: QMimeData) -> None:
        super().insertFromMimeData(source)
        strip_disallowed_formatting(self.document())


class ReportDialog(QDialog):
    """Bericht/Impulse editor for one session.

    Formatting (Auftrag A2b) is limited to bold/italic/underline and a
    heading level, applied via the fixed toolbar at the top - never a
    text color of its own, always the active theme's.
    """

    def __init__(
        self,
        treatment_session_service: TreatmentSessionService,
        session: SessionEntry,
        client_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._treatment_session_service = treatment_session_service
        self._session_id = session.id

        self.setWindowTitle(f"Bericht: {client_name}")
        self.setModal(True)
        self.resize(700, 700)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        heading = QLabel(
            "Bericht zur Sitzung vom "
            f"{session.date.strftime('%d.%m.%Y, %H:%M')} Uhr – "
            f"{session.treatment_type_name}",
            self,
        )
        heading.setWordWrap(True)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading.setFont(heading_font)

        self._report_edit = _GrowingTextEdit(self)
        self._impulses_edit = _GrowingTextEdit(self)
        self._active_editor: _GrowingTextEdit = self._report_edit

        toolbar = self._build_toolbar()

        scroll_content = QWidget(self)
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.addWidget(self._build_labeled_field("Bericht", self._report_edit))
        scroll_layout.addWidget(
            self._build_labeled_field("Impulse", self._impulses_edit)
        )
        scroll_layout.addStretch()

        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setWidget(scroll_content)

        self._make_cursor_follow_scroll(self._report_edit)
        self._make_cursor_follow_scroll(self._impulses_edit)
        self._connect_toolbar_state_signals(self._report_edit)
        self._connect_toolbar_state_signals(self._impulses_edit)

        button_box = QDialogButtonBox(self)
        self._save_button: QPushButton = button_box.addButton(
            "Speichern", QDialogButtonBox.ButtonRole.AcceptRole
        )
        button_box.addButton("Abbrechen", QDialogButtonBox.ButtonRole.RejectRole)
        self._save_button.setEnabled(False)
        button_box.accepted.connect(self._on_save_and_close)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(toolbar)
        layout.addWidget(self._scroll_area, 1)
        layout.addWidget(button_box)

        self._report_edit.setHtml(session.report or "")
        self._impulses_edit.setHtml(session.impulses or "")
        self._original_report_html = self._report_edit.toHtml()
        self._original_impulses_html = self._impulses_edit.toHtml()
        self._report_edit.textChanged.connect(self._update_save_enabled)
        self._impulses_edit.textChanged.connect(self._update_save_enabled)
        self._update_toolbar_state()

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save_clicked)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._on_save_and_close)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._on_save_and_close)

    def _build_toolbar(self) -> QWidget:
        self._style_combo = QComboBox(self)
        self._style_combo.addItems(_STYLE_NAMES)
        self._style_combo.currentIndexChanged.connect(self._on_style_changed)
        # The combo needs focus to open its popup at all, so - unlike the
        # NoFocus toggle buttons - it can't avoid taking focus. Give it back
        # to whichever field was active as soon as a real selection is made
        # (activated, not currentIndexChanged - the latter also fires for
        # our own programmatic updates in _update_toolbar_state()).
        self._style_combo.activated.connect(self._return_focus_to_active_editor)

        # Current theme only: this dialog is application-modal, so the
        # user cannot reach the main window's theme toggle while it is
        # open - no live-refresh path is needed for these icons.
        palette = get_palette(load_theme_mode())

        self._bold_button, self._bold_icons = self._make_letter_button(
            "F", "Fett", "Ctrl+B", palette, bold=True
        )
        self._bold_button.clicked.connect(self._toggle_bold)

        self._italic_button, self._italic_icons = self._make_letter_button(
            "K",
            "Kursiv",
            "Ctrl+I",
            palette,
            italic=True,
            weight=QFont.Weight.DemiBold,
            point_size_delta=2,
        )
        self._italic_button.clicked.connect(self._toggle_italic)

        self._underline_button, self._underline_icons = self._make_letter_button(
            "U",
            "Unterstrichen",
            "Ctrl+U",
            palette,
            underline=True,
            weight=QFont.Weight.DemiBold,
            point_size_delta=2,
        )
        self._underline_button.clicked.connect(self._toggle_underline)

        row = QHBoxLayout()
        row.addWidget(self._style_combo)
        row.addWidget(self._bold_button)
        row.addWidget(self._italic_button)
        row.addWidget(self._underline_button)
        row.addStretch()

        toolbar = QWidget(self)
        toolbar.setLayout(row)
        return toolbar

    def _make_letter_button(
        self,
        letter: str,
        tooltip: str,
        shortcut: str,
        palette: ColorPalette,
        *,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        weight: QFont.Weight | None = None,
        point_size_delta: int = 0,
    ) -> tuple[QPushButton, tuple[QIcon, QIcon]]:
        """A checkable button showing `letter` as an icon (not text) - see
        _render_letter_icon() for why. Returns the button plus its
        (unchecked, checked) icon pair, one in the theme's normal text
        color and one in its checked/on-accent contrast color, so
        _update_toolbar_state() can swap between them without re-rendering.
        """
        button = QPushButton(self)
        button.setCheckable(True)
        button.setFixedWidth(36)
        button.setIconSize(QSize(_TOOLBAR_ICON_SIZE, _TOOLBAR_ICON_SIZE))
        button.setToolTip(f"{tooltip} (Strg+{shortcut[-1]})")
        # The letter is an icon, not text - name it for screen readers.
        button.setAccessibleName(tooltip)
        button.setShortcut(QKeySequence(shortcut))
        # Never takes keyboard focus, so clicking it (or its shortcut) never
        # moves focus out of whichever text field is being edited - the
        # shortcut still works via the window-wide QShortcut context, and a
        # mouse click still activates the button regardless of focus policy.
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        font_kwargs = {
            "bold": bold,
            "italic": italic,
            "underline": underline,
            "weight": weight,
            "point_size_delta": point_size_delta,
        }
        icons = (
            self._render_letter_icon(letter, color=palette.text, **font_kwargs),
            self._render_letter_icon(
                letter, color=palette.surface_panel, **font_kwargs
            ),
        )
        button.setIcon(icons[0])
        return button, icons

    def _render_letter_icon(
        self,
        letter: str,
        *,
        color: str,
        bold: bool = False,
        italic: bool = False,
        underline: bool = False,
        weight: QFont.Weight | None = None,
        point_size_delta: int = 0,
    ) -> QIcon:
        """Renders `letter` offscreen onto a transparent pixmap, in `color`.

        QFont.StyleStrategy.NoSubpixelAntialias alone does not reliably
        stop ClearType from fringing the thin diagonal strokes of an
        italic K, or U's underline bar, with visible orange/blue color -
        Windows' native DirectWrite text backend does not honor it for a
        widget's own natively drawn label. Painting the glyph offscreen
        onto an alpha-blended QPixmap instead sidesteps the question
        entirely: subpixel/ClearType rendering fundamentally requires
        compositing against known-opaque screen pixels, so Qt's raster
        engine always falls back to plain grayscale antialiasing here,
        regardless of style strategy.
        """
        font = QFont(self.font())
        if bold:
            font.setBold(True)
        if weight is not None:
            font.setWeight(weight)
        if italic:
            font.setItalic(True)
        if underline:
            font.setUnderline(True)
        if point_size_delta and font.pointSize() > 0:
            font.setPointSize(font.pointSize() + point_size_delta)

        pixmap = QPixmap(_TOOLBAR_ICON_SIZE, _TOOLBAR_ICON_SIZE)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(font)
        painter.setPen(QColor(color))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, letter)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _build_labeled_field(label_text: str, field: QTextEdit) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.addWidget(QLabel(label_text, panel))
        layout.addWidget(field)
        return panel

    def _make_cursor_follow_scroll(self, text_edit: QTextEdit) -> None:
        def _on_cursor_moved() -> None:
            rect = text_edit.cursorRect()
            point = text_edit.mapTo(self._scroll_area.widget(), rect.center())
            self._scroll_area.ensureVisible(point.x(), point.y(), 5, rect.height())

        text_edit.cursorPositionChanged.connect(_on_cursor_moved)

    def _connect_toolbar_state_signals(self, editor: _GrowingTextEdit) -> None:
        editor.focused.connect(lambda: self._set_active_editor(editor))
        editor.cursorPositionChanged.connect(self._update_toolbar_state)
        editor.currentCharFormatChanged.connect(
            lambda _fmt: self._update_toolbar_state()
        )

    def _set_active_editor(self, editor: _GrowingTextEdit) -> None:
        self._active_editor = editor
        self._update_toolbar_state()

    def _return_focus_to_active_editor(self, _index: int) -> None:
        self._active_editor.setFocus()

    def _update_toolbar_state(self) -> None:
        """Reflects the active editor's format at the cursor in the
        toolbar. Blocks every widget's own signals while doing so - this
        only ever displays the current state, it must never itself count
        as a user action that re-triggers a format change or a focus
        hand-back.
        """
        cursor = self._active_editor.textCursor()
        char_format = cursor.charFormat()
        heading_level = min(cursor.blockFormat().headingLevel(), _MAX_HEADING_LEVEL)
        bold_active = char_format.fontWeight() == QFont.Weight.Bold
        italic_active = char_format.fontItalic()
        underline_active = char_format.fontUnderline()
        with (
            QSignalBlocker(self._bold_button),
            QSignalBlocker(self._italic_button),
            QSignalBlocker(self._underline_button),
            QSignalBlocker(self._style_combo),
        ):
            self._bold_button.setChecked(bold_active)
            self._italic_button.setChecked(italic_active)
            self._underline_button.setChecked(underline_active)
            self._style_combo.setCurrentIndex(heading_level)
        self._bold_button.setIcon(self._bold_icons[bold_active])
        self._italic_button.setIcon(self._italic_icons[italic_active])
        self._underline_button.setIcon(self._underline_icons[underline_active])

    def _toggle_bold(self) -> None:
        editor = self._active_editor
        is_bold = editor.fontWeight() == QFont.Weight.Bold
        editor.setFontWeight(QFont.Weight.Normal if is_bold else QFont.Weight.Bold)
        self._update_toolbar_state()

    def _toggle_italic(self) -> None:
        editor = self._active_editor
        editor.setFontItalic(not editor.fontItalic())
        self._update_toolbar_state()

    def _toggle_underline(self) -> None:
        editor = self._active_editor
        editor.setFontUnderline(not editor.fontUnderline())
        self._update_toolbar_state()

    def _on_style_changed(self, index: int) -> None:
        self._apply_heading_level(self._active_editor, index)
        self._update_toolbar_state()

    @staticmethod
    def _apply_heading_level(editor: QTextEdit, level: int) -> None:
        """Applies `level` (0 = Normal, 1-3 = Überschrift 1-3) to the whole
        block the cursor is in, the same unit Qt itself treats a heading
        as. The visual size comes from a relative FontSizeAdjustment, not
        an absolute point size, so later stripping FontPointSize (paste,
        pre-save cleanup) never undoes it; switching back to Normal resets
        both to plain weight/size for that block.
        """
        cursor = editor.textCursor()
        cursor.beginEditBlock()
        block_format = cursor.blockFormat()
        block_format.setHeadingLevel(level)
        cursor.mergeBlockFormat(block_format)

        char_format = QTextCharFormat()
        char_format.setFontWeight(QFont.Weight.Bold if level else QFont.Weight.Normal)
        char_format.setProperty(
            QTextFormat.Property.FontSizeAdjustment, _HEADING_SIZE_ADJUSTMENT[level]
        )
        cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        cursor.mergeCharFormat(char_format)
        # The editor's own (unmoved) live cursor, so typing right after
        # switching style continues in the same format.
        editor.mergeCurrentCharFormat(char_format)
        cursor.endEditBlock()

    def _is_dirty(self) -> bool:
        return (
            self._report_edit.toHtml() != self._original_report_html
            or self._impulses_edit.toHtml() != self._original_impulses_html
        )

    def _update_save_enabled(self) -> None:
        self._save_button.setEnabled(self._is_dirty())

    def _save(self) -> bool:
        strip_disallowed_formatting(self._report_edit.document())
        strip_disallowed_formatting(self._impulses_edit.document())
        try:
            self._treatment_session_service.save_report(
                self._session_id,
                report=self._report_edit.toHtml(),
                impulses=self._impulses_edit.toHtml(),
            )
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return False
        self._original_report_html = self._report_edit.toHtml()
        self._original_impulses_html = self._impulses_edit.toHtml()
        self._update_save_enabled()
        return True

    def _on_save_clicked(self) -> None:
        self._save()

    def _on_save_and_close(self) -> None:
        if self._is_dirty() and not self._save():
            return
        self.accept()

    def reject(self) -> None:
        if not self._is_dirty():
            super().reject()
            return
        choice = ask_save_discard_cancel(
            "Es gibt ungespeicherte Änderungen am Bericht.", parent=self
        )
        if choice == "cancel":
            return
        if choice == "discard":
            super().reject()
            return
        if self._save():
            super().reject()

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)
