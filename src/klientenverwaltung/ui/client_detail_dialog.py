from datetime import date

from PySide6.QtCore import QByteArray, QSettings, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.app_context import AppServices
from klientenverwaltung.services import (
    ClientDetails,
    DuplicateClientError,
    ServiceError,
    ValidationError,
)
from klientenverwaltung.ui.buttons import window_row
from klientenverwaltung.ui.client_sessions_dialog import ClientSessionsDialog
from klientenverwaltung.ui.dialogs import (
    ask_save_discard_cancel,
    ask_save_possible_duplicate,
    show_error,
)
from klientenverwaltung.ui.optional_date_edit import OptionalDateEdit
from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry

_SALUTATION_SUGGESTIONS = ["", "Herr", "Frau", "Herr Dr.", "Frau Dr."]
# Not "client_detail/geometry": that one holds sizes saved for the earlier,
# narrow single-column window, which would squeeze the two halves.
_GEOMETRY_SETTINGS_KEY = "client_detail/two_column_geometry"
_SPLITTER_SETTINGS_KEY = "client_detail/splitter_state"


class ClientDetailDialog(QDialog):
    """A client's master data, in two halves: the form (Stammdaten) on the
    left, Anliegen and Notizen on the right.

    Sessions used to live in a table embedded right here, but that made
    the window too tall for a small screen (e.g. 1366x768) even with a
    QScrollArea - so they now live in their own window
    (ClientSessionsDialog), reached via the "Sitzungen (n)" button at the
    bottom, which also always shows the count and most recent date without
    having to open it.
    """

    # The client was saved ("Speichern" leaves this window open), or its
    # sessions changed in the window opened from here - the window behind
    # this modal one refreshes what it shows (docs/ui-regeln.md).
    data_changed = Signal()

    def __init__(
        self,
        services: AppServices,
        client_id: int | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._services = services
        self._client_id = client_id

        self.resize(1100, 660)
        self.setModal(True)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        self._build_ui()

        if client_id is not None:
            client = self._services.clients.get_client(client_id)
            self._populate_form(client)
            self.setWindowTitle(f"Klient: {client.first_name} {client.last_name}")
        else:
            self.setWindowTitle("Neuer Klient")

        self._original_values = self._collect_form_values()
        self._update_sessions_button()

    @property
    def client_id(self) -> int | None:
        """The client shown - also set once a new client was saved."""
        return self._client_id

    def _build_ui(self) -> None:
        self._salutation_combo = QComboBox(self)
        self._salutation_combo.setEditable(True)
        self._salutation_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._salutation_combo.addItems(_SALUTATION_SUGGESTIONS)
        self._first_name_edit = QLineEdit(self)
        self._last_name_edit = QLineEdit(self)
        # Starts decades back, not today - a birth date is typed or picked
        # from there, not scrolled to year by year.
        self._birth_date_edit = OptionalDateEdit(
            self, initial_date=date(date.today().year - 40, 1, 1), not_in_future=True
        )
        self._street_edit = QLineEdit(self)
        self._postal_code_edit = QLineEdit(self)
        self._city_edit = QLineEdit(self)
        self._phone_edit = QLineEdit(self)
        self._email_edit = QLineEdit(self)
        self._referral_source_edit = QLineEdit(self)
        self._consent_date_edit = OptionalDateEdit(self, not_in_future=True)

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
        # Where a ValidationError's field puts the cursor (see _save).
        self._field_edits: dict[str, QLineEdit] = {
            "first_name": self._first_name_edit,
            "last_name": self._last_name_edit,
            "street": self._street_edit,
            "postal_code": self._postal_code_edit,
            "city": self._city_edit,
            "phone": self._phone_edit,
            "email": self._email_edit,
        }

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
        self._splitter.addWidget(
            self._build_labeled_panel("Notizen:", self._notes_edit)
        )
        for pane_index in range(self._splitter.count()):
            self._splitter.setStretchFactor(pane_index, 1)
        self._splitter.setSizes([200, 200])
        self._splitter.splitterMoved.connect(self._save_splitter_state)
        self._restore_splitter_state()

        self._sessions_button = QPushButton(self)
        self._sessions_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._sessions_button.clicked.connect(self._on_sessions_clicked)
        self._sessions_last_date_label = QLabel(self)
        self._sessions_last_date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sessions_next_date_label = QLabel(self)
        self._sessions_next_date_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sessions_section = QVBoxLayout()
        sessions_section.addWidget(self._sessions_button)
        sessions_section.addWidget(self._sessions_last_date_label)
        sessions_section.addWidget(self._sessions_next_date_label)

        # Saves both halves, so it sits below them, next to "Schließen" -
        # never scrolled out of view.
        self._save_client_button = QPushButton("Speichern", self)
        self._save_client_button.setDefault(True)
        self._save_client_button.clicked.connect(self._on_save_clicked)
        # Enter inside Anliegen/Notizen is a line break (docs/ui-regeln.md):
        # Strg+S saves and stays, Strg+Enter saves and closes.
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._on_save_clicked)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._on_save_and_close)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._on_save_and_close)
        close_button = QPushButton("Schließen", self)
        close_button.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        # One measure for every gap around the form's scrollbar: the dialog's
        # own margin (from the style, not a fixed number).
        gutter = layout.contentsMargins().right()

        # Left half: the form. On a small screen (e.g. 1366x768 with a
        # scaled-up display) it does not fit - wrapped in a QScrollArea, the
        # dialog's own minimum height stays small instead of forcing the
        # window taller than the screen. The Sitzungen button stays outside/
        # below it, always visible without having to scroll down.
        scroll_content = QWidget(self)
        scroll_layout = QVBoxLayout(scroll_content)
        # The right margin keeps the input fields clear of the scrollbar.
        # Together with the columns' spacing below, the scrollbar ends up
        # centered in the gap between the two halves (gutter on either
        # side); without a scrollbar that gap is simply twice the gutter.
        scroll_layout.setContentsMargins(0, 0, gutter, 0)
        scroll_layout.addLayout(form)
        scroll_layout.addStretch()

        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll_area.setWidget(scroll_content)
        # Never narrower than the form itself - there is no horizontal
        # scrollbar to reach a cut-off field with.
        self._scroll_area.setMinimumWidth(
            scroll_content.minimumSizeHint().width()
            + self._scroll_area.verticalScrollBar().sizeHint().width()
        )

        # Same right edge as the form's fields above it.
        sessions_section.setContentsMargins(0, 0, gutter, 0)
        left_half = QVBoxLayout()
        left_half.addWidget(self._scroll_area, 1)
        left_half.addLayout(sessions_section)

        # Right half: only Anliegen and Notizen, over the full height - and
        # never squeezed down to a few words per line.
        self._splitter.setMinimumWidth(300)
        halves = QHBoxLayout()
        halves.setSpacing(gutter)
        halves.addLayout(left_half, 1)
        halves.addWidget(self._splitter, 1)

        layout.addLayout(halves, 1)
        layout.addWidget(window_row(self._save_client_button, close_button))

    @staticmethod
    def _build_labeled_panel(label_text: str, content: QWidget) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label_text, panel))
        layout.addWidget(content)
        return panel

    def _restore_splitter_state(self) -> None:
        state = QSettings().value(_SPLITTER_SETTINGS_KEY)
        if isinstance(state, QByteArray):
            self._splitter.restoreState(state)

    def _save_splitter_state(self) -> None:
        QSettings().setValue(_SPLITTER_SETTINGS_KEY, self._splitter.saveState())

    def done(self, result: int) -> None:
        # done() is the single choke point every close path (accept, the
        # custom reject() above, the window's X button) funnels through, so
        # this is where size+position get persisted, not scattered across
        # each of those paths.
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        self._save_splitter_state()
        super().done(result)

    def _populate_form(self, client: ClientDetails) -> None:
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

    def _update_sessions_button(self) -> None:
        if self._client_id is None:
            self._sessions_button.setText("Sitzungen")
            self._sessions_button.setEnabled(False)
            self._sessions_last_date_label.setText(
                "Sitzungen können hinzugefügt werden, nachdem der Klient "
                "gespeichert wurde."
            )
            self._sessions_next_date_label.setText("")
            return
        session_count = self._services.treatment_sessions.count_sessions_for_client(
            self._client_id
        )
        self._sessions_button.setEnabled(True)
        self._sessions_button.setText(f"Sitzungen ({session_count})")
        # Same past/future split as the client list's "Letzte
        # Sitzung"/"Nächster Termin" columns (both read
        # TreatmentSessionRepository.get_last_session_dates()/
        # get_upcoming_sessions() via this one service method), so the two
        # views can never disagree about what counts as "last" vs "next".
        summary = self._services.treatment_sessions.get_session_summary(self._client_id)
        self._sessions_last_date_label.setText(
            f"Letzte Sitzung: {summary.last_session_date.strftime('%d.%m.%Y')}"
            if summary.last_session_date is not None
            else "Letzte Sitzung: keine"
        )
        self._sessions_next_date_label.setText(
            f"Nächste Sitzung: {summary.next_session_date.strftime('%d.%m.%Y')}"
            if summary.next_session_date is not None
            else "Nächste Sitzung: keine"
        )

    def _save(self) -> bool:
        values = self._collect_form_values()
        clients = self._services.clients
        allow_duplicate = False
        while True:
            try:
                if self._client_id is None:
                    client = clients.create_client(
                        **values, allow_duplicate=allow_duplicate
                    )
                    self._client_id = client.id
                else:
                    client = clients.update_client(
                        self._client_id, **values, allow_duplicate=allow_duplicate
                    )
                break
            except DuplicateClientError as exc:
                # Everything else is in order (the service checks this
                # last) - the user decides, then the same save runs again.
                if not ask_save_possible_duplicate(str(exc), parent=self):
                    return False
                allow_duplicate = True
            except ServiceError as exc:
                show_error(str(exc), parent=self)
                if isinstance(exc, ValidationError) and exc.field in self._field_edits:
                    # Straight to the field that needs correcting.
                    field_edit = self._field_edits[exc.field]
                    self._scroll_area.ensureWidgetVisible(field_edit)
                    field_edit.setFocus()
                    field_edit.selectAll()
                return False
        # Show what was stored - the service normalizes casing - not the
        # raw input.
        self._populate_form(client)
        self._original_values = self._collect_form_values()
        self.setWindowTitle(f"Klient: {client.first_name} {client.last_name}")
        self._update_sessions_button()
        self.data_changed.emit()
        return True

    def _on_save_clicked(self) -> None:
        self._save()

    def _on_save_and_close(self) -> None:
        if self._save():
            self.accept()

    def _on_sessions_clicked(self) -> None:
        if self._client_id is None:
            return
        if self._is_dirty():
            choice = ask_save_discard_cancel(
                "Es gibt ungespeicherte Änderungen an diesem Klienten.", parent=self
            )
            if choice == "cancel":
                return
            if choice == "save" and not self._save():
                return
        client_name = f"{self._first_name_edit.text()} {self._last_name_edit.text()}"
        dialog = ClientSessionsDialog(
            self._services,
            self._client_id,
            client_name.strip(),
            parent=self,
        )
        dialog.data_changed.connect(self._update_sessions_button)
        dialog.data_changed.connect(self.data_changed)
        dialog.exec()
        self._update_sessions_button()

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
        if self._save():
            super().reject()
