from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
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


class _GrowingTextEdit(QTextEdit):
    """A QTextEdit with no scrollbar of its own: it grows vertically to
    fit its content - never below _MIN_VISIBLE_LINES worth of height -
    so only the enclosing QScrollArea ever scrolls.
    """

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

    Auftrag A2a: plain text editing only, no formatting toolbar (that's
    A2b) - but content is still stored/loaded as HTML (toHtml/setHtml)
    since QTextEdit always round-trips through its rich-text model
    internally regardless, and A2b will need the HTML anyway.
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
        layout.addWidget(self._scroll_area, 1)
        layout.addWidget(button_box)

        self._report_edit.setHtml(session.report or "")
        self._impulses_edit.setHtml(session.impulses or "")
        self._original_report_html = self._report_edit.toHtml()
        self._original_impulses_html = self._impulses_edit.toHtml()
        self._report_edit.textChanged.connect(self._update_save_enabled)
        self._impulses_edit.textChanged.connect(self._update_save_enabled)

        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save_clicked)
        QShortcut(
            QKeySequence("Ctrl+Return"), self, activated=self._on_save_and_close
        )
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._on_save_and_close)

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

    def _is_dirty(self) -> bool:
        return (
            self._report_edit.toHtml() != self._original_report_html
            or self._impulses_edit.toHtml() != self._original_impulses_html
        )

    def _update_save_enabled(self) -> None:
        self._save_button.setEnabled(self._is_dirty())

    def _save(self) -> bool:
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
