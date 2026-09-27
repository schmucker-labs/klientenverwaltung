# Auftrag C1: Medien zu Sitzungen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let media files (images/videos/audio) be copied onto the encrypted data drive and linked to sessions (many-to-many, files can be reused across sessions), with a background-thread import that shows a themed rotating-logo progress indicator with a real byte-based percentage and a Cancel button, and a per-session "Medien" window to attach/open/unlink files. No in-app playback — the OS's own default program opens the file.

**Architecture:** New `media`/`session_media` tables and SQLAlchemy models. A `MediaRepository` (raw queries only) underneath a new `MediaService` that owns all file-system logic (dedup by sha256, blocked copy with fsync+atomic rename, disk-space check) behind plain-Python callbacks (`progress_callback`, `should_cancel`, `confirm_duplicate`) — no Qt import anywhere in `services/`. The UI runs the import on a `QThread` (`MediaImportWorker`), bridging the duplicate-confirmation callback back to the GUI thread via a `Qt.ConnectionType.BlockingQueuedConnection` signal so a real `QMessageBox` can be shown safely from a background thread. A new reusable `LoadingSpinnerWidget` (two `QPainter`-drawn arcs counter-rotating, colored from the theme palette, mirroring `ui/icons/logo.svg`) sits inside a `LoadingDialog` that only appears after a 500 ms delay. `MediaDialog` (the "Medienfenster") is a `QDialog` built the same way as `ClientSessionsDialog`/`BackupManagementDialog` (`QTableView` + button row + `window_settings` geometry/header helpers). `ClientSessionsDialog` gains a "Medien" button and a "Medien" count column fed by a bulk repository query, the same pattern as the existing "letzte Sitzung"/"nächster Termin" bulk queries. `MediaService` is constructed once in `main.py` and threaded down through `MainWindow → ClientListWidget → ClientDetailDialog`/`ClientOverviewDialog → ClientSessionsDialog`, exactly how `treatment_session_service` already flows.

**Tech Stack:** PySide6 (QThread, QPainter, QMessageBox with `Qt.ConnectionType.BlockingQueuedConnection`), SQLAlchemy 2.x + Alembic, pytest, stdlib `hashlib`/`shutil`/`uuid`/`os`. No new dependencies.

**Spec:** The Auftrag C1 request in this conversation (reproduced in full in Global Constraints/task descriptions below — no separate spec file).

## Global Constraints

- UI text/labels: German. Code/identifiers/table/column names: English.
- "Klient", never "Kunde", anywhere user-visible.
- Dates in the UI: `TT.MM.JJJJ`; session date/time as `TT.MM.JJJJ, HH:MM Uhr` (matches `ReportDialog`'s heading format).
- `services/` never imports anything from `PySide6` — progress/cancel/duplicate-confirmation cross the service boundary as plain callables only.
- Media files are copied into `<drive_root>/medien/`, named `<uuid4 hex><original extension>`; only that relative filename is stored in the DB, never an absolute path (`drive_root` may differ across machines/sessions).
- Deleting a session or client removes only the `session_media` link (DB `ON DELETE CASCADE`); the `media` row and the physical file are never touched by this Auftrag (cleanup is Auftrag C2).
- A treatment-type-style "used, so can't hard-delete" rule does **not** apply to `media` — but `media_id` on `session_media` is `ON DELETE RESTRICT` so a media row can never be deleted while any session still links to it (defensive; nothing in this Auftrag deletes `media` rows at all).
- The import never deletes or moves the user's original source file — only ever reads it.
- No in-app media viewer/player: "Öffnen" always goes through `QDesktopServices.openUrl`.
- Every dialog uses `window_settings.restore_geometry`/`save_geometry` (and, for tables, `restore_header_state`/`save_header_state`/`finalize_column_widths`) under its own QSettings key, and fits 1366×768.
- No hardcoded colors in UI code — only `ColorPalette` values via `get_palette(load_theme_mode())`, same "current theme only" reasoning `ReportDialog`'s toolbar already documents (these dialogs are application-modal, so the user cannot reach the theme toggle while one is open).
- The application only ever loads PNG at runtime, never SVG — the loading spinner is drawn with `QPainter`, not an SVG asset, so this rule is a non-issue here, but no new SVG-at-runtime code must be introduced.
- ruff must pass with no errors; all tests green.
- Commit messages: no `Co-Authored-By: Claude` trailer (public portfolio repo).
- Only test data is ever used while implementing/verifying this (see CLAUDE.md) — never real client media.

## Review Focus

- **Cross-thread SQLite access**: the import runs on a background `QThread` that opens its own DB session while the GUI thread may simultaneously run its own queries (e.g. the user browsing elsewhere). Confirmed empirically (see Task 1) that SQLAlchemy's `pysqlcipher`/`pysqlite` dialect already permits this by default — pinned with a regression test so a future dependency bump can't silently reintroduce `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`.
- **Large file cancel/duplicate interplay**: cancelling *during* the hash-only duplicate-verification pass (same file size as an existing entry, but the user cancels before the hash finishes) must leave no temp file and no DB row — the cancel check must be honored in the same read loop the hashing pass reuses, not just in the copy pass.
- **Same-session double-attach**: attaching a file that is already linked to *this* session (e.g. re-picking the exact same file by accident) must short-circuit to an info message and do nothing — it must not re-ask "vorhandene Datei verwenden?" (that question is only for content that exists in the store but isn't yet linked *here*).
- **Small/instant imports never flash the loading dialog**: a tiny file whose entire copy finishes in a few milliseconds must never show the spinner at all (the 500 ms delayed-show timer must be cancelled/no-op'd once the worker's `finished`/`failed` signal has already arrived).
- **Missing file on disk**: opening or listing media whose physical file was removed from the drive out-of-band (e.g. manually deleted by the user in Explorer) must show "Die Datei wurde auf der Datenplatte nicht gefunden." rather than raising/crashing — covered by an existence check right before `QDesktopServices.openUrl`.

---

### Task 1: Pin the cross-thread SQLite assumption

**Files:**
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: `storage.create_encrypted_engine(db_path: Path, password: str) -> Engine` (existing)
- Produces: nothing new — this only documents/pins an existing, already-relied-upon behavior for Task 6's worker thread.

This whole feature's threading design (Task 6/9) rests on being able to open a DB session from a background `QThread` while the GUI thread also has the engine open. This was verified interactively during planning (`ThreadPoolExecutor` against a real `create_encrypted_engine()`-produced engine: a second thread's own `engine.connect()` succeeded). Pin it so a future SQLAlchemy/sqlcipher3 upgrade can't silently break the media importer.

- [ ] **Step 1: Write the failing/pinning test**

Add to `tests/test_storage.py` (new class, alongside `TestOpenDatabase`):

```python
class TestCreateEncryptedEngineThreading:
    def test_connection_works_from_a_different_thread(self, tmp_path: Path) -> None:
        """The media importer (Auftrag C1) runs its DB writes on a background
        QThread while the GUI thread may still be using this same engine -
        sqlite3 otherwise refuses a connection object outside the thread
        that created it. SQLAlchemy's pysqlcipher/pysqlite dialect already
        passes check_same_thread=False for a file-based database, so this
        already works today; pinned here so a future dependency upgrade
        can't silently take it away.
        """
        from concurrent.futures import ThreadPoolExecutor

        drive = tmp_path / "drive"
        drive.mkdir()
        db_path = drive / storage.DB_FILENAME
        engine = storage.create_encrypted_engine(db_path, "ein-sehr-sicheres-passwort")
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))

            def _query_from_other_thread() -> int:
                with engine.connect() as other_connection:
                    return other_connection.execute(text("SELECT 1")).scalar()

            with ThreadPoolExecutor(max_workers=1) as pool:
                result = pool.submit(_query_from_other_thread).result()
            assert result == 1
        finally:
            engine.dispose()
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/test_storage.py::TestCreateEncryptedEngineThreading -v`
Expected: PASS (this pins existing behavior; no production code changes in this task).

- [ ] **Step 3: Commit**

```bash
git add tests/test_storage.py
git commit -m "test: pin cross-thread SQLite access for the coming media importer"
```

---

### Task 2: Migration + models for `media`/`session_media`

**Files:**
- Create: `alembic/versions/<generated>_add_media_and_session_media.py`
- Create: `src/klientenverwaltung/models/media.py`
- Modify: `src/klientenverwaltung/models/__init__.py`

**Interfaces:**
- Produces: `Media` model (`id`, `stored_filename` unique, `original_filename`, `media_kind: str`, `size_bytes: int`, `sha256: str`, `created_at`)
- Produces: `SessionMedia` model (`session_id` PK/FK→session.id ON DELETE CASCADE, `media_id` PK/FK→media.id ON DELETE RESTRICT, `added_at`)

- [ ] **Step 1: Generate the migration skeleton**

Run: `uv run alembic revision -m "add media and session_media tables"`

This prints the generated revision id (referred to below as `<rev>`) and creates `alembic/versions/<rev>_add_media_and_session_media.py` with empty `upgrade()`/`downgrade()`. Its `down_revision` must be `"c311968e9a6f"` (the current head) — verify this is what got filled in.

- [ ] **Step 2: Fill in the migration**

```python
"""add media and session_media tables

Revision ID: <rev>
Revises: c311968e9a6f
Create Date: ...

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "<rev>"
down_revision: str | Sequence[str] | None = "c311968e9a6f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "media",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("stored_filename", sa.String(), nullable=False),
        sa.Column("original_filename", sa.String(), nullable=False),
        sa.Column("media_kind", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_filename"),
    )
    op.create_index("ix_media_size_bytes", "media", ["size_bytes"])
    op.create_table(
        "session_media",
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("media_id", sa.Integer(), nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["session.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("session_id", "media_id"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("session_media")
    op.drop_index("ix_media_size_bytes", table_name="media")
    op.drop_table("media")
```

- [ ] **Step 3: Write the models**

`src/klientenverwaltung/models/media.py`:

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from klientenverwaltung.models.base import Base


class Media(Base):
    __tablename__ = "media"

    id: Mapped[int] = mapped_column(primary_key=True)
    stored_filename: Mapped[str] = mapped_column(unique=True)
    original_filename: Mapped[str]
    media_kind: Mapped[str]
    size_bytes: Mapped[int] = mapped_column(index=True)
    sha256: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class SessionMedia(Base):
    __tablename__ = "session_media"

    session_id: Mapped[int] = mapped_column(
        ForeignKey("session.id", ondelete="CASCADE"), primary_key=True
    )
    media_id: Mapped[int] = mapped_column(
        ForeignKey("media.id", ondelete="RESTRICT"), primary_key=True
    )
    added_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

No relationships are declared on `Client`/`TreatmentSession`/`Media` — `MediaRepository` (Task 3) queries `session_media` explicitly via joins, matching the "repositories are the only place with SQLAlchemy queries" rule without adding ORM navigation nothing else needs yet.

- [ ] **Step 4: Export the models**

`src/klientenverwaltung/models/__init__.py`:

```python
from klientenverwaltung.models.base import Base
from klientenverwaltung.models.client import Client
from klientenverwaltung.models.media import Media, SessionMedia
from klientenverwaltung.models.session import TreatmentSession
from klientenverwaltung.models.treatment_type import TreatmentType

__all__ = [
    "Base",
    "Client",
    "Media",
    "SessionMedia",
    "TreatmentSession",
    "TreatmentType",
]
```

- [ ] **Step 5: Verify the migration round-trips**

Run: `uv run alembic upgrade head` against a scratch copy is unnecessary — every test's `engine` fixture calls `Base.metadata.create_all(engine)` directly (not via Alembic), so the models are what tests actually exercise. Instead verify Alembic itself is consistent:

Run: `uv run python -c "from klientenverwaltung.models import Base; from sqlalchemy import create_engine; e = create_engine('sqlite:///:memory:'); Base.metadata.create_all(e); print(sorted(Base.metadata.tables))"`
Expected: `['client', 'media', 'session', 'session_media', 'treatment_type']`

Then a real upgrade/downgrade/upgrade round trip against a throwaway file:

Run: `uv run alembic -x db_path=/tmp/does-not-apply upgrade head` — **skip this**, this repo's `alembic/env.py` reads the DB path from `storage`/`config`, not `-x`. Instead trust `apply_migrations()`'s existing test coverage in `tests/test_storage.py` (`TestHasPendingMigrations`) plus the direct `Base.metadata.create_all` check above; do not hand-invoke Alembic against a real drive path for this check.

- [ ] **Step 6: ruff**

Run: `uv run ruff check src/klientenverwaltung/models/media.py src/klientenverwaltung/models/__init__.py alembic/versions/<rev>_add_media_and_session_media.py`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add alembic/versions/<rev>_add_media_and_session_media.py src/klientenverwaltung/models/media.py src/klientenverwaltung/models/__init__.py
git commit -m "feat: add media and session_media tables"
```

---

### Task 3: `MediaRepository`

**Files:**
- Create: `src/klientenverwaltung/repositories/media_repository.py`
- Modify: `src/klientenverwaltung/repositories/__init__.py`

**Interfaces:**
- Consumes: `Media`, `SessionMedia` (Task 2)
- Produces: `MediaRepository(session: Session)` with:
  - `add(media: Media) -> Media`
  - `get_by_id(media_id: int) -> Media | None`
  - `list_by_size(size_bytes: int) -> list[Media]`
  - `is_linked(session_id: int, media_id: int) -> bool`
  - `link(session_id: int, media_id: int) -> None`
  - `unlink(session_id: int, media_id: int) -> bool` (returns whether a link existed)
  - `list_for_session(session_id: int) -> list[tuple[Media, datetime]]` (media + its `session_media.added_at` for *this* session)
  - `count_for_sessions(session_ids: Sequence[int]) -> dict[int, int]`

No dedicated test file: every method here is exercised through `MediaService`'s tests (Task 4), the same way `ClientRepository` has no standalone test file and is only tested via `ClientService`.

- [ ] **Step 1: Write the repository**

```python
from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from klientenverwaltung.models import Media, SessionMedia


class MediaRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, media: Media) -> Media:
        self._session.add(media)
        self._session.flush()
        return media

    def get_by_id(self, media_id: int) -> Media | None:
        return self._session.get(Media, media_id)

    def list_by_size(self, size_bytes: int) -> list[Media]:
        stmt = select(Media).where(Media.size_bytes == size_bytes)
        return list(self._session.scalars(stmt))

    def is_linked(self, session_id: int, media_id: int) -> bool:
        return self._get_link(session_id, media_id) is not None

    def link(self, session_id: int, media_id: int) -> None:
        self._session.add(SessionMedia(session_id=session_id, media_id=media_id))
        self._session.flush()

    def unlink(self, session_id: int, media_id: int) -> bool:
        link = self._get_link(session_id, media_id)
        if link is None:
            return False
        self._session.delete(link)
        return True

    def list_for_session(self, session_id: int) -> list[tuple[Media, datetime]]:
        stmt = (
            select(Media, SessionMedia.added_at)
            .join(SessionMedia, SessionMedia.media_id == Media.id)
            .where(SessionMedia.session_id == session_id)
            .order_by(SessionMedia.added_at)
        )
        return [(media, added_at) for media, added_at in self._session.execute(stmt).all()]

    def count_for_sessions(self, session_ids: Sequence[int]) -> dict[int, int]:
        if not session_ids:
            return {}
        stmt = (
            select(SessionMedia.session_id, func.count(SessionMedia.media_id))
            .where(SessionMedia.session_id.in_(session_ids))
            .group_by(SessionMedia.session_id)
        )
        return dict(self._session.execute(stmt).all())

    def _get_link(self, session_id: int, media_id: int) -> SessionMedia | None:
        return self._session.get(SessionMedia, (session_id, media_id))
```

- [ ] **Step 2: Export it**

`src/klientenverwaltung/repositories/__init__.py`:

```python
from klientenverwaltung.repositories.client_repository import ClientRepository
from klientenverwaltung.repositories.media_repository import MediaRepository
from klientenverwaltung.repositories.treatment_session_repository import (
    TreatmentSessionRepository,
)
from klientenverwaltung.repositories.treatment_type_repository import (
    TreatmentTypeRepository,
)

__all__ = [
    "ClientRepository",
    "MediaRepository",
    "TreatmentSessionRepository",
    "TreatmentTypeRepository",
]
```

- [ ] **Step 3: ruff**

Run: `uv run ruff check src/klientenverwaltung/repositories/media_repository.py src/klientenverwaltung/repositories/__init__.py`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/klientenverwaltung/repositories/media_repository.py src/klientenverwaltung/repositories/__init__.py
git commit -m "feat: add MediaRepository"
```

---

### Task 4: `MediaService`

**Files:**
- Create: `src/klientenverwaltung/services/media_service.py`
- Modify: `src/klientenverwaltung/services/__init__.py`
- Test: `tests/test_media_service.py`
- Test fixtures: `tests/conftest.py` (add `media_service`/`tmp_drive_root` fixtures)

**Interfaces:**
- Consumes: `MediaRepository` (Task 3), `TreatmentSessionRepository.get_by_id` (existing), `transaction()` (existing), `NotFoundError`/`ServiceError` (existing)
- Produces:
  - `MediaKind = Literal["image", "video", "audio", "other"]`
  - `IMAGE_EXTENSIONS`, `VIDEO_EXTENSIONS`, `AUDIO_EXTENSIONS: frozenset[str]`
  - `classify_media_kind(filename: str) -> MediaKind`
  - `SessionMediaEntry` dataclass: `media_id: int`, `stored_filename: str`, `original_filename: str`, `media_kind: MediaKind`, `size_bytes: int`, `added_at: datetime`
  - `ImportOutcome` dataclass: `status: Literal["imported", "linked_existing", "already_linked", "cancelled"]`, `media: Media | None`, `original_filename: str`
  - `MediaService(session_factory: sessionmaker[Session], drive_root: Path)` with:
    - `import_file(session_id: int, source_path: Path, *, progress_callback: Callable[[int, int], None] | None = None, should_cancel: Callable[[], bool] | None = None, confirm_duplicate: Callable[[str], bool] | None = None) -> ImportOutcome`
    - `list_media_for_session(session_id: int) -> list[SessionMediaEntry]`
    - `count_media_for_sessions(session_ids: Sequence[int]) -> dict[int, int]`
    - `remove_link(session_id: int, media_id: int) -> None`
    - `resolve_media_path(media: Media) -> Path`

**Fixture additions** (`tests/conftest.py`, append):

```python
from klientenverwaltung.services import MediaService


@pytest.fixture
def media_service(
    session_factory: sessionmaker[Session], tmp_path: Path
) -> MediaService:
    return MediaService(session_factory, tmp_path / "drive")
```

(`tmp_path / "drive"` deliberately does not exist yet — `import_file()` must create `medien/` under it lazily, matching how a freshly set-up real data drive has no `medien` folder until the first import.)

- [ ] **Step 1: Write the failing tests**

`tests/test_media_service.py`:

```python
import hashlib
from pathlib import Path

import pytest

from klientenverwaltung.models import Client, TreatmentSession, TreatmentType
from klientenverwaltung.services import MediaService, NotFoundError
from klientenverwaltung.services.media_service import ImportOutcome


def _make_source_file(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_import_copies_file_and_links_it_to_the_session(
    media_service: MediaService,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5000)

    outcome = media_service.import_file(treatment_session.id, source)

    assert outcome.status == "imported"
    assert outcome.media is not None
    assert outcome.media.media_kind == "image"
    assert outcome.media.size_bytes == 5000
    assert outcome.media.sha256 == hashlib.sha256(b"a" * 5000).hexdigest()

    stored_path = media_service.resolve_media_path(outcome.media)
    assert stored_path.read_bytes() == b"a" * 5000
    assert stored_path.name != source.name  # neutral uuid name, not the original

    entries = media_service.list_media_for_session(treatment_session.id)
    assert [entry.media_id for entry in entries] == [outcome.media.id]
    assert entries[0].original_filename == "foto.jpg"


def test_duplicate_content_is_linked_not_recopied(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    tmp_path: Path,
) -> None:
    from datetime import datetime

    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 2, 1, 9, 0),
        duration_minutes=45,
    )
    session_a_id = other_session.id
    other_session_b = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 2, 2, 9, 0),
        duration_minutes=45,
    )
    session_b_id = other_session_b.id

    content = b"same bytes" * 1000
    source_a = _make_source_file(tmp_path, "original.mp4", content)
    first = media_service.import_file(session_a_id, source_a)
    assert first.status == "imported"

    # Different filename, identical content, attached to a *different*
    # session - must be recognized as the same file by hash and only
    # linked, never copied a second time.
    source_b = _make_source_file(tmp_path, "kopie.mp4", content)
    confirmations: list[str] = []
    second = media_service.import_file(
        session_b_id,
        source_b,
        confirm_duplicate=lambda original_filename: confirmations.append(
            original_filename
        )
        or True,
    )
    assert second.status == "linked_existing"
    assert second.media.id == first.media.id
    assert confirmations == ["original.mp4"]

    media_dir = media_service.resolve_media_path(first.media).parent
    assert len(list(media_dir.glob("*.mp4"))) == 1  # copied exactly once

    # Attaching the *same* content to session_a again, where it is already
    # linked: must short-circuit to "already_linked" without even asking.
    source_c = _make_source_file(tmp_path, "nochmal.mp4", content)
    third = media_service.import_file(
        session_a_id,
        source_c,
        confirm_duplicate=lambda _original_filename: pytest.fail(
            "must not ask when already linked to this session"
        ),
    )
    assert third.status == "already_linked"
    assert third.media.id == first.media.id


def test_cancel_during_copy_leaves_no_file_and_no_db_row(
    session_factory, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    drive_root = tmp_path / "drive"
    service = MediaService(session_factory, drive_root)
    source = _make_source_file(tmp_path, "video.mp4", b"x" * (2 * 1024 * 1024))

    outcome = service.import_file(
        treatment_session.id, source, should_cancel=lambda: True
    )

    assert outcome == ImportOutcome("cancelled", None, "video.mp4")
    media_dir = drive_root / "medien"
    leftovers = list(media_dir.glob("*")) if media_dir.exists() else []
    assert leftovers == []
    assert service.list_media_for_session(treatment_session.id) == []


def test_deleting_session_removes_link_but_keeps_media_and_file(
    media_service: MediaService,
    session_factory,
    treatment_session_service,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    from klientenverwaltung.repositories import MediaRepository

    source = _make_source_file(tmp_path, "aufnahme.mp3", b"audio" * 100)
    outcome = media_service.import_file(treatment_session.id, source)
    media_id = outcome.media.id
    stored_path = media_service.resolve_media_path(outcome.media)

    treatment_session_service.delete_session(treatment_session.id)

    assert media_service.list_media_for_session(treatment_session.id) == []
    assert stored_path.exists()  # file untouched (cleanup is Auftrag C2)
    with session_factory() as session:
        assert MediaRepository(session).get_by_id(media_id) is not None


def test_resolve_media_path_uses_the_given_drive_root(
    session_factory, tmp_path: Path, treatment_session: TreatmentSession
) -> None:
    original_root = tmp_path / "drive-one"
    service_a = MediaService(session_factory, original_root)
    source = _make_source_file(tmp_path, "bild.png", b"p" * 10)
    outcome = service_a.import_file(treatment_session.id, source)

    # Same database, different drive_root (e.g. the drive was remounted
    # under a different letter, or opened from a different machine) -
    # resolve_media_path must follow the new root, since only the relative
    # stored_filename is ever persisted.
    other_root = tmp_path / "drive-two"
    service_b = MediaService(session_factory, other_root)
    resolved = service_b.resolve_media_path(outcome.media)

    assert resolved == other_root / "medien" / outcome.media.stored_filename
    assert not str(resolved).startswith(str(original_root))


def test_import_raises_not_found_for_unknown_session(
    media_service: MediaService, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "x.jpg", b"x")
    with pytest.raises(NotFoundError):
        media_service.import_file(999, source)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_media_service.py -v`
Expected: FAIL (collection error — `klientenverwaltung.services.media_service` does not exist yet).

- [ ] **Step 3: Implement `MediaService`**

`src/klientenverwaltung/services/media_service.py`:

```python
from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session, sessionmaker

from klientenverwaltung.models import Media
from klientenverwaltung.repositories import MediaRepository, TreatmentSessionRepository
from klientenverwaltung.services.errors import NotFoundError, ServiceError
from klientenverwaltung.services.transaction import transaction

MEDIA_FOLDER_NAME = "medien"
_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB per progress tick

MediaKind = Literal["image", "video", "audio", "other"]

IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif", ".heic"}
)
VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".m4v"})
AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".wma"})


def classify_media_kind(filename: str) -> MediaKind:
    extension = Path(filename).suffix.lower()
    if extension in IMAGE_EXTENSIONS:
        return "image"
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    return "other"


@dataclass(frozen=True)
class SessionMediaEntry:
    """One row of a session's media list (Auftrag C1's Medienfenster) -
    original_filename/media_kind/size_bytes describe the underlying file,
    added_at is when *this session* was linked to it (not when the file
    was first ever imported, which may predate this link by a lot if the
    same recording is reused across several sessions)."""

    media_id: int
    stored_filename: str
    original_filename: str
    media_kind: MediaKind
    size_bytes: int
    added_at: datetime


@dataclass(frozen=True)
class ImportOutcome:
    """Result of MediaService.import_file():
    - "imported": a genuinely new file was copied onto the drive.
    - "linked_existing": identical content already existed in the media
      store (under a possibly different original filename) and the user
      confirmed reusing it - nothing was copied.
    - "already_linked": identical content already existed *and* was
      already linked to this exact session - nothing was asked or done.
    - "cancelled": should_cancel() returned True, or the user declined the
      "vorhandene Datei verwenden?" question - no file and no DB row.
    `media` is None only for "cancelled".
    """

    status: Literal["imported", "linked_existing", "already_linked", "cancelled"]
    media: Media | None
    original_filename: str


def _process_file(
    source_path: Path,
    total_size: int,
    *,
    copy_to: Path | None,
    progress_callback: Callable[[int, int], None] | None,
    should_cancel: Callable[[], bool] | None,
) -> str | None:
    """Reads source_path in blocks, sha256-hashing it, optionally writing
    each block to copy_to at the same time (a single read pass covers
    both hashing and copying, so a large file is never read twice just to
    be copied). Returns the hex digest, or None if should_cancel() became
    true partway through - the caller is responsible for removing any
    partial copy_to file in that case, and for anything already written
    when an OSError propagates out of here.
    """
    digest = hashlib.sha256()
    done = 0
    dest_file = copy_to.open("wb") if copy_to is not None else None
    try:
        with source_path.open("rb") as source_file:
            while True:
                if should_cancel is not None and should_cancel():
                    return None
                chunk = source_file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                digest.update(chunk)
                if dest_file is not None:
                    dest_file.write(chunk)
                done += len(chunk)
                if progress_callback is not None:
                    progress_callback(done, total_size)
        if dest_file is not None:
            dest_file.flush()
            os.fsync(dest_file.fileno())
        return digest.hexdigest()
    finally:
        if dest_file is not None:
            dest_file.close()


class MediaService:
    def __init__(self, session_factory: sessionmaker[Session], drive_root: Path) -> None:
        self._session_factory = session_factory
        self._drive_root = drive_root
        self._media_dir = drive_root / MEDIA_FOLDER_NAME

    def import_file(
        self,
        session_id: int,
        source_path: Path,
        *,
        progress_callback: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
        confirm_duplicate: Callable[[str], bool] | None = None,
    ) -> ImportOutcome:
        if not source_path.is_file():
            raise ServiceError(f"Datei wurde nicht gefunden: {source_path}")
        size_bytes = source_path.stat().st_size

        free_bytes = shutil.disk_usage(self._drive_root).free
        if free_bytes < size_bytes:
            raise ServiceError(
                "Auf der Datenplatte ist nicht genügend freier Speicherplatz "
                "frei, um diese Datei zu kopieren."
            )

        with self._session_factory() as session:
            if TreatmentSessionRepository(session).get_by_id(session_id) is None:
                raise NotFoundError(f"Sitzung mit ID {session_id} wurde nicht gefunden.")

            media_repo = MediaRepository(session)
            same_size_candidates = media_repo.list_by_size(size_bytes)
            digest_hint: str | None = None

            if same_size_candidates:
                digest_hint = _process_file(
                    source_path,
                    size_bytes,
                    copy_to=None,
                    progress_callback=progress_callback,
                    should_cancel=should_cancel,
                )
                if digest_hint is None:
                    return ImportOutcome("cancelled", None, source_path.name)

                match = next(
                    (m for m in same_size_candidates if m.sha256 == digest_hint), None
                )
                if match is not None:
                    if media_repo.is_linked(session_id, match.id):
                        return ImportOutcome(
                            "already_linked", match, match.original_filename
                        )
                    if confirm_duplicate is None or not confirm_duplicate(
                        match.original_filename
                    ):
                        return ImportOutcome("cancelled", None, match.original_filename)
                    media_repo.link(session_id, match.id)
                    with transaction(
                        session, "Datei konnte nicht zugeordnet werden."
                    ):
                        pass
                    return ImportOutcome(
                        "linked_existing", match, match.original_filename
                    )

            media = self._copy_and_store(
                source_path, size_bytes, digest_hint, progress_callback, should_cancel
            )
            if media is None:
                return ImportOutcome("cancelled", None, source_path.name)

            media_repo.add(media)
            media_repo.link(session_id, media.id)
            with transaction(session, "Datei konnte nicht gespeichert werden."):
                pass
        return ImportOutcome("imported", media, source_path.name)

    def _copy_and_store(
        self,
        source_path: Path,
        size_bytes: int,
        known_digest: str | None,
        progress_callback: Callable[[int, int], None] | None,
        should_cancel: Callable[[], bool] | None,
    ) -> Media | None:
        self._media_dir.mkdir(parents=True, exist_ok=True)
        extension = source_path.suffix.lower()
        stored_filename = f"{uuid.uuid4().hex}{extension}"
        temp_path = self._media_dir / f"{stored_filename}.part"
        final_path = self._media_dir / stored_filename
        try:
            digest = _process_file(
                source_path,
                size_bytes,
                copy_to=temp_path,
                progress_callback=progress_callback,
                should_cancel=should_cancel,
            )
            if digest is None:
                temp_path.unlink(missing_ok=True)
                return None
            temp_path.rename(final_path)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise ServiceError(f"Datei konnte nicht kopiert werden: {exc}") from exc
        return Media(
            stored_filename=stored_filename,
            original_filename=source_path.name,
            media_kind=classify_media_kind(source_path.name),
            size_bytes=size_bytes,
            sha256=known_digest or digest,
        )

    def list_media_for_session(self, session_id: int) -> list[SessionMediaEntry]:
        with self._session_factory() as session:
            rows = MediaRepository(session).list_for_session(session_id)
        return [
            SessionMediaEntry(
                media_id=media.id,
                stored_filename=media.stored_filename,
                original_filename=media.original_filename,
                media_kind=media.media_kind,  # type: ignore[arg-type]
                size_bytes=media.size_bytes,
                added_at=added_at,
            )
            for media, added_at in rows
        ]

    def count_media_for_sessions(self, session_ids: Sequence[int]) -> dict[int, int]:
        with self._session_factory() as session:
            return MediaRepository(session).count_for_sessions(session_ids)

    def remove_link(self, session_id: int, media_id: int) -> None:
        with self._session_factory() as session:
            repo = MediaRepository(session)
            if not repo.unlink(session_id, media_id):
                raise NotFoundError(
                    "Diese Datei ist dieser Sitzung nicht zugeordnet."
                )
            with transaction(session, "Verknüpfung konnte nicht entfernt werden."):
                pass

    def resolve_media_path(self, media: Media) -> Path:
        return self._media_dir / media.stored_filename
```

Note the `digest = _process_file(...)` reassignment inside `_copy_and_store`'s try-block shadows the outer `digest` name from `import_file` — that's fine, they're different scopes; the final `sha256=known_digest or digest` line picks whichever one is actually meaningful (the freshly computed one, unless `known_digest` was already established by the same-size hash-only pass).

- [ ] **Step 4: Export from services**

`src/klientenverwaltung/services/__init__.py` (add to existing content):

```python
from klientenverwaltung.services.media_service import (
    ImportOutcome,
    MediaKind,
    MediaService,
    SessionMediaEntry,
    classify_media_kind,
)
```

and add `"ImportOutcome"`, `"MediaKind"`, `"MediaService"`, `"SessionMediaEntry"`, `"classify_media_kind"` to `__all__` (keep the list alphabetically sorted, matching the existing style).

- [ ] **Step 5: Add the fixtures**

Add the `media_service` fixture shown above to `tests/conftest.py` (needs `from klientenverwaltung.services import MediaService` added to its imports).

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_media_service.py -v`
Expected: PASS (6 tests).

- [ ] **Step 7: Run the full suite + ruff**

Run: `uv run pytest -q`
Run: `uv run ruff check src/klientenverwaltung/services/media_service.py src/klientenverwaltung/services/__init__.py tests/test_media_service.py tests/conftest.py`
Expected: all green, no lint errors.

- [ ] **Step 8: Commit**

```bash
git add src/klientenverwaltung/services/media_service.py src/klientenverwaltung/services/__init__.py tests/test_media_service.py tests/conftest.py
git commit -m "feat: add MediaService (import, dedup, linking)"
```

---

### Task 5: `LoadingSpinnerWidget`

**Files:**
- Create: `src/klientenverwaltung/ui/loading_spinner.py`

**Interfaces:**
- Produces: `LoadingSpinnerWidget(QWidget)` with `set_colors(outer: str, inner: str) -> None`

No automated test (pure paint code with no business logic to assert on) — verified visually in Task 13's manual pass, consistent with how `ui/theme.py`'s arrow-icon rendering and `ReportDialog`'s letter-icon rendering have no dedicated tests either.

- [ ] **Step 1: Write the widget**

```python
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QHideEvent, QPainter, QPaintEvent, QPen, QShowEvent
from PySide6.QtWidgets import QWidget

_WIDGET_SIZE = 72
_TICK_INTERVAL_MS = 30
_OUTER_DEGREES_PER_TICK = 6
_INNER_DEGREES_PER_TICK = 8
# Degrees drawn out of 360, mirroring ui/icons/logo.svg's two arcs (dasharray
# "382 96" / circumference ~478 -> ~80%; "202 88" / circumference ~289 ->
# ~70%) - not copied exactly, close enough to read as "the same two arcs".
_OUTER_ARC_SPAN_DEGREES = 288
_INNER_ARC_SPAN_DEGREES = 252
_OUTER_PEN_WIDTH = 7
_INNER_PEN_WIDTH = 5
_OUTER_MARGIN = 4
_INNER_MARGIN = 20


class LoadingSpinnerWidget(QWidget):
    """The two half-circles from the app logo, counter-rotating - used by
    LoadingDialog while a media import runs. Colors must be set explicitly
    via set_colors() (normally the theme's accent/accent_secondary) before
    it looks right; it starts with a plausible fallback so it never paints
    literally colorless if a caller forgets.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_WIDGET_SIZE, _WIDGET_SIZE)
        self._outer_angle = 0
        self._inner_angle = 0
        self._outer_color = QColor("#A7654F")
        self._inner_color = QColor("#B89A67")
        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_INTERVAL_MS)
        self._timer.timeout.connect(self._advance)

    def set_colors(self, outer: str, inner: str) -> None:
        self._outer_color = QColor(outer)
        self._inner_color = QColor(inner)
        self.update()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._timer.start()

    def hideEvent(self, event: QHideEvent) -> None:
        self._timer.stop()
        super().hideEvent(event)

    def _advance(self) -> None:
        self._outer_angle = (self._outer_angle + _OUTER_DEGREES_PER_TICK) % 360
        self._inner_angle = (self._inner_angle - _INNER_DEGREES_PER_TICK) % 360
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        outer_pen = QPen(self._outer_color)
        outer_pen.setWidth(_OUTER_PEN_WIDTH)
        outer_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(outer_pen)
        outer_rect = self.rect().adjusted(
            _OUTER_MARGIN, _OUTER_MARGIN, -_OUTER_MARGIN, -_OUTER_MARGIN
        )
        painter.drawArc(outer_rect, self._outer_angle * 16, _OUTER_ARC_SPAN_DEGREES * 16)

        inner_pen = QPen(self._inner_color)
        inner_pen.setWidth(_INNER_PEN_WIDTH)
        inner_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(inner_pen)
        inner_rect = self.rect().adjusted(
            _INNER_MARGIN, _INNER_MARGIN, -_INNER_MARGIN, -_INNER_MARGIN
        )
        painter.drawArc(inner_rect, self._inner_angle * 16, _INNER_ARC_SPAN_DEGREES * 16)
        painter.end()
```

- [ ] **Step 2: ruff**

Run: `uv run ruff check src/klientenverwaltung/ui/loading_spinner.py`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/klientenverwaltung/ui/loading_spinner.py
git commit -m "feat: add rotating two-arc loading spinner widget"
```

---

### Task 6: `LoadingDialog`

**Files:**
- Create: `src/klientenverwaltung/ui/loading_dialog.py`

**Interfaces:**
- Consumes: `LoadingSpinnerWidget` (Task 5), `get_palette`/`load_theme_mode` (existing)
- Produces: `LoadingDialog(QDialog)` with `Signal cancelled`, `set_progress(done: int, total: int) -> None`, `finish() -> None`

- [ ] **Step 1: Write the dialog**

```python
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from klientenverwaltung.ui.loading_spinner import LoadingSpinnerWidget
from klientenverwaltung.ui.theme import get_palette, load_theme_mode

_SHOW_DELAY_MS = 500


class LoadingDialog(QDialog):
    """A themed progress indicator for a long-running background operation
    (Auftrag C1's media import). Never appears for an operation that
    finishes within _SHOW_DELAY_MS, so a small file's import never flashes
    it on screen - call finish() exactly once, from the operation's
    completion handler, whether or not this ever became visible.
    """

    cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bitte warten")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        palette = get_palette(load_theme_mode())
        self._spinner = LoadingSpinnerWidget(self)
        self._spinner.set_colors(palette.accent, palette.accent_secondary)

        self._percent_label = QLabel("0 %", self)
        self._percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        cancel_button = QPushButton("Abbrechen", self)
        cancel_button.clicked.connect(self._on_cancel_clicked)

        layout = QVBoxLayout(self)
        layout.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._percent_label)
        layout.addWidget(cancel_button, 0, Qt.AlignmentFlag.AlignHCenter)

        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.setInterval(_SHOW_DELAY_MS)
        self._show_timer.timeout.connect(self.show)
        self._show_timer.start()

    def set_progress(self, done: int, total: int) -> None:
        percent = 0 if total <= 0 else min(100, round(done * 100 / total))
        self._percent_label.setText(f"{percent} %")

    def finish(self) -> None:
        """Call exactly once when the underlying operation is done
        (success, failure, or cancelled) - stops the delayed-show timer
        (so it can't pop the dialog back up afterwards) and closes it,
        harmless even if it was never shown at all.
        """
        self._show_timer.stop()
        self.close()

    def _on_cancel_clicked(self) -> None:
        self.cancelled.emit()

    def reject(self) -> None:
        # Escape/close button acts exactly like the Abbrechen button - the
        # caller is still responsible for actually closing this dialog via
        # finish() once the cancellation has taken effect, so this must
        # NOT call super().reject() itself.
        self._on_cancel_clicked()
```

- [ ] **Step 2: ruff**

Run: `uv run ruff check src/klientenverwaltung/ui/loading_dialog.py`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/klientenverwaltung/ui/loading_dialog.py
git commit -m "feat: add LoadingDialog (delayed-show progress + cancel)"
```

---

### Task 7: `MediaImportWorker` (QThread bridge)

**Files:**
- Create: `src/klientenverwaltung/ui/media_import_worker.py`

**Interfaces:**
- Consumes: `MediaService.import_file` (Task 4)
- Produces: `MediaImportWorker(QObject)` with signals `progress(int, int)`, `duplicate_found(str)`, `finished(object)` (an `ImportOutcome`), `failed(str)`; methods `run() -> None` (a `@Slot`), `cancel() -> None`, `set_duplicate_answer(bool) -> None`

- [ ] **Step 1: Write the worker**

```python
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from klientenverwaltung.services import MediaService, ServiceError


class MediaImportWorker(QObject):
    """Runs MediaService.import_file() on a background QThread.

    duplicate_found must be connected with Qt.ConnectionType.BlockingQueuedConnection
    to a GUI-thread slot that shows a QMessageBox and calls
    set_duplicate_answer() before returning - that connection type is what
    makes emit() here block this worker thread until the GUI thread's slot
    has actually finished, which is the only safe way to show a modal
    dialog in response to something happening on a non-GUI thread.
    """

    progress = Signal(int, int)
    duplicate_found = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, media_service: MediaService, session_id: int, source_path: Path) -> None:
        super().__init__()
        self._media_service = media_service
        self._session_id = session_id
        self._source_path = source_path
        self._cancel_event = threading.Event()
        self._duplicate_answer = False

    def cancel(self) -> None:
        self._cancel_event.set()

    def set_duplicate_answer(self, answer: bool) -> None:
        self._duplicate_answer = answer

    @Slot()
    def run(self) -> None:
        try:
            outcome = self._media_service.import_file(
                self._session_id,
                self._source_path,
                progress_callback=lambda done, total: self.progress.emit(done, total),
                should_cancel=self._cancel_event.is_set,
                confirm_duplicate=self._ask_duplicate,
            )
        except ServiceError as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(outcome)

    def _ask_duplicate(self, original_filename: str) -> bool:
        self._duplicate_answer = False
        self.duplicate_found.emit(original_filename)
        return self._duplicate_answer
```

- [ ] **Step 2: ruff**

Run: `uv run ruff check src/klientenverwaltung/ui/media_import_worker.py`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/klientenverwaltung/ui/media_import_worker.py
git commit -m "feat: add MediaImportWorker (background-thread import bridge)"
```

---

### Task 8: `ask_use_existing_file` dialog helper

**Files:**
- Modify: `src/klientenverwaltung/ui/dialogs.py`

**Interfaces:**
- Produces: `ask_use_existing_file(original_filename: str, *, parent: QWidget | None = None) -> bool`

- [ ] **Step 1: Add the helper**

Append to `src/klientenverwaltung/ui/dialogs.py`:

```python
def ask_use_existing_file(
    original_filename: str, *, parent: QWidget | None = None
) -> bool:
    """Shown when an imported file's content already exists in the media
    store under a possibly different name; Ja links the existing file
    without copying again, Nein skips attaching this file at all (the
    duplicate is not stored a second time - Auftrag C1's dedup would
    otherwise be pointless).
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Datei bereits vorhanden")
    box.setText(
        f'Diese Datei ist bereits vorhanden als "{original_filename}". '
        "Vorhandene Datei verwenden?"
    )
    yes_button = box.addButton("Ja", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Nein", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(yes_button)
    box.exec()
    return box.clickedButton() is yes_button
```

- [ ] **Step 2: ruff**

Run: `uv run ruff check src/klientenverwaltung/ui/dialogs.py`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/klientenverwaltung/ui/dialogs.py
git commit -m "feat: add ask_use_existing_file dialog helper"
```

---

### Task 9: `MediaTableModel`

**Files:**
- Create: `src/klientenverwaltung/ui/media_table_model.py`

**Interfaces:**
- Consumes: `SessionMediaEntry` (Task 4)
- Produces: `COLUMN_TITLES`, `MediaTableModel(QAbstractTableModel)` with `set_entries(list[SessionMediaEntry]) -> None`, `entry_at(row: int) -> SessionMediaEntry`; module-level `format_size_bytes(size_bytes: int) -> str`

- [ ] **Step 1: Write the model**

```python
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from klientenverwaltung.services.media_service import MediaKind, SessionMediaEntry

COLUMN_TITLES = ("Name", "Art", "Größe", "Hinzugefügt am")
_KIND_LABELS: dict[MediaKind, str] = {
    "image": "Bild",
    "video": "Video",
    "audio": "Audio",
    "other": "Sonstige",
}


def format_size_bytes(size_bytes: int) -> str:
    """Human-readable size with a German comma decimal separator, e.g.
    "1,4 GB" - distinct from backup_table_model._format_size (MB/KB only,
    period separator), since backups stay in the low-MB range while media
    files routinely reach several GB.
    """
    for suffix, factor in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if size_bytes >= factor:
            return f"{size_bytes / factor:.1f}".replace(".", ",") + f" {suffix}"
    return f"{size_bytes} B"


class MediaTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._entries: list[SessionMediaEntry] = []

    def set_entries(self, entries: list[SessionMediaEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def entry_at(self, row: int) -> SessionMediaEntry:
        return self._entries[row]

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._entries)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(COLUMN_TITLES)

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> object:
        if (
            role != Qt.ItemDataRole.DisplayRole
            or orientation != Qt.Orientation.Horizontal
        ):
            return None
        if 0 <= section < len(COLUMN_TITLES):
            return COLUMN_TITLES[section]
        return None

    def data(
        self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if not index.isValid():
            return None
        entry = self._entries[index.row()]
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        column = index.column()
        if column == 0:
            return entry.original_filename
        if column == 1:
            return _KIND_LABELS[entry.media_kind]
        if column == 2:
            return format_size_bytes(entry.size_bytes)
        if column == 3:
            return entry.added_at.strftime("%d.%m.%Y %H:%M")
        return None
```

- [ ] **Step 2: ruff**

Run: `uv run ruff check src/klientenverwaltung/ui/media_table_model.py`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/klientenverwaltung/ui/media_table_model.py
git commit -m "feat: add MediaTableModel"
```

---

### Task 10: `MediaDialog` (the Medienfenster)

**Files:**
- Create: `src/klientenverwaltung/ui/media_dialog.py`

**Interfaces:**
- Consumes: `MediaService` (Task 4), `MediaImportWorker` (Task 7), `LoadingDialog` (Task 6), `MediaTableModel`/`format_size_bytes` (Task 9), `ask_use_existing_file`/`ask_confirm_delete`/`show_error`/`show_info` (existing + Task 8), `IMAGE_EXTENSIONS`/`VIDEO_EXTENSIONS`/`AUDIO_EXTENSIONS` (Task 4), `window_settings` helpers (existing)
- Produces: `MediaDialog(QDialog)` constructed as `MediaDialog(media_service, session, client_name, parent=None)`

- [ ] **Step 1: Write the dialog**

```python
import os
from pathlib import Path

from PySide6.QtCore import QThread, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.models import TreatmentSession
from klientenverwaltung.services import ServiceError
from klientenverwaltung.services.media_service import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    VIDEO_EXTENSIONS,
    ImportOutcome,
    MediaService,
    SessionMediaEntry,
)
from klientenverwaltung.ui.dialogs import (
    ask_confirm_delete,
    ask_use_existing_file,
    show_error,
    show_info,
)
from klientenverwaltung.ui.loading_dialog import LoadingDialog
from klientenverwaltung.ui.media_import_worker import MediaImportWorker
from klientenverwaltung.ui.media_table_model import COLUMN_TITLES, MediaTableModel
from klientenverwaltung.ui.window_settings import (
    finalize_column_widths,
    restore_geometry,
    restore_header_state,
    save_geometry,
    save_header_state,
)

_GEOMETRY_SETTINGS_KEY = "media_dialog/geometry"
_TABLE_HEADER_SETTINGS_KEY = "media_dialog/header_state"
_NAME_COLUMN = 0


def _build_file_filter() -> str:
    extensions = sorted(IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS)
    patterns = " ".join(f"*{ext}" for ext in extensions)
    return f"Medien ({patterns});;Alle Dateien (*)"


_FILE_FILTER = _build_file_filter()


class MediaDialog(QDialog):
    """Medien zur Sitzung (Auftrag C1) - list/attach/open/unlink files
    copied onto the data drive for one session. No in-app viewer: "Öffnen"
    always defers to Windows' own default program for the file type.
    """

    def __init__(
        self,
        media_service: MediaService,
        session: TreatmentSession,
        client_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._media_service = media_service
        self._session_id = session.id
        self._thread: QThread | None = None
        self._worker: MediaImportWorker | None = None
        self._loading_dialog: LoadingDialog | None = None

        self.setWindowTitle(f"Medien: {client_name}")
        self.setModal(True)
        self.resize(650, 450)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        heading = QLabel(
            "Medien zur Sitzung vom "
            f"{session.date.strftime('%d.%m.%Y, %H:%M')} Uhr – "
            f"{session.treatment_type.name}",
            self,
        )
        heading.setWordWrap(True)
        heading_font = heading.font()
        heading_font.setBold(True)
        heading.setFont(heading_font)

        self._table_model = MediaTableModel()
        self._table_view = QTableView(self)
        self._table_view.setModel(self._table_model)
        self._table_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self._table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table_view.verticalHeader().setVisible(False)
        self._table_view.doubleClicked.connect(self._on_open_clicked)

        self._attach_button = QPushButton("Datei anfügen …", self)
        self._open_button = QPushButton("Öffnen", self)
        self._remove_link_button = QPushButton("Verknüpfung entfernen", self)
        self._open_button.setEnabled(False)
        self._remove_link_button.setEnabled(False)
        self._attach_button.clicked.connect(self._on_attach_clicked)
        self._open_button.clicked.connect(self._on_open_clicked)
        self._remove_link_button.clicked.connect(self._on_remove_link_clicked)

        button_row = QHBoxLayout()
        button_row.addWidget(self._attach_button)
        button_row.addWidget(self._open_button)
        button_row.addWidget(self._remove_link_button)
        button_row.addStretch()

        self._close_button = QPushButton("Schließen", self)
        self._close_button.clicked.connect(self.accept)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(self._close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(self._table_view, 1)
        layout.addLayout(button_row)
        layout.addLayout(close_row)

        self._reload_media()

        header = self._table_view.horizontalHeader()
        restored = restore_header_state(header, _TABLE_HEADER_SETTINGS_KEY, COLUMN_TITLES)
        if not restored:
            self._table_view.resizeColumnsToContents()
        finalize_column_widths(header, self._table_model.columnCount(), _NAME_COLUMN, restored)
        header.sectionResized.connect(self._save_table_header_state)
        self._table_view.selectionModel().selectionChanged.connect(
            self._update_button_states
        )

    def _save_table_header_state(self) -> None:
        save_header_state(
            self._table_view.horizontalHeader(), _TABLE_HEADER_SETTINGS_KEY, COLUMN_TITLES
        )

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)

    def _reload_media(self) -> None:
        entries = self._media_service.list_media_for_session(self._session_id)
        self._table_model.set_entries(entries)
        self._update_button_states()

    def _selected_entry(self) -> SessionMediaEntry | None:
        rows = self._table_view.selectionModel().selectedRows()
        if len(rows) != 1:
            return None
        return self._table_model.entry_at(rows[0].row())

    def _update_button_states(self) -> None:
        has_selection = self._selected_entry() is not None
        self._open_button.setEnabled(has_selection)
        self._remove_link_button.setEnabled(has_selection)

    def _on_attach_clicked(self) -> None:
        path_str, _selected_filter = QFileDialog.getOpenFileName(
            self, "Datei anfügen", "", _FILE_FILTER
        )
        if not path_str:
            return
        self._start_import(Path(path_str))

    def _start_import(self, source_path: Path) -> None:
        self._set_busy(True)
        self._loading_dialog = LoadingDialog(self)
        self._thread = QThread(self)
        self._worker = MediaImportWorker(self._media_service, self._session_id, source_path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._loading_dialog.set_progress)
        self._loading_dialog.cancelled.connect(self._worker.cancel)
        self._worker.duplicate_found.connect(
            self._on_duplicate_found, Qt.ConnectionType.BlockingQueuedConnection
        )
        self._worker.finished.connect(
            lambda outcome: self._on_import_finished(outcome, source_path)
        )
        self._worker.failed.connect(self._on_import_failed)
        self._thread.start()

    def _on_duplicate_found(self, original_filename: str) -> None:
        answer = ask_use_existing_file(original_filename, parent=self)
        assert self._worker is not None
        self._worker.set_duplicate_answer(answer)

    def _cleanup_thread(self) -> None:
        assert self._thread is not None
        self._thread.quit()
        self._thread.wait()
        self._thread = None
        self._worker = None
        self._set_busy(False)

    def _set_busy(self, busy: bool) -> None:
        self._attach_button.setEnabled(not busy)
        self._close_button.setEnabled(not busy)

    def _on_import_finished(self, outcome: ImportOutcome, source_path: Path) -> None:
        assert self._loading_dialog is not None
        self._loading_dialog.finish()
        self._cleanup_thread()
        self._reload_media()
        if outcome.status == "imported":
            show_info(
                "Die Datei wurde auf die Datenplatte übernommen. Das Original "
                f"liegt weiterhin unter {source_path}. Es kann Gesundheitsdaten "
                "enthalten – bitte löschen Sie es selbst, wenn es nicht mehr "
                "gebraucht wird.",
                parent=self,
            )
        elif outcome.status == "already_linked":
            show_info(
                "Diese Datei ist dieser Sitzung bereits zugeordnet.", parent=self
            )

    def _on_import_failed(self, message: str) -> None:
        assert self._loading_dialog is not None
        self._loading_dialog.finish()
        self._cleanup_thread()
        show_error(message, parent=self)

    def _on_open_clicked(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        path = self._media_service.resolve_media_path_for_entry(entry)
        if not path.exists():
            show_error(
                "Die Datei wurde auf der Datenplatte nicht gefunden.", parent=self
            )
            return
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path))):
            show_error(
                "Für diese Datei ist auf diesem Computer kein Programm zum "
                "Öffnen hinterlegt.",
                parent=self,
            )

    def _on_remove_link_clicked(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        confirmed = ask_confirm_delete(
            f'Verknüpfung von "{entry.original_filename}" zu dieser Sitzung '
            "entfernen? Die Datei selbst bleibt erhalten.",
            title="Verknüpfung entfernen",
            parent=self,
        )
        if not confirmed:
            return
        try:
            self._media_service.remove_link(self._session_id, entry.media_id)
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return
        self._reload_media()
```

`resolve_media_path` (Task 4) takes a `Media` model, but the table model only holds `SessionMediaEntry` (no live `Media` object) - add a small overload-by-name to `MediaService` in this task rather than Task 4, since it's purely a UI-driven need:

- [ ] **Step 2: Add `resolve_media_path_for_entry` to `MediaService`**

In `src/klientenverwaltung/services/media_service.py`, add next to `resolve_media_path`:

```python
    def resolve_media_path_for_entry(self, entry: SessionMediaEntry) -> Path:
        return self._media_dir / entry.stored_filename
```

- [ ] **Step 3: ruff**

Run: `uv run ruff check src/klientenverwaltung/ui/media_dialog.py src/klientenverwaltung/services/media_service.py`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/klientenverwaltung/ui/media_dialog.py src/klientenverwaltung/services/media_service.py
git commit -m "feat: add MediaDialog (Medienfenster)"
```

---

### Task 11: "Medien" button + column on `ClientSessionsDialog`

**Files:**
- Modify: `src/klientenverwaltung/ui/session_table_model.py`
- Modify: `src/klientenverwaltung/ui/client_sessions_dialog.py`

**Interfaces:**
- Consumes: `MediaService.count_media_for_sessions` (Task 4), `MediaDialog` (Task 10)
- Produces: `SessionTableModel.set_sessions(sessions, media_counts)` (signature change); `ClientSessionsDialog(treatment_type_service, treatment_session_service, media_service, client_id, client_name, parent=None)` (signature change - new `media_service` parameter)

- [ ] **Step 1: Add the "Medien" column to `SessionTableModel`**

In `src/klientenverwaltung/ui/session_table_model.py`, change:

```python
COLUMN_TITLES = ("Datum", "Behandlungsart", "Dauer (Min.)", "Bericht")
REPORT_COLUMN = 3
```

to:

```python
COLUMN_TITLES = ("Datum", "Behandlungsart", "Dauer (Min.)", "Medien", "Bericht")
MEDIA_COLUMN = 3
REPORT_COLUMN = 4
```

Change `__init__`/`set_sessions`:

```python
    def __init__(self) -> None:
        super().__init__()
        self._sessions: list[TreatmentSession] = []
        self._media_counts: dict[int, int] = {}

    def set_sessions(
        self, sessions: list[TreatmentSession], media_counts: dict[int, int]
    ) -> None:
        self.beginResetModel()
        self._sessions = sessions
        self._media_counts = media_counts
        self.endResetModel()
```

In `data()`, add centered alignment for the new column and adjust the existing `REPORT_COLUMN` alignment check to also cover `MEDIA_COLUMN`:

```python
        if role == Qt.ItemDataRole.TextAlignmentRole and column in (
            MEDIA_COLUMN,
            REPORT_COLUMN,
        ):
            return Qt.AlignmentFlag.AlignCenter

        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if column == 0:
            return session.date.strftime("%d.%m.%Y %H:%M")
        if column == 1:
            return session.treatment_type.name
        if column == 2:
            return str(session.duration_minutes)
        if column == MEDIA_COLUMN:
            count = self._media_counts.get(session.id, 0)
            return str(count) if count else ""
        if column == REPORT_COLUMN:
            return _REPORT_CHECK if (session.report or session.impulses) else ""
        return None
```

- [ ] **Step 2: Wire it up in `ClientSessionsDialog`**

In `src/klientenverwaltung/ui/client_sessions_dialog.py`:

Add the import and constructor parameter:

```python
from klientenverwaltung.services import (
    MediaService,
    ServiceError,
    TreatmentSessionService,
    TreatmentTypeService,
)
from klientenverwaltung.ui.media_dialog import MediaDialog
from klientenverwaltung.ui.session_table_model import (
    COLUMN_TITLES,
    MEDIA_COLUMN,
    REPORT_COLUMN,
    SessionTableModel,
)
```

```python
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
        ...
```

In `_build_ui`, replace the initial `set_sessions` call and the fixed-width setup:

```python
        self._session_table_model = SessionTableModel()
        sessions = self._treatment_session_service.list_sessions_for_client(self._client_id)
        self._session_table_model.set_sessions(sessions, self._media_counts_for(sessions))
        ...
        if not restored:
            self._session_table_view.resizeColumnsToContents()
            self._session_table_view.setColumnWidth(MEDIA_COLUMN, 60)
            self._session_table_view.setColumnWidth(REPORT_COLUMN, 60)
```

Add the helper and update `_reload_sessions`:

```python
    def _media_counts_for(self, sessions: list) -> dict[int, int]:
        return self._media_service.count_media_for_sessions(
            [session.id for session in sessions]
        )

    def _reload_sessions(self) -> None:
        sessions = self._treatment_session_service.list_sessions_for_client(
            self._client_id
        )
        self._session_table_model.set_sessions(sessions, self._media_counts_for(sessions))
        self._update_button_states()
```

Add the "Medien" button, placed left of "Bericht" (same size/style - a plain `QPushButton`, no extra styling needed):

```python
        self._media_button = QPushButton("Medien", self)
        self._report_button = QPushButton("Bericht", self)
        ...
        self._media_button.setEnabled(False)
        self._report_button.setEnabled(False)
        ...
        self._media_button.clicked.connect(self._on_media_clicked)
        self._report_button.clicked.connect(self._on_report_clicked)
        ...
        button_row.addStretch()
        button_row.addWidget(self._media_button)
        button_row.addWidget(self._report_button)
        button_row.addWidget(self._new_session_button)
        button_row.addWidget(self._edit_session_button)
        button_row.addWidget(self._delete_session_button)
```

Update `_update_button_states` to also toggle `_media_button`, and add the click handler:

```python
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
```

- [ ] **Step 3: ruff**

Run: `uv run ruff check src/klientenverwaltung/ui/session_table_model.py src/klientenverwaltung/ui/client_sessions_dialog.py`
Expected: no errors (constructors of `ClientSessionsDialog` at its two call sites are still broken at this point - fixed in Task 12 - so a full `ruff check .`/import-time smoke test is deferred to that task's end).

- [ ] **Step 4: Commit**

```bash
git add src/klientenverwaltung/ui/session_table_model.py src/klientenverwaltung/ui/client_sessions_dialog.py
git commit -m "feat: add Medien button and count column to the session window"
```

---

### Task 12: Thread `MediaService` through the window chain

**Files:**
- Modify: `src/klientenverwaltung/main.py`
- Modify: `src/klientenverwaltung/ui/main_window.py`
- Modify: `src/klientenverwaltung/ui/client_list_widget.py`
- Modify: `src/klientenverwaltung/ui/client_detail_dialog.py`
- Modify: `src/klientenverwaltung/ui/client_overview_dialog.py`

**Interfaces:**
- Consumes: `MediaService` (Task 4)
- Produces: every constructor in this chain gains a `media_service: MediaService` parameter, mirroring how `treatment_session_service` already flows through all five of these files.

- [ ] **Step 1: Construct it once in `main.py`**

In `_run_startup()`, alongside the existing service construction:

```python
    from klientenverwaltung.services import MediaService

    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    client_service = ClientService(session_factory)
    treatment_type_service = TreatmentTypeService(session_factory)
    treatment_session_service = TreatmentSessionService(session_factory)
    media_service = MediaService(session_factory, drive_root)

    window = MainWindow(
        client_service,
        treatment_type_service,
        treatment_session_service,
        media_service,
        engine=engine,
        drive_root=drive_root,
    )
```

(Move the `MediaService` import to the top-level import block alongside the other `from klientenverwaltung.services import (...)` line instead of inline, matching the existing style - the inline form above is only to show where it plugs in.)

- [ ] **Step 2: `MainWindow`**

```python
    def __init__(
        self,
        client_service: ClientService,
        treatment_type_service: TreatmentTypeService,
        treatment_session_service: TreatmentSessionService,
        media_service: MediaService,
        *,
        engine: Engine,
        drive_root: Path,
    ) -> None:
        super().__init__()
        self._treatment_type_service = treatment_type_service
        self._engine = engine
        self._drive_root = drive_root
        self._theme_mode = load_theme_mode()

        self.setWindowTitle("Klientenverwaltung")
        self.resize(1000, 700)
        self.setCentralWidget(
            ClientListWidget(
                client_service,
                treatment_type_service,
                treatment_session_service,
                media_service,
            )
        )
```

(Add `MediaService` to the `from klientenverwaltung.services import (...)` block.)

- [ ] **Step 3: `ClientListWidget`**

```python
    def __init__(
        self,
        client_service: ClientService,
        treatment_type_service: TreatmentTypeService,
        treatment_session_service: TreatmentSessionService,
        media_service: MediaService,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._client_service = client_service
        self._treatment_type_service = treatment_type_service
        self._treatment_session_service = treatment_session_service
        self._media_service = media_service
```

Update both dialog-opening methods:

```python
    def _open_detail_dialog(self, client_id: int | None) -> None:
        dialog = ClientDetailDialog(
            self._client_service,
            self._treatment_type_service,
            self._treatment_session_service,
            self._media_service,
            client_id,
            parent=self,
        )
        dialog.exec()
        self._reload()

    def _open_overview_dialog(self, client_id: int) -> None:
        dialog = ClientOverviewDialog(
            self._client_service,
            self._treatment_type_service,
            self._treatment_session_service,
            self._media_service,
            client_id,
            parent=self,
        )
        dialog.exec()
        self._reload()
```

(Add `MediaService` to its `from klientenverwaltung.services import (...)` block.)

- [ ] **Step 4: `ClientDetailDialog`**

```python
    def __init__(
        self,
        client_service: ClientService,
        treatment_type_service: TreatmentTypeService,
        treatment_session_service: TreatmentSessionService,
        media_service: MediaService,
        client_id: int | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._client_service = client_service
        self._treatment_type_service = treatment_type_service
        self._treatment_session_service = treatment_session_service
        self._media_service = media_service
        self._client_id = client_id
```

In `_on_sessions_clicked`:

```python
        dialog = ClientSessionsDialog(
            self._treatment_type_service,
            self._treatment_session_service,
            self._media_service,
            self._client_id,
            client_name.strip(),
            parent=self,
        )
```

(Add `MediaService` to its `from klientenverwaltung.services import (...)` block.)

- [ ] **Step 5: `ClientOverviewDialog`**

```python
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
```

In `_on_sessions_clicked`:

```python
        dialog = ClientSessionsDialog(
            self._treatment_type_service,
            self._treatment_session_service,
            self._media_service,
            self._client_id,
            client_name,
            parent=self,
        )
```

(Add `MediaService` to its `from klientenverwaltung.services import (...)` block.)

- [ ] **Step 6: Full-app smoke import + ruff + full test suite**

Run: `uv run python -c "import klientenverwaltung.main"`
Expected: no `ImportError`/`TypeError` (catches any missed call site from Tasks 11-12).

Run: `uv run ruff check .`
Expected: no errors.

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/klientenverwaltung/main.py src/klientenverwaltung/ui/main_window.py src/klientenverwaltung/ui/client_list_widget.py src/klientenverwaltung/ui/client_detail_dialog.py src/klientenverwaltung/ui/client_overview_dialog.py
git commit -m "feat: wire MediaService through the client/session window chain"
```

---

### Task 13: Docs

**Files:**
- Modify: `CLAUDE.md`
- Modify: `TODO.md`

- [ ] **Step 1: `CLAUDE.md` datamodel**

Add two new table entries under `## Datenmodell`, after the existing `session` table:

```markdown
### media
| Spalte | Typ | Hinweis |
|---|---|---|
| id | int PK | |
| stored_filename | str, eindeutig | UUID + Originalendung, relativ zum Medienordner |
| original_filename | str | ursprünglicher Dateiname, nur zur Anzeige |
| media_kind | str | "image"/"video"/"audio"/"other", aus der Endung bestimmt |
| size_bytes | int | |
| sha256 | str | für die Duplikat-Erkennung beim Import |
| created_at | datetime | automatisch |

### session_media
| Spalte | Typ | Hinweis |
|---|---|---|
| session_id | FK → session.id | Pflicht, ON DELETE CASCADE, Teil des Primärschlüssels |
| media_id | FK → media.id | Pflicht, ON DELETE RESTRICT, Teil des Primärschlüssels |
| added_at | datetime | automatisch, wann diese Sitzung mit der Datei verknüpft wurde |
```

Add a bullet under `### Regeln`:

```markdown
- Mediendateien liegen im Ordner "medien" auf der Datenplatte, benannt mit einer
  UUID statt dem Originalnamen. Eine Datei kann mehreren Sitzungen zugeordnet sein
  (Duplikate werden über den Dateiinhalt/SHA-256 erkannt, nie erneut kopiert).
  Sitzung/Klient löschen entfernt nur die Verknüpfung (`session_media`), nie die
  Datei oder den `media`-Eintrag (Aufräumen verwaister Dateien ist Auftrag C2).
  Das Original bleibt immer unverändert, wo der Anwender es ausgewählt hat -
  das Programm löscht es nie.
```

Add a bullet under `## Speicherung, Verschlüsselung, Sicherheit`:

```markdown
- Mediendateien werden nur kopiert, nie verschoben oder gelöscht, und liegen
  unverschlüsselt im Ordner "medien" auf der Datenplatte - ihr Schutz hängt
  bis auf Weiteres von der Verschlüsselung der ganzen Datenplatte ab (siehe
  TODO.md, "Vor der Übergabe").
```

- [ ] **Step 2: `TODO.md`**

Under `## Vor der Übergabe`, add:

```markdown
- Verschlüsselung der Mediendateien klären (Windows-Edition prüfen: Pro -> BitLocker
  To Go; Home -> Upgrade/VeraCrypt/eigene Verschlüsselung). Bevor echte Aufnahmen
  gespeichert werden!
- Heiler informieren: Mediendateien werden NICHT gesichert.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md TODO.md
git commit -m "docs: document media/session_media data model and open follow-ups"
```

---

### Task 14: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Full automated check**

Run: `uv run ruff check .`
Run: `uv run pytest -q`
Expected: both clean/all-green.

- [ ] **Step 2: Build the debug .exe**

Follow `docs/build.md`'s debug-build steps (the console-enabled variant) to produce a debug build.

- [ ] **Step 3: Manual test with a large file**

Using **only test data** (per CLAUDE.md): run the debug build against a scratch/test data drive, open a session's "Medien" window, click "Datei anfügen …", and pick a file larger than 1 GB (any large local test file - e.g. a throwaway video). Verify:
- The loading dialog appears (after a brief delay), spinner rotating, percentage counting up as real progress (not stuck at 0 or jumping straight to 100).
- Clicking "Abbrechen" partway through stops the import; reopening the Medien window shows no new row, and the drive's `medien` folder has no leftover `.part` file.
- Re-running the same import to completion succeeds, the file appears in the list with a correct human-readable size (e.g. "1,2 GB"), and "Öffnen" launches the right default Windows program.
- Attaching the exact same file again to a different session shows the "bereits vorhanden ... verwenden?" prompt and does not create a second copy in `medien`.

- [ ] **Step 4: Report back**

Summarize the manual verification result (pass/fail per bullet above) — no commit for this task, it's verification only.
