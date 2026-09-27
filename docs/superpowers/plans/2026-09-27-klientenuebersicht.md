# Klientenübersicht (Auftrag B1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only "Klientenübersicht" dialog, reachable via double-click and a new right-click context menu on the client list, showing a client's data as a letter-style overview with empty fields/sections fully omitted.

**Architecture:** New `ClientOverviewDialog` in `ui/`, built the same way as the existing `ClientDetailDialog`/`ClientSessionsDialog` (QScrollArea body, fixed button row, `window_settings` geometry helper). All non-trivial computation (age, address-block assembly, report count) lives in `ClientService`/`TreatmentSessionService`, not in the dialog. `client_list_widget.py` gets a new right-click context menu and its double-click handler switches from the edit dialog to the new overview dialog.

**Tech Stack:** PySide6, SQLAlchemy 2.x models already in place, pytest for the service-layer logic.

**Spec:** The Auftrag B1 request in this conversation (no separate spec file — the full text is reproduced in Global Constraints/task descriptions below).

## Global Constraints

- UI text/labels: German. Code/identifiers: English.
- "Klient", never "Kunde", anywhere user-visible.
- Dates in the UI: `TT.MM.JJJJ` (`strftime("%d.%m.%Y")`).
- No business logic in `ui/` — age calculation, address-line assembly, and report counting belong in the service layer.
- Every dialog uses the shared `window_settings.restore_geometry`/`save_geometry` helpers under its own QSettings key, and fits 1366x768 (QScrollArea if needed).
- Empty fields (and their labels) are never shown in the overview dialog; a section with no content disappears entirely, no gap left behind.
- No hardcoded colors in UI code — only theme palette values, and only where the existing codebase already does the same (this plan does not introduce any new inline color).
- ruff must pass with no errors; all tests green.
- Commit messages: no `Co-Authored-By: Claude` trailer (public portfolio repo).

## Review Focus

- Client with **every optional field set to `None`** (fresh client, just first/last name): overview must show only the name line, "Klient seit", "Letzte Sitzung: keine", "Nächster Termin: keine" — no crash, no stray blank sections.
- **Only PLZ set, no city** (or vice versa): address block must show the one present value alone, not "None Ort" or a stray leading/trailing space.
- **Birth date is today's date** (age must credit the birthday immediately) vs. **birth date is tomorrow's month/day** (must still show last year's age, not one too many).
- Sessions whose `report`/`impulses` are empty strings rather than `None` (shouldn't happen per the model layer's normalization, but the counting logic must not accidentally count them) — covered by testing both `None` and falsy-but-set inputs.
- Right-click on an **empty area** of the client table (no row under the cursor) must not throw or show a menu with a stale/wrong client.

---

### Task 1: `ClientService` — age calculation and address block

**Files:**
- Modify: `src/klientenverwaltung/services/client_service.py`
- Modify: `src/klientenverwaltung/services/__init__.py`
- Test: `tests/test_client_service.py`

**Interfaces:**
- Produces: `ClientService.compute_age(birth_date: date, *, today: date | None = None) -> int` (staticmethod)
- Produces: `ClientService.build_address_block(client: Client) -> ClientAddressBlock` (staticmethod)
- Produces: `ClientAddressBlock` dataclass with fields `name_line: str`, `lines: list[str]`, `contact_lines: list[str]`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_client_service.py (append)
from datetime import date

from klientenverwaltung.services.client_service import ClientAddressBlock


@pytest.mark.parametrize(
    "birth_date,today,expected_age",
    [
        (date(1980, 3, 15), date(2026, 3, 15), 46),  # exact birthday
        (date(1980, 3, 15), date(2026, 3, 14), 45),  # day before birthday
        (date(1980, 3, 15), date(2026, 3, 16), 46),  # day after birthday
        (date(2026, 1, 1), date(2026, 1, 1), 0),  # born today
    ],
)
def test_compute_age(birth_date: date, today: date, expected_age: int) -> None:
    assert ClientService.compute_age(birth_date, today=today) == expected_age


def test_build_address_block_with_all_fields_set() -> None:
    client = Client(
        salutation="Frau",
        first_name="Erika",
        last_name="Musterfrau",
        street="Hauptstraße 1",
        postal_code="12345",
        city="Musterstadt",
        phone="0123456789",
        email="erika@example.com",
    )
    block = ClientService.build_address_block(client)
    assert block == ClientAddressBlock(
        name_line="Frau Erika Musterfrau",
        lines=["Hauptstraße 1", "12345 Musterstadt"],
        contact_lines=["Telefon: 0123456789", "E-Mail: erika@example.com"],
    )


@pytest.mark.parametrize(
    "overrides,expected_lines,expected_contact_lines",
    [
        ({"street": None}, ["12345 Musterstadt"], ["Telefon: 0123456789"]),
        ({"postal_code": None}, ["Hauptstraße 1", "Musterstadt"], ["Telefon: 0123456789"]),
        ({"city": None}, ["Hauptstraße 1", "12345"], ["Telefon: 0123456789"]),
        (
            {"postal_code": None, "city": None},
            ["Hauptstraße 1"],
            ["Telefon: 0123456789"],
        ),
        ({"phone": None}, ["Hauptstraße 1", "12345 Musterstadt"], []),
        ({"phone": None, "email": None}, ["Hauptstraße 1", "12345 Musterstadt"], []),
        ({"salutation": None}, ["Hauptstraße 1", "12345 Musterstadt"], ["Telefon: 0123456789"]),
    ],
)
def test_build_address_block_omits_missing_fields(
    overrides: dict[str, str | None],
    expected_lines: list[str],
    expected_contact_lines: list[str],
) -> None:
    fields = {
        "salutation": "Frau",
        "first_name": "Erika",
        "last_name": "Musterfrau",
        "street": "Hauptstraße 1",
        "postal_code": "12345",
        "city": "Musterstadt",
        "phone": "0123456789",
        "email": None,
        **overrides,
    }
    client = Client(**fields)
    block = ClientService.build_address_block(client)
    assert block.lines == expected_lines
    assert block.contact_lines == expected_contact_lines


def test_build_address_block_name_line_omits_missing_salutation() -> None:
    client = Client(salutation=None, first_name="Anna", last_name="Muster")
    block = ClientService.build_address_block(client)
    assert block.name_line == "Anna Muster"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_client_service.py -k "compute_age or address_block" -v`
Expected: FAIL (`AttributeError`/`ImportError` — methods/dataclass don't exist yet)

- [ ] **Step 3: Implement**

In `src/klientenverwaltung/services/client_service.py`, add near the top (after the existing dataclasses) and inside the `ClientService` class:

```python
@dataclass(frozen=True)
class ClientAddressBlock:
    """The Klientenübersicht's letter-style address block (Auftrag B1).

    name_line is always present (first/last name are mandatory); lines and
    contact_lines contain only the address/contact lines the client
    actually has, in display order, so the dialog can render exactly what
    exists with no empty-field placeholders.
    """

    name_line: str
    lines: list[str]
    contact_lines: list[str]
```

Add to `ClientService` (near the other `@staticmethod` helpers at the bottom):

```python
    @staticmethod
    def compute_age(birth_date: date, *, today: date | None = None) -> int:
        today = today if today is not None else date.today()
        age = today.year - birth_date.year
        if (today.month, today.day) < (birth_date.month, birth_date.day):
            age -= 1
        return age

    @staticmethod
    def build_address_block(client: Client) -> ClientAddressBlock:
        name_line = " ".join(
            part
            for part in (client.salutation, client.first_name, client.last_name)
            if part
        )

        lines: list[str] = []
        if client.street:
            lines.append(client.street)
        postal_and_city = " ".join(
            part for part in (client.postal_code, client.city) if part
        )
        if postal_and_city:
            lines.append(postal_and_city)

        contact_lines: list[str] = []
        if client.phone:
            contact_lines.append(f"Telefon: {client.phone}")
        if client.email:
            contact_lines.append(f"E-Mail: {client.email}")

        return ClientAddressBlock(
            name_line=name_line, lines=lines, contact_lines=contact_lines
        )
```

In `src/klientenverwaltung/services/__init__.py`, add `ClientAddressBlock` to the import from `client_service` and to `__all__`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_client_service.py -v`
Expected: PASS (all, including pre-existing tests)

- [ ] **Step 5: Commit**

```bash
git add src/klientenverwaltung/services/client_service.py src/klientenverwaltung/services/__init__.py tests/test_client_service.py
git commit -m "Add age and address-block logic to ClientService (Auftrag B1)"
```

---

### Task 2: `TreatmentSessionService` — report/impulse count

**Files:**
- Modify: `src/klientenverwaltung/services/treatment_session_service.py`
- Test: `tests/test_treatment_session_service.py`

**Interfaces:**
- Consumes: `TreatmentSessionService.list_sessions_for_client(client_id: int) -> list[TreatmentSession]` (existing)
- Produces: `TreatmentSessionService.count_sessions_with_content(client_id: int) -> int`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_treatment_session_service.py (append)
def test_count_sessions_with_content_counts_only_sessions_with_report_or_impulses(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    no_content = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 10, 9, 0),
        duration_minutes=60,
    )
    report_only = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 11, 9, 0),
        duration_minutes=60,
    )
    impulses_only = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 12, 9, 0),
        duration_minutes=60,
    )
    both = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 13, 9, 0),
        duration_minutes=60,
    )
    treatment_session_service.save_report(
        no_content.id, report=None, impulses=None
    )
    treatment_session_service.save_report(
        report_only.id, report="<p>Bericht</p>", impulses=None
    )
    treatment_session_service.save_report(
        impulses_only.id, report=None, impulses="<p>Impuls</p>"
    )
    treatment_session_service.save_report(
        both.id, report="<p>Bericht</p>", impulses="<p>Impuls</p>"
    )

    assert (
        treatment_session_service.count_sessions_with_content(client.id) == 3
    )


def test_count_sessions_with_content_is_zero_for_client_without_sessions(
    treatment_session_service: TreatmentSessionService, client: Client
) -> None:
    assert treatment_session_service.count_sessions_with_content(client.id) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_treatment_session_service.py -k count_sessions_with_content -v`
Expected: FAIL (`AttributeError: 'TreatmentSessionService' object has no attribute 'count_sessions_with_content'`)

- [ ] **Step 3: Implement**

In `src/klientenverwaltung/services/treatment_session_service.py`, add to `TreatmentSessionService` (near `list_sessions_for_client`):

```python
    def count_sessions_with_content(self, client_id: int) -> int:
        """Sessions with a Bericht or Impulse entered (Auftrag A2's report
        window) - drives the "Berichte (n)" button on the Klientenübersicht
        (Auftrag B1)."""
        sessions = self.list_sessions_for_client(client_id)
        return sum(1 for session in sessions if session.report or session.impulses)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_treatment_session_service.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add src/klientenverwaltung/services/treatment_session_service.py tests/test_treatment_session_service.py
git commit -m "Add report/impulse session count to TreatmentSessionService (Auftrag B1)"
```

---

### Task 3: `ClientOverviewDialog`

**Files:**
- Create: `src/klientenverwaltung/ui/client_overview_dialog.py`

**Interfaces:**
- Consumes: `ClientService.get_client`, `ClientService.compute_age`, `ClientService.build_address_block`, `TreatmentSessionService.list_sessions_for_client`, `TreatmentSessionService.get_session_summary`, `TreatmentSessionService.count_sessions_with_content`, `ClientDetailDialog(client_service, treatment_type_service, treatment_session_service, client_id, parent)`, `ClientSessionsDialog(treatment_type_service, treatment_session_service, client_id, client_name, parent)`, `restore_geometry`/`save_geometry`.
- Produces: `ClientOverviewDialog(client_service, treatment_type_service, treatment_session_service, client_id: int, parent=None)` — no return value consumed elsewhere; `client_list_widget.py` (Task 4) only calls `.exec()` on it.

No automated tests for this task — it is pure Qt wiring around already-tested service logic (per this project's existing pattern: `client_detail_dialog.py`/`client_sessions_dialog.py` have no dedicated dialog tests either). Verified manually in Task 5's final step.

- [ ] **Step 1: Create the dialog**

```python
# src/klientenverwaltung/ui/client_overview_dialog.py
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
    TreatmentSessionService,
    TreatmentTypeService,
)
from klientenverwaltung.ui.client_detail_dialog import ClientDetailDialog
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
        client_id: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._client_service = client_service
        self._treatment_type_service = treatment_type_service
        self._treatment_session_service = treatment_session_service
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

        report_count = self._treatment_session_service.count_sessions_with_content(
            client.id
        )
        self._report_button.setText(f"Berichte ({report_count})")
        # Actually opening something here is Auftrag B2 - until then this
        # stays disabled regardless of the count.
        self._report_button.setEnabled(False)
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
        layout.addWidget(
            QLabel(f"Klient seit: {client.created_at.strftime('%d.%m.%Y')}", panel)
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
                    else "keine"
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

    def _on_sessions_clicked(self) -> None:
        client = self._client_service.get_client(self._client_id)
        client_name = f"{client.first_name} {client.last_name}"
        dialog = ClientSessionsDialog(
            self._treatment_type_service,
            self._treatment_session_service,
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
            self._client_id,
            parent=self,
        )
        dialog.exec()
        self._reload()
```

- [ ] **Step 2: ruff check**

Run: `uv run ruff check src/klientenverwaltung/ui/client_overview_dialog.py`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add src/klientenverwaltung/ui/client_overview_dialog.py
git commit -m "Add read-only Klientenübersicht dialog (Auftrag B1)"
```

---

### Task 4: Wire into the client list (double-click + context menu)

**Files:**
- Modify: `src/klientenverwaltung/ui/client_list_widget.py`

**Interfaces:**
- Consumes: `ClientOverviewDialog` (Task 3)

- [ ] **Step 1: Update imports and add the context menu**

In `src/klientenverwaltung/ui/client_list_widget.py`:

Change the `PySide6.QtCore` import to add `QPoint, Qt`:
```python
from PySide6.QtCore import QModelIndex, QPoint, Qt, QTimer
```

Change the `PySide6.QtWidgets` import to add `QMenu`:
```python
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)
```

Add the new dialog import next to the existing one:
```python
from klientenverwaltung.ui.client_detail_dialog import ClientDetailDialog
from klientenverwaltung.ui.client_overview_dialog import ClientOverviewDialog
```

After `self._table_view.doubleClicked.connect(self._on_row_double_clicked)` in `__init__`, add:
```python
        self._table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table_view.customContextMenuRequested.connect(self._show_context_menu)
```

- [ ] **Step 2: Add `_open_overview_dialog`, use it from double-click, add the context menu handler**

Replace:
```python
    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        entry = self._table_model.entry_at(index.row())
        self._open_detail_dialog(entry.id)
```
with:
```python
    def _open_overview_dialog(self, client_id: int) -> None:
        dialog = ClientOverviewDialog(
            self._client_service,
            self._treatment_type_service,
            self._treatment_session_service,
            client_id,
            parent=self,
        )
        dialog.exec()
        self._reload()

    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        entry = self._table_model.entry_at(index.row())
        self._open_overview_dialog(entry.id)

    def _show_context_menu(self, pos: QPoint) -> None:
        index = self._table_view.indexAt(pos)
        if not index.isValid():
            return
        self._table_view.selectRow(index.row())
        entry = self._table_model.entry_at(index.row())

        menu = QMenu(self)
        view_action = menu.addAction("Ansicht")
        edit_action = menu.addAction("Bearbeiten")
        menu.addSeparator()
        archive_action = menu.addAction(
            "Wiederherstellen" if entry.archived else "Archivieren"
        )
        delete_action = menu.addAction("Löschen")

        chosen = menu.exec(self._table_view.viewport().mapToGlobal(pos))
        if chosen is view_action:
            self._open_overview_dialog(entry.id)
        elif chosen is edit_action:
            self._open_detail_dialog(entry.id)
        elif chosen is archive_action:
            self._on_archive_clicked()
        elif chosen is delete_action:
            self._on_delete_clicked()
```

(`_open_detail_dialog`, `_on_archive_clicked`, `_on_delete_clicked` already exist unchanged — the context menu just reuses them after moving the selection.)

- [ ] **Step 3: ruff check**

Run: `uv run ruff check src/klientenverwaltung/ui/client_list_widget.py`
Expected: no errors

- [ ] **Step 4: Manual verification**

Since this and Task 3 are pure UI wiring with no dedicated automated tests, verify by hand with throwaway data (never real client data on the laptop):
1. Run a short Python snippet against a temp SQLite file (same pattern as `tests/conftest.py`'s `engine`/`session_factory` fixtures) that seeds 2-3 clients with varying combinations of missing fields (one with everything filled in, one with only first/last name, one archived, one with a past+future session and a session with a Bericht).
2. Launch just `ClientListWidget` (or the relevant dialogs directly) in a throwaway `QApplication` against that data.
3. Confirm: double-click opens the Übersicht (not the edit dialog); right-click shows Ansicht/Bearbeiten/separator/Archivieren-or-Wiederherstellen/Löschen; the Übersicht shows only non-empty fields/sections, the correct age, "Berichte (n)" always disabled, "Sitzungen (n)" opens the sessions dialog and the Übersicht refreshes after it and after Bearbeiten closes.
4. Take a screenshot (`widget.grab().save(...)`) of the Übersicht for at least the "everything filled in" and "only first/last name" clients and inspect them.

- [ ] **Step 5: Commit**

```bash
git add src/klientenverwaltung/ui/client_list_widget.py
git commit -m "Open Klientenübersicht on double-click and add list context menu (Auftrag B1)"
```

---

### Task 5: Update `docs/ui-regeln.md`

**Files:**
- Modify: `docs/ui-regeln.md`

- [ ] **Step 1: Add the new rule**

Add a new bullet at the end of the file:

```markdown
- In reinen Anzeige-Fenstern (keine Eingabefelder, z. B. die Klientenübersicht) werden
  leere Felder komplett weggelassen, samt Beschriftung - ein Abschnitt ohne Inhalt
  verschwindet vollständig, es bleibt keine Lücke stehen. Doppelklick in der
  Klientenliste öffnet diese Ansicht, nicht mehr direkt den Bearbeiten-Dialog.
```

- [ ] **Step 2: Commit**

```bash
git add docs/ui-regeln.md
git commit -m "Document Anzeige-Fenster rule for empty fields (Auftrag B1)"
```

---

### Task 6: Full verification

- [ ] **Step 1: Run the whole test suite**

Run: `uv run pytest -v`
Expected: all tests pass

- [ ] **Step 2: Run ruff over the whole project**

Run: `uv run ruff check .`
Expected: no errors

No commit for this task (verification only, nothing to stage).
