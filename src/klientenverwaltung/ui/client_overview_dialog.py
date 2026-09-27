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

from klientenverwaltung.models import Client
from klientenverwaltung.services import (
    ClientService,
    MediaService,
    TreatmentSessionService,
    TreatmentTypeService,
)
from klientenverwaltung.ui.client_detail_dialog import ClientDetailDialog
from klientenverwaltung.ui.client_report_history_dialog import (
    ClientReportHistoryDialog,
)
from klientenverwaltung.ui.client_sessions_dialog import ClientSessionsDialog
from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry

_GEOMETRY_SETTINGS_KEY = "client_overview/geometry"
_SECTION_SPACING = 18


class ClientOverviewDialog(QDialog):
    """Read-only Klientenübersicht (Auftrag B1) - no input fields, just a
    letter-style summary of a client's data. "Sitzungen"/"Bearbeiten" open
    the existing dialogs and this view reloads its content afterwards, so
    it never shows stale data, counts or a stale window title.
    """

    def __init__(
        self,
        client_service: ClientService,
        treatment_type_service: TreatmentTypeService,
        treatment_session_service: TreatmentSessionService,
        media_service: MediaService,
        client_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._client_service = client_service
        self._treatment_type_service = treatment_type_service
        self._treatment_session_service = treatment_session_service
        self._media_service = media_service
        self._client_id = client_id

        self.resize(650, 700)
        self.setModal(True)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        self._archived_label = QLabel("Archiviert", self)
        archived_font = self._archived_label.font()
        archived_font.setBold(True)
        self._archived_label.setFont(archived_font)

        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self._report_button = QPushButton(self)
        self._sessions_button = QPushButton(self)
        self._edit_button = QPushButton("Bearbeiten", self)
        close_button = QPushButton("Schließen", self)
        close_button.setDefault(True)
        self._report_button.clicked.connect(self._on_report_clicked)
        self._sessions_button.clicked.connect(self._on_sessions_clicked)
        self._edit_button.clicked.connect(self._on_edit_clicked)
        close_button.clicked.connect(self.accept)

        button_row = QHBoxLayout()
        button_row.addWidget(self._report_button)
        button_row.addWidget(self._sessions_button)
        button_row.addStretch()
        button_row.addWidget(self._edit_button)
        button_row.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._archived_label)
        layout.addWidget(self._scroll_area, 1)
        layout.addLayout(button_row)

        self._reload()

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)

    def _reload(self) -> None:
        client = self._client_service.get_client(self._client_id)
        self.setWindowTitle(f"Klient: {client.first_name} {client.last_name}")
        self._archived_label.setVisible(client.archived)
        self._scroll_area.setWidget(self._build_content(client))
        self._update_buttons(client)

    def _update_buttons(self, client: Client) -> None:
        sessions = self._treatment_session_service.list_sessions_for_client(client.id)
        self._sessions_button.setText(f"Sitzungen ({len(sessions)})")

        report_count = len(
            self._treatment_session_service.list_sessions_with_content(client.id)
        )
        self._report_button.setText(f"Berichte ({report_count})")
        self._report_button.setEnabled(report_count > 0)
        self._report_button.setToolTip(
            "Noch kein Bericht vorhanden" if report_count == 0 else ""
        )

    def _build_content(self, client: Client) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)

        layout.addWidget(self._build_address_block(client))
        layout.addSpacing(_SECTION_SPACING)
        layout.addWidget(self._build_birth_and_since_lines(client))

        concern_section = self._build_text_section("Anliegen", client.concern)
        if concern_section is not None:
            layout.addSpacing(_SECTION_SPACING)
            layout.addWidget(concern_section)

        notes_section = self._build_text_section("Notizen", client.notes)
        if notes_section is not None:
            layout.addSpacing(_SECTION_SPACING)
            layout.addWidget(notes_section)

        further_section = self._build_further_details(client)
        if further_section is not None:
            layout.addSpacing(_SECTION_SPACING)
            layout.addWidget(further_section)

        layout.addSpacing(_SECTION_SPACING)
        layout.addWidget(self._build_session_dates(client))
        layout.addStretch()
        return content

    def _build_address_block(self, client: Client) -> QWidget:
        block = self._client_service.build_address_block(client)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        name_label = QLabel(block.name_line, panel)
        name_font = name_label.font()
        name_font.setBold(True)
        name_font.setPointSize(name_font.pointSize() + 2)
        name_label.setFont(name_font)
        layout.addWidget(name_label)

        for line in block.lines:
            layout.addWidget(QLabel(line, panel))

        if block.contact_lines:
            layout.addSpacing(_SECTION_SPACING // 2)
            for line in block.contact_lines:
                layout.addWidget(QLabel(line, panel))

        return panel

    def _build_birth_and_since_lines(self, client: Client) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        if client.birth_date is not None:
            age = self._client_service.compute_age(client.birth_date)
            layout.addWidget(
                QLabel(
                    f"Geburtsdatum: {client.birth_date.strftime('%d.%m.%Y')} "
                    f"({age} Jahre)",
                    panel,
                )
            )
        since_date = self._client_service.client_since_date(client.created_at)
        layout.addWidget(
            QLabel(f"Klient seit: {since_date.strftime('%d.%m.%Y')}", panel)
        )
        return panel

    def _build_text_section(self, title: str, text: str | None) -> QWidget | None:
        if not text:
            return None
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._heading_label(title, panel))
        content_label = QLabel(text, panel)
        content_label.setWordWrap(True)
        layout.addWidget(content_label)
        return panel

    def _build_further_details(self, client: Client) -> QWidget | None:
        if not client.referral_source and not client.consent_date:
            return None
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._heading_label("Weitere Angaben", panel))
        if client.referral_source:
            layout.addWidget(
                QLabel(f"Aufmerksam geworden durch: {client.referral_source}", panel)
            )
        if client.consent_date:
            layout.addWidget(
                QLabel(
                    "Datenschutz-Einwilligung vom: "
                    f"{client.consent_date.strftime('%d.%m.%Y')}",
                    panel,
                )
            )
        return panel

    def _build_session_dates(self, client: Client) -> QWidget:
        summary = self._treatment_session_service.get_session_summary(client.id)
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            QLabel(
                "Letzte Sitzung: "
                + (
                    summary.last_session_date.strftime("%d.%m.%Y")
                    if summary.last_session_date is not None
                    else "keine"
                ),
                panel,
            )
        )
        layout.addWidget(
            QLabel(
                "Nächster Termin: "
                + (
                    summary.next_session_date.strftime("%d.%m.%Y")
                    if summary.next_session_date is not None
                    else "keiner"
                ),
                panel,
            )
        )
        return panel

    @staticmethod
    def _heading_label(text: str, parent: QWidget) -> QLabel:
        label = QLabel(text, parent)
        font = label.font()
        font.setBold(True)
        label.setFont(font)
        return label

    def _on_report_clicked(self) -> None:
        client = self._client_service.get_client(self._client_id)
        client_name = f"{client.first_name} {client.last_name}"
        dialog = ClientReportHistoryDialog(
            self._treatment_session_service,
            self._client_id,
            client_name,
            parent=self,
        )
        dialog.exec()

    def _on_sessions_clicked(self) -> None:
        client = self._client_service.get_client(self._client_id)
        client_name = f"{client.first_name} {client.last_name}"
        dialog = ClientSessionsDialog(
            self._treatment_type_service,
            self._treatment_session_service,
            self._media_service,
            self._client_id,
            client_name,
            parent=self,
        )
        dialog.exec()
        self._reload()

    def _on_edit_clicked(self) -> None:
        dialog = ClientDetailDialog(
            self._client_service,
            self._treatment_type_service,
            self._treatment_session_service,
            self._media_service,
            self._client_id,
            parent=self,
        )
        dialog.exec()
        self._reload()
