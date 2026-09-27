# Berichtsverlauf (Auftrag B2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only "Berichtsverlauf" dialog showing every session of a client that has a Bericht or Impulse, newest first, two columns per session (Bericht | Impulse) rendered exactly as formatted, reachable from the Klientenübersicht's "Berichte (n)" button (which B1 left permanently disabled).

**Architecture:** A new repository query (`TreatmentSessionRepository.list_with_content_for_client`) does the filtering/ordering in SQL; a thin service method (`TreatmentSessionService.list_sessions_with_content`) exposes it. This same method replaces B1's `count_sessions_with_content` (now just `len(...)` of the same list) so there is exactly one query that defines "has content" everywhere it's used. The dialog itself reuses the existing rich-text auto-growing text widget from `report_dialog.py`, extracted into its own module so both the editable Bericht window and the new read-only history share the same "no internal scrollbar, grows to fit content" behavior instead of duplicating it.

**Tech Stack:** PySide6, SQLAlchemy 2.x, pytest. No new dependencies, no new Alembic migration, no new PyInstaller hidden imports (every Qt class used here is already used elsewhere in the app).

**Spec:** The Auftrag B2 request in this conversation (reproduced in Global Constraints / task descriptions below). Builds on Auftrag B1 (already implemented: `ClientOverviewDialog`, `docs/ui-regeln.md`'s Anzeige-Fenster rule).

## Global Constraints

- UI text/labels: German. Code/identifiers: English.
- Dialog title: `"Berichte: <Vorname Nachname>"`.
- Sessions ordered newest first; a session with neither Bericht nor Impulse never appears.
- Per session: heading `"Sitzung vom TT.MM.JJJJ, HH:MM Uhr – <Behandlungsart>"`, then two columns "Bericht" / "Impulse", rendered with whatever formatting was saved (bold/italic/underline/headings) - never a hardcoded text color, always the active theme's (per `docs/ui-regeln.md`'s rich-text rule).
- An empty side of a session shows a plain "–" instead of an empty text area - not a big blank box.
- No scrollbar inside any text area - each one is exactly as tall as its content; only the whole window scrolls.
- Text is selectable/copyable but never editable.
- A live theme switch while this dialog is open must still recolor its text (automatic here as long as no per-character foreground color is ever set - the stored HTML already has none, since `ReportDialog._save()` strips it before saving).
- Window geometry via the shared `window_settings.restore_geometry`/`save_geometry` helpers under its own QSettings key; usable at 1366x768 with both columns readable.
- No business logic in `ui/` - the "which sessions have content, in what order" decision lives in the repository query + service method, not the dialog.
- ruff must pass with no errors; all tests green.
- Commit messages: no `Co-Authored-By: Claude` trailer.

## Review Focus

- A session with **only Impulse, no Bericht** (and vice versa): must appear in the list (it has content), with the empty side showing "–", not blank.
- A client with **sessions that have report/impulses IS NOT NULL but an empty string** (defense-in-depth - `save_report()` never lets this happen today, but the query must not rely on that): must not appear in the Berichtsverlauf and must not count toward "Berichte (n)".
- **Two sessions on the same date** (or any tie): ordering must stay deterministic newest-first without crashing on a tie-break.
- A client with **zero sessions with content**: `ClientOverviewDialog`'s "Berichte (0)" must stay disabled with its tooltip - opening `ClientReportHistoryDialog` directly in this state (e.g. testing) must not crash on an empty list.
- **Long/heavy rich-text content across many sessions** (Auftrag B2's own performance requirement) - opening and scrolling must stay responsive; verified manually since this is not something a unit test meaningfully proves.

---

### Task 1: Sessions-with-content query (repository + service)

**Files:**
- Modify: `src/klientenverwaltung/repositories/treatment_session_repository.py`
- Modify: `src/klientenverwaltung/services/treatment_session_service.py`
- Modify: `src/klientenverwaltung/ui/client_overview_dialog.py` (switch off the now-removed `count_sessions_with_content`)
- Test: `tests/test_treatment_session_service.py`

**Interfaces:**
- Produces: `TreatmentSessionRepository.list_with_content_for_client(client_id: int) -> list[TreatmentSession]` (newest first, eager-loads `treatment_type`)
- Produces: `TreatmentSessionService.list_sessions_with_content(client_id: int) -> list[TreatmentSession]`
- Removes: `TreatmentSessionService.count_sessions_with_content` (added in Auftrag B1) - every caller now uses `len(list_sessions_with_content(...))` instead, so there is exactly one query defining "has content".
- Consumes (in `client_overview_dialog.py`): the new `list_sessions_with_content`.

- [ ] **Step 1: Remove the three superseded tests and write the three new failing tests**

In `tests/test_treatment_session_service.py`, delete these three existing tests (added in Auftrag B1, now superseded):
- `test_count_sessions_with_content_counts_only_sessions_with_report_or_impulses` (line ~361)
- `test_count_sessions_with_content_is_zero_for_client_without_sessions` (line ~408)
- `test_count_sessions_with_content_does_not_count_empty_string_content` (line ~414)

Add in their place:

```python
def test_list_sessions_with_content_orders_newest_first_and_excludes_contentless(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    older = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 10, 9, 0),
        duration_minutes=60,
    )
    newer = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 20, 9, 0),
        duration_minutes=60,
    )
    without_content = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 25, 9, 0),
        duration_minutes=60,
    )
    treatment_session_service.save_report(older.id, report="<p>Alt</p>", impulses=None)
    treatment_session_service.save_report(newer.id, report="<p>Neu</p>", impulses=None)
    treatment_session_service.save_report(
        without_content.id, report=None, impulses=None
    )

    result = treatment_session_service.list_sessions_with_content(client.id)

    assert [s.id for s in result] == [newer.id, older.id]


def test_list_sessions_with_content_breaks_same_date_ties_deterministically(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    """Two sessions at the exact same date must still come back in a fixed,
    repeatable order (newest-inserted first) rather than whatever order
    SQLite happens to return ties in - Berichtsverlauf must not visibly
    reshuffle same-timestamp sessions between opens."""
    same_date = datetime(2026, 1, 10, 9, 0)
    first_created = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=same_date,
        duration_minutes=60,
    )
    second_created = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=same_date,
        duration_minutes=60,
    )
    treatment_session_service.save_report(
        first_created.id, report="<p>Erste</p>", impulses=None
    )
    treatment_session_service.save_report(
        second_created.id, report="<p>Zweite</p>", impulses=None
    )

    result = treatment_session_service.list_sessions_with_content(client.id)

    assert [s.id for s in result] == [second_created.id, first_created.id]


def test_list_sessions_with_content_includes_session_with_only_impulses(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 10, 9, 0),
        duration_minutes=60,
    )
    treatment_session_service.save_report(
        session.id, report=None, impulses="<p>Impuls</p>"
    )

    result = treatment_session_service.list_sessions_with_content(client.id)

    assert [s.id for s in result] == [session.id]


def test_list_sessions_with_content_excludes_empty_string_content(
    treatment_session_service: TreatmentSessionService,
    session_factory: sessionmaker[Session],
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    """save_report() normalizes blank content to None before it ever reaches
    the database, so this bypasses it to write empty strings directly -
    proving the query itself treats "" as no content, not just that
    save_report() never lets one through (same defense-in-depth this
    class's counting already had in Auftrag B1 - see docs/superpowers/plans
    /2026-09-27-klientenuebersicht.md's final review)."""
    session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 14, 9, 0),
        duration_minutes=60,
    )
    with session_factory() as db_session:
        treatment_session = db_session.get(TreatmentSession, session.id)
        treatment_session.report = ""
        treatment_session.impulses = ""
        db_session.commit()

    assert treatment_session_service.list_sessions_with_content(client.id) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_treatment_session_service.py -k list_sessions_with_content -v`
Expected: FAIL (`AttributeError: 'TreatmentSessionService' object has no attribute 'list_sessions_with_content'`)

- [ ] **Step 3: Implement the repository query**

In `src/klientenverwaltung/repositories/treatment_session_repository.py`, change the import line:

```python
from sqlalchemy import and_, func, or_, select
```

Add a module-level helper and the new method (near `list_for_client`):

```python
def _has_content(column):
    return and_(column.is_not(None), column != "")
```

```python
    def list_with_content_for_client(self, client_id: int) -> list[TreatmentSession]:
        """Sessions for a client with a Bericht or Impulse entered, newest
        first - Auftrag B2's Berichtsverlauf and the "Berichte (n)" count
        on the Klientenübersicht both read this one query, so they can
        never disagree about what counts as "has content". Excludes empty
        strings as well as NULL, even though save_report() never lets a
        blank Bericht/Impulse reach the database as anything but NULL - a
        second, independent guard at the query that produces the count/list.

        Eager-loads treatment_type so callers can read session.treatment_type.name
        after this repository's session/transaction has ended.
        """
        stmt = (
            select(TreatmentSession)
            .where(
                TreatmentSession.client_id == client_id,
                or_(
                    _has_content(TreatmentSession.report),
                    _has_content(TreatmentSession.impulses),
                ),
            )
            .options(joinedload(TreatmentSession.treatment_type))
            .order_by(TreatmentSession.date.desc(), TreatmentSession.id.desc())
        )
        return list(self._session.scalars(stmt))
```

Note the secondary `TreatmentSession.id.desc()` sort key: without it, two sessions at the exact same `date` would come back in whatever order SQLite happens to return ties in - not guaranteed stable across runs. Ordering by id (newest-inserted first) as a tiebreak keeps the Berichtsverlauf's order deterministic and repeatable.

- [ ] **Step 4: Implement the service method and remove the superseded one**

In `src/klientenverwaltung/services/treatment_session_service.py`, replace:

```python
    def count_sessions_with_content(self, client_id: int) -> int:
        """Sessions with a Bericht or Impulse entered (Auftrag A2's report
        window) - drives the "Berichte (n)" button on the Klientenübersicht
        (Auftrag B1)."""
        sessions = self.list_sessions_for_client(client_id)
        return sum(1 for session in sessions if session.report or session.impulses)
```

with:

```python
    def list_sessions_with_content(self, client_id: int) -> list[TreatmentSession]:
        """Sessions with a Bericht or Impulse entered (Auftrag A2's report
        window), newest first - feeds both the Berichtsverlauf dialog and
        the "Berichte (n)" count on the Klientenübersicht (Auftrag B2)."""
        with self._session_factory() as session:
            return TreatmentSessionRepository(session).list_with_content_for_client(
                client_id
            )
```

- [ ] **Step 5: Update the one caller of the removed method**

In `src/klientenverwaltung/ui/client_overview_dialog.py`, replace in `_update_buttons`:

```python
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
```

with:

```python
        report_count = len(
            self._treatment_session_service.list_sessions_with_content(client.id)
        )
        self._report_button.setText(f"Berichte ({report_count})")
        self._report_button.setEnabled(report_count > 0)
        self._report_button.setToolTip(
            "Noch kein Bericht vorhanden" if report_count == 0 else ""
        )
```

(Task 4 wires the button's `clicked` signal; this step only fixes the count/enabled state so the dialog keeps working standalone between tasks.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_treatment_session_service.py -v && uv run ruff check src/klientenverwaltung/repositories/treatment_session_repository.py src/klientenverwaltung/services/treatment_session_service.py src/klientenverwaltung/ui/client_overview_dialog.py`
Expected: all tests PASS; ruff reports no errors

- [ ] **Step 7: Commit**

```bash
git add src/klientenverwaltung/repositories/treatment_session_repository.py src/klientenverwaltung/services/treatment_session_service.py src/klientenverwaltung/ui/client_overview_dialog.py tests/test_treatment_session_service.py
git commit -m "Add sessions-with-content query, replacing B1's count method (Auftrag B2)"
```

---

### Task 2: Extract shared `GrowingTextEdit` widget

**Files:**
- Create: `src/klientenverwaltung/ui/growing_text_edit.py`
- Modify: `src/klientenverwaltung/ui/report_dialog.py`

**Interfaces:**
- Produces: `GrowingTextEdit(QTextEdit)` - `__init__(self, parent: QWidget | None = None)`, no-scrollbar auto-height behavior only.
- Consumes (in `report_dialog.py`): `_GrowingTextEdit` becomes a subclass of `GrowingTextEdit`, adding only the `focused` signal and `insertFromMimeData` paste-stripping - both editing-only concerns that stay private to the Bericht editor.

No new tests for this task - `tests/test_report_dialog.py` only tests `strip_disallowed_formatting`, which is untouched; this is a pure extraction with the exact same runtime behavior for `ReportDialog`. The existing suite proves nothing broke.

- [ ] **Step 1: Create the shared widget**

```python
# src/klientenverwaltung/ui/growing_text_edit.py
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import QSizePolicy, QTextEdit, QWidget

MIN_VISIBLE_LINES = 8


class GrowingTextEdit(QTextEdit):
    """A QTextEdit with no scrollbar of its own: it grows vertically to fit
    its content - never below MIN_VISIBLE_LINES worth of height - so only
    an enclosing QScrollArea ever scrolls.

    Shared by the Bericht editor (Auftrag A2, which subclasses this to add
    editing-specific behavior - see report_dialog._GrowingTextEdit) and the
    read-only Berichtsverlauf (Auftrag B2, used as-is with setReadOnly(True)).
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
        min_height = self.fontMetrics().lineSpacing() * MIN_VISIBLE_LINES + extra
        content_height = self.document().size().height() + extra
        self.setFixedHeight(int(max(min_height, content_height)))
```

- [ ] **Step 2: Slim down `report_dialog.py`'s `_GrowingTextEdit` to a subclass**

Replace the whole existing `_GrowingTextEdit` class body in `src/klientenverwaltung/ui/report_dialog.py`:

```python
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
```

with:

```python
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
```

Add the import (near the other `klientenverwaltung.ui` imports):

```python
from klientenverwaltung.ui.growing_text_edit import GrowingTextEdit
```

Remove `QResizeEvent` and `QSizePolicy` from `report_dialog.py`'s imports - they were only used inside the code just deleted. Also remove the now-unused `_MIN_VISIBLE_LINES = 8` module constant (moved to `growing_text_edit.py` as `MIN_VISIBLE_LINES`).

- [ ] **Step 3: Run tests and ruff**

Run: `uv run pytest tests/test_report_dialog.py -v && uv run ruff check src/klientenverwaltung/ui/report_dialog.py src/klientenverwaltung/ui/growing_text_edit.py`
Expected: all tests PASS; ruff reports no errors (this also catches the unused-import cleanup from Step 2)

- [ ] **Step 4: Commit**

```bash
git add src/klientenverwaltung/ui/growing_text_edit.py src/klientenverwaltung/ui/report_dialog.py
git commit -m "Extract GrowingTextEdit into its own module for reuse (Auftrag B2)"
```

---

### Task 3: `ClientReportHistoryDialog`

**Files:**
- Create: `src/klientenverwaltung/ui/client_report_history_dialog.py`

**Interfaces:**
- Consumes: `TreatmentSessionService.list_sessions_with_content(client_id) -> list[TreatmentSession]` (Task 1), `GrowingTextEdit` (Task 2), `restore_geometry`/`save_geometry`.
- Produces: `ClientReportHistoryDialog(treatment_session_service, client_id: int, client_name: str, parent=None)` - `client_list_widget.py` never touches this; only `ClientOverviewDialog` (Task 4) constructs it and calls `.exec()`.

No automated tests for this task - pure Qt display wiring around an already-tested query, matching this project's existing pattern for `client_detail_dialog.py`/`client_sessions_dialog.py`/`client_overview_dialog.py` (none have dialog-level tests). Verified manually in Task 5.

- [ ] **Step 1: Create the dialog**

```python
# src/klientenverwaltung/ui/client_report_history_dialog.py
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
```

Design notes for the implementer:
- Separation between sessions is generous vertical spacing (`_SESSION_SPACING`), not a drawn line - the spec says "Abstand/Linie" (spacing *or* line), and a drawn `QFrame` line would need a new centrally-themed QSS rule in `theme.py` to avoid an unthemed native line color; spacing alone satisfies the requirement without that extra surface.
- The "–" placeholder is a plain, unstyled `QLabel` - no muted/secondary color - because any color set here at construction time would not react to a live theme switch (the whole app's colors come from one global stylesheet swap in `theme.apply_theme_mode()`, not per-widget styling), and `docs/ui-regeln.md` requires exactly that live-switch behavior. Plainness here already reads as understated next to a full formatted paragraph.
- `GrowingTextEdit(...).setReadOnly(True)` alone satisfies "selectable/copyable but not editable" - Qt's read-only `QTextEdit` still allows text selection and Ctrl+C, it only blocks typing/pasting.
- No stripping of the loaded HTML's formatting is needed here: `ReportDialog._save()` already stripped disallowed formatting before persisting it, so what's stored is already theme-color-free.

- [ ] **Step 2: ruff check**

Run: `uv run ruff check src/klientenverwaltung/ui/client_report_history_dialog.py`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add src/klientenverwaltung/ui/client_report_history_dialog.py
git commit -m "Add read-only Berichtsverlauf dialog (Auftrag B2)"
```

---

### Task 4: Wire "Berichte (n)" on the Klientenübersicht

**Files:**
- Modify: `src/klientenverwaltung/ui/client_overview_dialog.py`

**Interfaces:**
- Consumes: `ClientReportHistoryDialog` (Task 3)

- [ ] **Step 1: Import and connect**

Add the import:

```python
from klientenverwaltung.ui.client_report_history_dialog import ClientReportHistoryDialog
```

In `__init__`, next to the other button connections (`self._sessions_button.clicked.connect(...)`, `self._edit_button.clicked.connect(...)`), add:

```python
        self._report_button.clicked.connect(self._on_report_clicked)
```

Add the handler (near `_on_sessions_clicked`/`_on_edit_clicked`):

```python
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
```

No `self._reload()` call after `dialog.exec()`: unlike Sitzungen/Bearbeiten, Berichtsverlauf is purely read-only - nothing reachable from it can change the client's data, so there is nothing to refresh.

- [ ] **Step 2: ruff check**

Run: `uv run ruff check src/klientenverwaltung/ui/client_overview_dialog.py`
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add src/klientenverwaltung/ui/client_overview_dialog.py
git commit -m "Open Berichtsverlauf from the Klientenübersicht's Berichte button (Auftrag B2)"
```

---

### Task 5: Manual verification (visuals, empty/mixed content, performance)

No automated tests - this task is entirely manual verification per the plan's Review Focus and Auftrag B2's explicit performance requirement (item 4: "Testdaten dafür erzeugen, danach wieder entfernen").

- [ ] **Step 1: Visual/functional check with a handful of throwaway clients**

Write a throwaway script (same pattern as Auftrag B1's manual verification: a temp SQLite file via `create_engine`/`sessionmaker`, never touching real/encrypted data) that creates:
- A client with 3 sessions: one with only a Bericht, one with only Impulse, one with both (with bold/italic/underline/heading formatting in the HTML) - confirms ordering, the "–" placeholder, and formatting rendering.
- A client with sessions but none containing a Bericht/Impulse - confirms `ClientOverviewDialog` shows "Berichte (0)" disabled with the tooltip, and that constructing `ClientReportHistoryDialog` directly against this client does not crash on an empty list.

Open both `ClientOverviewDialog` (to confirm the button state and that clicking "Berichte" opens the history) and `ClientReportHistoryDialog` directly, grab() each to a PNG, and inspect the images. Confirm: newest session first, formatting preserved, "–" for the empty side, no visible scrollbar inside any text area, window title `"Berichte: <name>"`.

- [ ] **Step 2: Performance check with 100 long sessions**

Extend the same throwaway script: for one client, generate 100 sessions dated on 100 different days, each with a long Bericht (e.g. 20+ paragraphs of repeated Lorem-ipsum-style HTML with a mix of bold/italic/headings) and a shorter Impulse. Time the `ClientReportHistoryDialog` construction (`time.perf_counter()` around `ClientReportHistoryDialog(...)`) and confirm it completes quickly enough to feel instant (well under a second is the bar - PyInstaller/production hardware may be slower than the dev machine, but this should not be anywhere close to a multi-second stall). Report the measured time.

Delete the throwaway SQLite file afterward - it must not linger on disk per the "Testdaten... danach wieder entfernen" instruction and the project's storage rules (no client-shaped data outside the encrypted drive).

- [ ] **Step 3: No commit for this task** (verification only)

---

### Task 6: Build the debug executable

- [ ] **Step 1: Build**

Run: `uv run python scripts/build_exe.py --debug`
Expected: build completes without error, producing `klientenverwaltung-debug.exe` (confirms PyInstaller bundling still succeeds with the two new UI modules - no new hidden imports are expected since every Qt class used here is already used elsewhere in the app, but this is what would catch it if one were missed).

- [ ] **Step 2: Report what could and could not be checked in the actual .exe**

This environment has no GUI-interaction/screen-automation tool available, so a human-style click-through of the built .exe's Übersicht/Berichtsverlauf windows is not something the implementer can perform here. Report plainly: the debug build succeeded (or the exact error if not), and that the dialogs' actual behavior was verified via Task 5's programmatic harness against the same source the .exe was built from - not inside the running .exe itself. Say this explicitly rather than implying a manual click-through happened; the user can do that pass themselves with the built .exe if they want it.

- [ ] **Step 3: No commit for this task**

---

### Task 7: Full verification

- [ ] **Step 1: Run the whole test suite**

Run: `uv run pytest -v`
Expected: all tests pass

- [ ] **Step 2: Run ruff over the whole project**

Run: `uv run ruff check .`
Expected: no errors

No commit for this task (verification only, nothing to stage).
