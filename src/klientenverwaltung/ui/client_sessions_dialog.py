from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.models import TreatmentSession
from klientenverwaltung.services import (
    MediaService,
    ServiceError,
    TreatmentSessionService,
    TreatmentTypeService,
)
from klientenverwaltung.ui.dialogs import (
    ask_confirm_delete,
    ask_create_treatment_type,
    show_error,
)
from klientenverwaltung.ui.media_cleanup import offer_to_delete_now_unused_media
from klientenverwaltung.ui.media_dialog import MediaDialog
from klientenverwaltung.ui.report_dialog import ReportDialog
from klientenverwaltung.ui.session_dialog import SessionDialog
from klientenverwaltung.ui.session_table_model import (
    COLUMN_TITLES,
    MEDIA_COLUMN,
    REPORT_COLUMN,
    SessionTableModel,
)
from klientenverwaltung.ui.treatment_type_management_dialog import (
    TreatmentTypeManagementDialog,
)
from klientenverwaltung.ui.window_settings import (
    finalize_column_widths,
    restore_geometry,
    restore_header_state,
    save_geometry,
    save_header_state,
)

_GEOMETRY_SETTINGS_KEY = "client_sessions/geometry"
_TABLE_HEADER_SETTINGS_KEY = "client_detail/session_table_header_state"


class ClientSessionsDialog(QDialog):
    """A client's session history in its own window - split out of
    ClientDetailDialog (see its docstring) because the two together no
    longer fit on a small screen."""

    def __init__(
        self,
        treatment_type_service: TreatmentTypeService,
        treatment_session_service: TreatmentSessionService,
        media_service: MediaService,
        client_id: int,
        client_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._treatment_type_service = treatment_type_service
        self._treatment_session_service = treatment_session_service
        self._media_service = media_service
        self._client_id = client_id
        self._client_name = client_name

        self.setWindowTitle(f"Sitzungen: {client_name}")
        self.setModal(True)
        self.resize(650, 450)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        self._build_ui()

    def _build_ui(self) -> None:
        self._session_table_model = SessionTableModel()
        # Populated before resizeColumnsToContents() below, which otherwise
        # only has the (much shorter) column headers to measure against on
        # an empty model, and would size the Datum column too narrow to
        # show a real date once sessions are loaded.
        sessions = self._treatment_session_service.list_sessions_for_client(
            self._client_id
        )
        self._session_table_model.set_sessions(sessions, self._media_counts_for(sessions))
        self._session_table_view = QTableView(self)
        self._session_table_view.setModel(self._session_table_model)
        self._session_table_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._session_table_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._session_table_view.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        session_header = self._session_table_view.horizontalHeader()
        self._session_table_view.verticalHeader().setVisible(False)
        restored = restore_header_state(
            session_header, _TABLE_HEADER_SETTINGS_KEY, COLUMN_TITLES
        )
        if not restored:
            self._session_table_view.resizeColumnsToContents()
            self._session_table_view.setColumnWidth(MEDIA_COLUMN, 60)
            self._session_table_view.setColumnWidth(REPORT_COLUMN, 60)
        # Behandlungsart (treatment type name) is the one open-ended,
        # variable-length column, so it gets the remaining space rather than
        # stretching whichever column happens to be last - Bericht is last
        # and must stay a narrow, fixed-width checkmark column.
        finalize_column_widths(
            session_header, self._session_table_model.columnCount(), 1, restored
        )
        session_header.sectionResized.connect(self._save_table_header_state)
        self._session_table_view.selectionModel().selectionChanged.connect(
            self._update_button_states
        )

        self._media_button = QPushButton("Medien", self)
        self._report_button = QPushButton("Bericht", self)
        self._new_session_button = QPushButton("Neue Sitzung", self)
        self._edit_session_button = QPushButton("Bearbeiten", self)
        self._delete_session_button = QPushButton("Löschen", self)
        self._media_button.setEnabled(False)
        self._report_button.setEnabled(False)
        self._edit_session_button.setEnabled(False)
        self._delete_session_button.setEnabled(False)
        self._media_button.clicked.connect(self._on_media_clicked)
        self._report_button.clicked.connect(self._on_report_clicked)
        self._new_session_button.clicked.connect(self._on_new_session_clicked)
        self._edit_session_button.clicked.connect(self._on_edit_session_clicked)
        self._delete_session_button.clicked.connect(self._on_delete_session_clicked)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self._media_button)
        button_row.addWidget(self._report_button)
        button_row.addWidget(self._new_session_button)
        button_row.addWidget(self._edit_session_button)
        button_row.addWidget(self._delete_session_button)

        close_button = QPushButton("Schließen", self)
        close_button.clicked.connect(self.accept)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._session_table_view, 1)
        layout.addLayout(button_row)
        layout.addLayout(close_row)

    def _save_table_header_state(self) -> None:
        save_header_state(
            self._session_table_view.horizontalHeader(),
            _TABLE_HEADER_SETTINGS_KEY,
            COLUMN_TITLES,
        )

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)

    def _media_counts_for(self, sessions: list[TreatmentSession]) -> dict[int, int]:
        return self._media_service.count_media_for_sessions(
            [session.id for session in sessions]
        )

    def _reload_sessions(self) -> None:
        sessions = self._treatment_session_service.list_sessions_for_client(
            self._client_id
        )
        self._session_table_model.set_sessions(sessions, self._media_counts_for(sessions))
        self._update_button_states()

    def _selected_session(self) -> TreatmentSession | None:
        rows = self._session_table_view.selectionModel().selectedRows()
        if len(rows) != 1:
            return None
        return self._session_table_model.session_at(rows[0].row())

    def _update_button_states(self) -> None:
        has_selection = self._selected_session() is not None
        self._media_button.setEnabled(has_selection)
        self._report_button.setEnabled(has_selection)
        self._edit_session_button.setEnabled(has_selection)
        self._delete_session_button.setEnabled(has_selection)

    def _on_media_clicked(self) -> None:
        session = self._selected_session()
        if session is None:
            return
        dialog = MediaDialog(
            self._media_service, session, self._client_name, parent=self
        )
        dialog.exec()
        self._reload_sessions()

    def _on_report_clicked(self) -> None:
        session = self._selected_session()
        if session is None:
            return
        dialog = ReportDialog(
            self._treatment_session_service, session, self._client_name, parent=self
        )
        # Always reload, not just on Accepted: Strg+S saves without closing,
        # and even the "Abbrechen" -> "Speichern" prompt path can save
        # before returning Rejected - so the dialog's result alone can't
        # tell us whether the report checkmark needs to be refreshed.
        dialog.exec()
        self._reload_sessions()

    def _on_new_session_clicked(self) -> None:
        if not self._ensure_active_treatment_type_exists():
            return
        dialog = SessionDialog(
            self._treatment_type_service,
            self._treatment_session_service,
            self._client_id,
            session=None,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload_sessions()

    def _ensure_active_treatment_type_exists(self) -> bool:
        """Guards "Neue Sitzung": with no active treatment type to pick,
        SessionDialog's Behandlungsart dropdown would just be empty
        (Auftrag D1). Offers to open the treatment-type management right
        away and, if that leaves an active type behind, lets the caller
        continue straight into SessionDialog.
        """
        if self._treatment_type_service.has_active_treatment_types():
            return True
        if self._treatment_type_service.has_treatment_types():
            message = (
                "Es gibt keine aktive Behandlungsart. Bitte legen Sie zuerst eine "
                "Behandlungsart an (z. B. 'Meditation')."
            )
        else:
            message = (
                "Es ist noch keine Behandlungsart angelegt. Bitte legen Sie zuerst "
                "eine Behandlungsart an (z. B. 'Meditation')."
            )
        if not ask_create_treatment_type(message, parent=self):
            return False
        management_dialog = TreatmentTypeManagementDialog(
            self._treatment_type_service, parent=self
        )
        management_dialog.exec()
        return self._treatment_type_service.has_active_treatment_types()

    def _on_edit_session_clicked(self) -> None:
        session = self._selected_session()
        if session is None:
            return
        self._edit_session(session)

    def _edit_session(self, session: TreatmentSession) -> None:
        dialog = SessionDialog(
            self._treatment_type_service,
            self._treatment_session_service,
            self._client_id,
            session=session,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload_sessions()

    def _on_delete_session_clicked(self) -> None:
        session = self._selected_session()
        if session is None:
            return
        confirmed = ask_confirm_delete(
            f"Sitzung vom {session.date.strftime('%d.%m.%Y %H:%M')} "
            f"({session.treatment_type.name}) unwiderruflich löschen?",
            title="Sitzung löschen",
            parent=self,
        )
        if not confirmed:
            return
        candidate_media_ids = [
            entry.media_id
            for entry in self._media_service.list_media_for_session(session.id)
        ]
        try:
            self._treatment_session_service.delete_session(session.id)
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return
        offer_to_delete_now_unused_media(self._media_service, candidate_media_ids, parent=self)
        self._reload_sessions()
