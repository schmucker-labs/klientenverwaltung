from PySide6.QtCore import QByteArray, QModelIndex, QSettings, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.models import Client, TreatmentSession
from klientenverwaltung.services import (
    ClientService,
    ServiceError,
    TreatmentSessionService,
    TreatmentTypeService,
)
from klientenverwaltung.ui.dialogs import (
    ask_confirm_delete,
    ask_save_discard_cancel,
    show_error,
)
from klientenverwaltung.ui.optional_date_edit import OptionalDateEdit
from klientenverwaltung.ui.session_dialog import SessionDialog
from klientenverwaltung.ui.session_note_dialog import SessionNoteDialog
from klientenverwaltung.ui.session_table_model import NOTE_COLUMN, SessionTableModel
from klientenverwaltung.ui.window_settings import (
    finalize_column_widths,
    restore_geometry,
    restore_header_state,
    save_geometry,
    save_header_state,
)

_SALUTATION_SUGGESTIONS = ["", "Herr", "Frau", "Herr Dr.", "Frau Dr."]
_GEOMETRY_SETTINGS_KEY = "client_detail/geometry"
_SPLITTER_SETTINGS_KEY = "client_detail/splitter_state"
_SESSION_TABLE_HEADER_SETTINGS_KEY = "client_detail/session_table_header_state"


class ClientDetailDialog(QDialog):
    def __init__(
        self,
        client_service: ClientService,
        treatment_type_service: TreatmentTypeService,
        treatment_session_service: TreatmentSessionService,
        client_id: int | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._client_service = client_service
        self._treatment_type_service = treatment_type_service
        self._treatment_session_service = treatment_session_service
        self._client_id = client_id

        self.resize(700, 800)
        self.setModal(True)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        self._build_ui()

        if client_id is not None:
            client = self._client_service.get_client(client_id)
            self._populate_form(client)
            self.setWindowTitle(f"Klient: {client.first_name} {client.last_name}")
        else:
            self.setWindowTitle("Neuer Klient")

        self._original_values = self._collect_form_values()
        self._update_session_section_enabled()
        self._reload_sessions()

    def _build_ui(self) -> None:
        self._salutation_combo = QComboBox(self)
        self._salutation_combo.setEditable(True)
        self._salutation_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._salutation_combo.addItems(_SALUTATION_SUGGESTIONS)
        self._first_name_edit = QLineEdit(self)
        self._last_name_edit = QLineEdit(self)
        self._birth_date_edit = OptionalDateEdit(self)
        self._street_edit = QLineEdit(self)
        self._postal_code_edit = QLineEdit(self)
        self._city_edit = QLineEdit(self)
        self._phone_edit = QLineEdit(self)
        self._email_edit = QLineEdit(self)
        self._referral_source_edit = QLineEdit(self)
        self._consent_date_edit = OptionalDateEdit(self)

        form = QFormLayout()
        form.addRow("Anrede:", self._salutation_combo)
        form.addRow("Vorname:", self._first_name_edit)
        form.addRow("Nachname:", self._last_name_edit)
        form.addRow("Geburtsdatum:", self._birth_date_edit)
        form.addRow("Straße:", self._street_edit)
        form.addRow("PLZ:", self._postal_code_edit)
        form.addRow("Ort:", self._city_edit)
        form.addRow("Telefon:", self._phone_edit)
        form.addRow("E-Mail:", self._email_edit)
        form.addRow("Aufmerksam geworden durch:", self._referral_source_edit)
        form.addRow("Einwilligung vom:", self._consent_date_edit)

        self._save_client_button = QPushButton("Speichern", self)
        self._save_client_button.setDefault(True)
        self._save_client_button.clicked.connect(self._on_save_clicked)
        save_row = QHBoxLayout()
        save_row.addStretch()
        save_row.addWidget(self._save_client_button)

        self._concern_edit = QTextEdit(self)
        self._notes_edit = QTextEdit(self)

        self._splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._splitter.setChildrenCollapsible(False)
        # Default handle width (4px) is too thin to reliably grab; the
        # target user is not a technician and may not sit optimally in
        # front of the screen, so click targets need to be generous.
        self._splitter.setHandleWidth(10)
        self._splitter.addWidget(
            self._build_labeled_panel("Anliegen:", self._concern_edit)
        )
        self._splitter.addWidget(self._build_sessions_panel())
        self._splitter.addWidget(
            self._build_labeled_panel("Notizen:", self._notes_edit)
        )
        for pane_index in range(self._splitter.count()):
            self._splitter.setStretchFactor(pane_index, 1)
        self._splitter.setSizes([120, 400, 120])
        self._splitter.splitterMoved.connect(self._save_splitter_state)
        self._restore_splitter_state()

        close_button = QPushButton("Schließen", self)
        close_button.clicked.connect(self.reject)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(close_button)

        # The form + splitter combined would need more height than fits on
        # a small screen (e.g. 1366x768) - wrapped in a QScrollArea, the
        # dialog's own minimum height stays small (just enough to show a
        # scrollbar) instead of forcing the window itself taller than the
        # screen. The close button stays outside/below it, always visible.
        scroll_content = QWidget(self)
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.addLayout(form)
        scroll_layout.addLayout(save_row)
        scroll_layout.addWidget(self._splitter, 1)

        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(scroll_content)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll_area, 1)
        layout.addLayout(close_row)

    @staticmethod
    def _build_labeled_panel(label_text: str, content: QWidget) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label_text, panel))
        layout.addWidget(content)
        return panel

    def _build_sessions_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("<b>Sitzungen</b>", panel))

        self._new_session_hint = QLabel(
            "Sitzungen können hinzugefügt werden, nachdem der Klient gespeichert wurde.",
            panel,
        )
        layout.addWidget(self._new_session_hint)

        self._session_table_model = SessionTableModel()
        self._session_table_view = QTableView(panel)
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
            session_header, _SESSION_TABLE_HEADER_SETTINGS_KEY
        )
        if not restored:
            self._session_table_view.resizeColumnsToContents()
            self._session_table_view.setColumnWidth(NOTE_COLUMN, 40)
        # Behandlungsart (treatment type name) is the one open-ended,
        # variable-length column, so it gets the remaining space rather than
        # stretching whichever column happens to be last - Notiz is last and
        # must stay a narrow, fixed-width icon column.
        finalize_column_widths(
            session_header, self._session_table_model.columnCount(), 1, restored
        )
        session_header.sectionResized.connect(self._save_session_table_header_state)
        self._session_table_view.selectionModel().selectionChanged.connect(
            self._update_session_button_states
        )
        self._session_table_view.clicked.connect(self._on_session_table_clicked)
        layout.addWidget(self._session_table_view)

        self._new_session_button = QPushButton("Neue Sitzung", panel)
        self._edit_session_button = QPushButton("Bearbeiten", panel)
        self._delete_session_button = QPushButton("Löschen", panel)
        self._edit_session_button.setEnabled(False)
        self._delete_session_button.setEnabled(False)
        self._new_session_button.clicked.connect(self._on_new_session_clicked)
        self._edit_session_button.clicked.connect(self._on_edit_session_clicked)
        self._delete_session_button.clicked.connect(self._on_delete_session_clicked)

        session_button_row = QHBoxLayout()
        session_button_row.addStretch()
        session_button_row.addWidget(self._new_session_button)
        session_button_row.addWidget(self._edit_session_button)
        session_button_row.addWidget(self._delete_session_button)
        layout.addLayout(session_button_row)

        return panel

    def _restore_splitter_state(self) -> None:
        state = QSettings().value(_SPLITTER_SETTINGS_KEY)
        if isinstance(state, QByteArray):
            self._splitter.restoreState(state)

    def _save_splitter_state(self) -> None:
        QSettings().setValue(_SPLITTER_SETTINGS_KEY, self._splitter.saveState())

    def _save_session_table_header_state(self) -> None:
        save_header_state(
            self._session_table_view.horizontalHeader(),
            _SESSION_TABLE_HEADER_SETTINGS_KEY,
        )

    def done(self, result: int) -> None:
        # done() is the single choke point every close path (accept, the
        # custom reject() above, the window's X button) funnels through, so
        # this is where size+position get persisted, not scattered across
        # each of those paths.
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        self._save_splitter_state()
        super().done(result)

    def _populate_form(self, client: Client) -> None:
        self._salutation_combo.setCurrentText(client.salutation or "")
        self._first_name_edit.setText(client.first_name)
        self._last_name_edit.setText(client.last_name)
        self._birth_date_edit.set_value(client.birth_date)
        self._street_edit.setText(client.street or "")
        self._postal_code_edit.setText(client.postal_code or "")
        self._city_edit.setText(client.city or "")
        self._phone_edit.setText(client.phone or "")
        self._email_edit.setText(client.email or "")
        self._concern_edit.setPlainText(client.concern or "")
        self._referral_source_edit.setText(client.referral_source or "")
        self._consent_date_edit.set_value(client.consent_date)
        self._notes_edit.setPlainText(client.notes or "")

    def _collect_form_values(self) -> dict[str, object]:
        return {
            "first_name": self._first_name_edit.text().strip(),
            "last_name": self._last_name_edit.text().strip(),
            "salutation": self._salutation_combo.currentText().strip() or None,
            "birth_date": self._birth_date_edit.value(),
            "street": self._street_edit.text().strip() or None,
            "postal_code": self._postal_code_edit.text().strip() or None,
            "city": self._city_edit.text().strip() or None,
            "phone": self._phone_edit.text().strip() or None,
            "email": self._email_edit.text().strip() or None,
            "concern": self._concern_edit.toPlainText().strip() or None,
            "referral_source": self._referral_source_edit.text().strip() or None,
            "consent_date": self._consent_date_edit.value(),
            "notes": self._notes_edit.toPlainText().strip() or None,
        }

    def _is_dirty(self) -> bool:
        return self._collect_form_values() != self._original_values

    def _update_session_section_enabled(self) -> None:
        has_client = self._client_id is not None
        self._new_session_hint.setVisible(not has_client)
        self._new_session_button.setEnabled(has_client)
        self._session_table_view.setEnabled(has_client)

    def _reload_sessions(self) -> None:
        if self._client_id is None:
            self._session_table_model.set_sessions([])
        else:
            sessions = self._treatment_session_service.list_sessions_for_client(
                self._client_id
            )
            self._session_table_model.set_sessions(sessions)
        self._update_session_button_states()

    def _selected_session(self) -> TreatmentSession | None:
        rows = self._session_table_view.selectionModel().selectedRows()
        if len(rows) != 1:
            return None
        return self._session_table_model.session_at(rows[0].row())

    def _update_session_button_states(self) -> None:
        has_selection = self._selected_session() is not None
        self._edit_session_button.setEnabled(has_selection)
        self._delete_session_button.setEnabled(has_selection)

    def _on_save_clicked(self) -> None:
        values = self._collect_form_values()
        try:
            if self._client_id is None:
                client = self._client_service.create_client(**values)
                self._client_id = client.id
            else:
                client = self._client_service.update_client(self._client_id, **values)
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return
        self._original_values = values
        self.setWindowTitle(f"Klient: {client.first_name} {client.last_name}")
        self._update_session_section_enabled()
        self._reload_sessions()

    def _on_new_session_clicked(self) -> None:
        if self._client_id is None:
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

    def _on_edit_session_clicked(self) -> None:
        session = self._selected_session()
        if session is None:
            return
        self._edit_session(session)

    def _on_session_table_clicked(self, index: QModelIndex) -> None:
        if not index.isValid() or index.column() != NOTE_COLUMN:
            return
        session = self._session_table_model.session_at(index.row())
        if not session.notes:
            return
        dialog = SessionNoteDialog(session.notes, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._edit_session(session)

    def _edit_session(self, session: TreatmentSession) -> None:
        if self._client_id is None:
            return
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
        try:
            self._treatment_session_service.delete_session(session.id)
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return
        self._reload_sessions()

    def reject(self) -> None:
        if not self._is_dirty():
            super().reject()
            return
        choice = ask_save_discard_cancel(
            "Es gibt ungespeicherte Änderungen an diesem Klienten.", parent=self
        )
        if choice == "cancel":
            return
        if choice == "discard":
            super().reject()
            return
        self._on_save_clicked()
        if not self._is_dirty():
            super().reject()
