from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.models import TreatmentSession
from klientenverwaltung.services import TreatmentSessionService
from klientenverwaltung.ui.growing_text_edit import GrowingTextEdit
from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry

_GEOMETRY_SETTINGS_KEY = "client_report_history/geometry"
_SESSION_SPACING = 28


class ClientReportHistoryDialog(QDialog):
    """Read-only Berichtsverlauf (Auftrag B2): every session with a Bericht
    or Impulse, newest first, side by side, exactly as formatted when
    saved. Nothing here can be edited - the columns exist to read and
    copy from, not to change.
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

        sessions = treatment_session_service.list_sessions_with_content(client_id)

        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        for index, session in enumerate(sessions):
            if index > 0:
                content_layout.addSpacing(_SESSION_SPACING)
            content_layout.addWidget(self._build_session_panel(session))
        content_layout.addStretch()

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(content)

        close_button = QPushButton("Schließen", self)
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll_area, 1)
        layout.addLayout(close_row)

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)

    def _build_session_panel(self, session: TreatmentSession) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        heading = QLabel(
            "Sitzung vom "
            f"{session.date.strftime('%d.%m.%Y, %H:%M')} Uhr – "
            f"{session.treatment_type.name}",
            panel,
        )
        heading_font = heading.font()
        heading_font.setBold(True)
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
        layout.addWidget(self._heading_label(title, panel))
        if html:
            text_edit = GrowingTextEdit(panel)
            text_edit.setReadOnly(True)
            text_edit.setHtml(html)
            layout.addWidget(text_edit)
        else:
            layout.addWidget(QLabel("–", panel))
        layout.addStretch()
        return panel

    @staticmethod
    def _heading_label(text: str, parent: QWidget) -> QLabel:
        label = QLabel(text, parent)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        return label
