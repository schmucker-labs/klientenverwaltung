from PySide6.QtCore import QMimeData, QSignalBlocker, Qt, Signal
from PySide6.QtGui import (
    QFocusEvent,
    QFont,
    QKeySequence,
    QResizeEvent,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
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
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.models import TreatmentSession
from klientenverwaltung.services import ServiceError, TreatmentSessionService
from klientenverwaltung.ui.dialogs import ask_save_discard_cancel, show_error
from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry

_GEOMETRY_SETTINGS_KEY = "report/geometry"
_MIN_VISIBLE_LINES = 8
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


def strip_disallowed_formatting(document: QTextDocument) -> None:
    """Removes foreground/background color and any explicit font family or
    point/pixel size from every character in `document`, in place.

    Bold, italic, underline and the heading level are left untouched - the
    heading level's visual size comes from a relative FontSizeAdjustment
    (see _apply_heading_level()), a different QTextFormat property than
    the absolute FontPointSize/FontPixelSize cleared here, so clearing the
    latter never undoes a heading's size.
    """
    block = document.begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            fragment = it.fragment()
            if fragment.isValid():
                fmt = fragment.charFormat()
                if any(fmt.hasProperty(prop) for prop in _STRIPPED_CHAR_PROPERTIES):
                    for prop in _STRIPPED_CHAR_PROPERTIES:
                        fmt.clearProperty(prop)
                    cursor = QTextCursor(document)
                    cursor.setPosition(fragment.position())
                    cursor.setPosition(
                        fragment.position() + fragment.length(),
                        QTextCursor.MoveMode.KeepAnchor,
                    )
                    cursor.setCharFormat(fmt)
            it += 1
        block = block.next()


class _GrowingTextEdit(QTextEdit):
    """A QTextEdit with no scrollbar of its own: it grows vertically to
    fit its content - never below _MIN_VISIBLE_LINES worth of height -
    so only the enclosing QScrollArea ever scrolls.

    Only ever gains formatting through the toolbar (bold/italic/underline/
    heading) - insertFromMimeData() strips everything else straight away,
    same as the pre-save cleanup in ReportDialog._save().
    """

    focused = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.document().documentLayout().documentSizeChanged.connect(
            self._update_height
        )
        self._update_height()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        # A width change re-wraps the text, which changes its height too -
        # documentSizeChanged alone does not reliably fire for that.
        self._update_height()

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.focused.emit()

    def insertFromMimeData(self, source: QMimeData) -> None:
        super().insertFromMimeData(source)
        strip_disallowed_formatting(self.document())

    def _update_height(self, *_args: object) -> None:
        margins = self.contentsMargins()
        frame = 2 * self.frameWidth()
        extra = (
            2 * self.document().documentMargin()
            + margins.top()
            + margins.bottom()
            + frame
        )
        min_height = self.fontMetrics().lineSpacing() * _MIN_VISIBLE_LINES + extra
        content_height = self.document().size().height() + extra
        self.setFixedHeight(int(max(min_height, content_height)))


class ReportDialog(QDialog):
    """Bericht/Impulse editor for one session.

    Formatting (Auftrag A2b) is limited to bold/italic/underline and a
    heading level, applied via the fixed toolbar at the top - never a
    text color of its own, always the active theme's.
    """

    def __init__(
        self,
        treatment_session_service: TreatmentSessionService,
        session: TreatmentSession,
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
            f"{session.treatment_type.name}",
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
        scroll_layout.addWidget(
            self._build_labeled_field("Bericht", self._report_edit)
        )
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
        button_box.accepted.connect(self._on_save_clicked)
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
        QShortcut(
            QKeySequence("Ctrl+Return"), self, activated=self._on_save_and_close
        )
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._on_save_and_close)

    def _build_toolbar(self) -> QWidget:
        self._style_combo = QComboBox(self)
        self._style_combo.addItems(_STYLE_NAMES)
        self._style_combo.currentIndexChanged.connect(self._on_style_changed)

        self._bold_button = self._make_toggle_button("F", "Fett", "Ctrl+B")
        bold_font = self._bold_button.font()
        bold_font.setBold(True)
        self._bold_button.setFont(bold_font)
        self._bold_button.clicked.connect(self._toggle_bold)

        self._italic_button = self._make_toggle_button("K", "Kursiv", "Ctrl+I")
        italic_font = self._italic_button.font()
        italic_font.setItalic(True)
        self._italic_button.setFont(italic_font)
        self._italic_button.clicked.connect(self._toggle_italic)

        self._underline_button = self._make_toggle_button(
            "U", "Unterstrichen", "Ctrl+U"
        )
        underline_font = self._underline_button.font()
        underline_font.setUnderline(True)
        self._underline_button.setFont(underline_font)
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

    def _make_toggle_button(
        self, text: str, tooltip: str, shortcut: str
    ) -> QPushButton:
        button = QPushButton(text, self)
        button.setCheckable(True)
        button.setFixedWidth(36)
        button.setToolTip(f"{tooltip} (Strg+{shortcut[-1]})")
        button.setShortcut(QKeySequence(shortcut))
        return button

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

    def _update_toolbar_state(self) -> None:
        cursor = self._active_editor.textCursor()
        char_format = cursor.charFormat()
        self._bold_button.setChecked(char_format.fontWeight() == QFont.Weight.Bold)
        self._italic_button.setChecked(char_format.fontItalic())
        self._underline_button.setChecked(char_format.fontUnderline())
        heading_level = min(cursor.blockFormat().headingLevel(), _MAX_HEADING_LEVEL)
        with QSignalBlocker(self._style_combo):
            self._style_combo.setCurrentIndex(heading_level)

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
