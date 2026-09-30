from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.services import SessionEntry, TreatmentSessionService
from klientenverwaltung.ui.buttons import window_row
from klientenverwaltung.ui.growing_text_edit import GrowingTextEdit
from klientenverwaltung.ui.scrollbar_gap import (
    apply_scrollbar_gap,
    keep_clear_of_scrollbar,
)
from klientenverwaltung.ui.sorting import german_sort_key
from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry

_GEOMETRY_SETTINGS_KEY = "client_report_history/geometry"
_OLDEST_FIRST_SETTINGS_KEY = "client_report_history/oldest_first"


class ClientReportHistoryDialog(QDialog):
    """Read-only Berichtsverlauf (Auftrag B2): every session with a Bericht
    or Impulse, side by side, exactly as formatted when saved. Nothing here
    can be edited - the columns exist to read and copy from, not to change.

    The row above the list narrows it down to one Behandlungsart and turns
    the order around (newest first unless chosen otherwise; the order is
    remembered, the Behandlungsart is not - it differs from client to
    client).
    """

    def __init__(
        self,
        treatment_session_service: TreatmentSessionService,
        client_id: int,
        client_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle(f"Berichte: {client_name}")
        self.setModal(True)
        self.resize(1000, 700)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        # Newest first, as the service delivers them.
        self._sessions = treatment_session_service.list_sessions_with_content(client_id)

        # Only the types this client has reports for - any other choice
        # could only ever produce an empty list.
        self._type_combo = QComboBox(self)
        self._type_combo.addItem("Alle Behandlungsarten", None)
        type_names = {
            session.treatment_type_id: session.treatment_type_name
            for session in self._sessions
        }
        for type_id, name in sorted(
            type_names.items(), key=lambda item: german_sort_key(item[1])
        ):
            self._type_combo.addItem(name, type_id)

        self._order_combo = QComboBox(self)
        self._order_combo.addItem("Absteigend (neueste zuerst)", False)
        self._order_combo.addItem("Aufsteigend (älteste zuerst)", True)
        oldest_first = QSettings().value(_OLDEST_FIRST_SETTINGS_KEY, False, type=bool)
        self._order_combo.setCurrentIndex(self._order_combo.findData(oldest_first))

        self._type_combo.currentIndexChanged.connect(self._show_sessions)
        self._order_combo.currentIndexChanged.connect(self._on_order_changed)

        layout = QVBoxLayout(self)
        # See docs/ui-regeln.md: the dialog's margin between its blocks.
        self._gutter = layout.contentsMargins().right()
        layout.setSpacing(self._gutter)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Behandlungsart:", self))
        filter_row.addWidget(self._type_combo)
        filter_row.addSpacing(2 * self._gutter)
        filter_row.addWidget(QLabel("Sortieren nach Datum:", self))
        filter_row.addWidget(self._order_combo)
        filter_row.addStretch()

        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        keep_clear_of_scrollbar(self._scroll_area, self._gutter)

        close_button = QPushButton("Schließen", self)
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)

        layout.addLayout(filter_row)
        layout.addWidget(self._scroll_area, 1)
        layout.addWidget(window_row(close_button))

        self._show_sessions()

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)

    def _on_order_changed(self) -> None:
        QSettings().setValue(
            _OLDEST_FIRST_SETTINGS_KEY, bool(self._order_combo.currentData())
        )
        self._show_sessions()

    def _show_sessions(self) -> None:
        """(Re)builds the list for the chosen Behandlungsart and order -
        from the sessions loaded when the dialog opened; nothing can change
        them while this modal, read-only dialog is up."""
        type_id = self._type_combo.currentData()
        sessions = [
            session
            for session in self._sessions
            if type_id is None or session.treatment_type_id == type_id
        ]
        if self._order_combo.currentData():
            sessions.reverse()

        content = QWidget()
        content_layout = QVBoxLayout(content)
        # Starts at the same left edge as the row above it.
        content_layout.setContentsMargins(0, 0, 0, 0)
        # Twice the margin above and below each divider line: any closer
        # and it reads as a second border of the field above it.
        content_layout.setSpacing(2 * self._gutter)
        for index, session in enumerate(sessions):
            if index > 0:
                content_layout.addWidget(self._build_divider(content))
            content_layout.addWidget(self._build_session_panel(session))
        # With a factor, so it alone takes up a taller window's spare height -
        # otherwise the session panels share it and drift apart.
        content_layout.addStretch(1)

        # Replaces (and deletes) the previous list; back to the top.
        self._scroll_area.setWidget(content)
        apply_scrollbar_gap(self._scroll_area, self._gutter)

    @staticmethod
    def _build_divider(parent: QWidget) -> QFrame:
        """A hairline between two sessions; the theme colors it like the
        fields' borders (QFrame[divider="true"])."""
        divider = QFrame(parent)
        divider.setProperty("divider", True)
        divider.setFixedHeight(1)
        return divider

    def _build_session_panel(self, session: SessionEntry) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        # The one thing to find when scanning the list: larger than
        # everything else, like the name on the Klientenübersicht.
        heading = QLabel(
            "Sitzung vom "
            f"{session.date.strftime('%d.%m.%Y, %H:%M')} Uhr – "
            f"{session.treatment_type_name}",
            panel,
        )
        heading.setWordWrap(True)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading_font.setPointSize(heading_font.pointSize() + 2)
        heading.setFont(heading_font)
        layout.addWidget(heading)

        columns = QHBoxLayout()
        columns.addWidget(self._build_column("Bericht", session.report), 1)
        columns.addWidget(self._build_column("Impulse", session.impulses), 1)
        layout.addLayout(columns)

        return panel

    def _build_column(self, title: str, html: str | None) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        # Secondary, not bold: a caption for the field below it, clearly
        # below the session's heading in rank.
        caption = QLabel(title, panel)
        caption.setProperty("secondary", True)
        layout.addWidget(caption)
        if html:
            # min_visible_lines=1, not the editor's default comfortable
            # minimum: this is a read-only display that must be exactly as
            # tall as its content (Auftrag B2), not padded with blank space.
            text_edit = GrowingTextEdit(panel, min_visible_lines=1)
            text_edit.setReadOnly(True)
            text_edit.setHtml(html)
            layout.addWidget(text_edit)
        else:
            layout.addWidget(QLabel("–", panel))
        layout.addStretch()
        return panel
