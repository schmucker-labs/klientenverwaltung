# Auftrag C2: Medienübersicht, vorhandene Medien zuordnen, Umbenennen, Aufräumen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a global "Medienübersicht" window (all media files, usage counts, missing/unknown-file detection, rename, delete), let a session pick up already-imported media without copying, and ask the user once after any action that leaves a file unused whether to delete it for good.

**Architecture:** All new business logic (counting, "would become unused", medien-folder↔DB reconciliation, rename validation, deletion) lives in `MediaService`/`MediaRepository`, exactly like Auftrag C1. Three new small dialogs (`MediaOverviewDialog`, `RenameMediaDialog`, `SelectExistingMediaDialog`) follow the existing management-dialog shape (`TreatmentTypeManagementDialog`, `MediaDialog`). One shared UI helper (`ui/media_cleanup.py`) implements the "ask, then maybe delete, then report failures" sequence once and is called from the three places an action can orphan a media file (remove a link, delete a session, delete a client) — never from archiving.

**Tech Stack:** PySide6, SQLAlchemy 2.x, pytest. No new dependencies. Builds directly on Auftrag C1 (`Media`/`SessionMedia` tables, `MediaService`, `MediaDialog`, `MediaTableModel` all already exist).

**Spec:** The Auftrag C2 request in this conversation (reproduced in full in Global Constraints/task descriptions below — no separate spec file). Also read `CLAUDE.md` and `docs/ui-regeln.md` before starting, per the Auftrag's own instruction.

## Global Constraints

- UI text/labels: German. Code/identifiers/table/column names: English.
- Mediendateien werden NIE automatisch gelöscht, nur nach ausdrücklicher Bestätigung des Anwenders — this holds for every deletion path this plan adds (Medienübersicht's "Löschen" button, and the post-action "n Dateien werden nicht mehr verwendet" prompt).
- The post-action "jetzt löschen?" prompt fires for: Sitzung löschen, Klient endgültig löschen, "Verknüpfung entfernen" im Medienfenster. It must NOT fire for archiving a client.
- "Löschen" in the Medienübersicht is only ever enabled for media used by 0 sessions and for untracked ("unbekannte") files; a used file's delete control is disabled with a tooltip naming the usage count.
- Renaming changes only `Media.original_filename`; the file on disk (`stored_filename`) is never touched. The extension is fixed and not editable.
- Forbidden filename characters: `\ / : * ? " < > |`. Empty name (after stripping) is rejected.
- If a file can't actually be deleted from disk (e.g. open in another program), its DB row is not deleted either — it stays visible in the Medienübersicht as 0×, and the user sees a plain German message, never a crash.
- Every dialog uses `window_settings.restore_geometry`/`save_geometry` (and, for tables, `restore_header_state`/`save_header_state`/`finalize_column_widths`) under its own QSettings key, and fits 1366×768.
- No hardcoded colors in UI code — only `ColorPalette` values via `get_palette(load_theme_mode())`, matching existing dialogs.
- `services/` never imports anything from `PySide6`.
- ruff must pass with no errors; all tests green.
- Commit messages: no `Co-Authored-By: Claude` trailer (public portfolio repo).
- Only test data is ever used while implementing/verifying this (see CLAUDE.md).

## Review Focus

- **A media row whose usage count is exactly 1, then that one session is deleted**: `find_now_unused` must report it (0 links left); a media row still linked to 2+ sessions after one is removed must NOT be reported.
- **Deleting a client with several sessions that share one media file** (e.g. the same photo attached to two of that client's own sessions): the file must be offered exactly once, not twice, and only once BOTH sessions' links are actually gone.
- **A `.part` file (an import truly in progress, or one C1's startup cleanup hasn't reached yet) must never appear as an "unbekannte Datei"** in the Medienübersicht — it's a transient temp file, not an untracked media file.
- **Renaming with only whitespace, or with a forbidden character buried in the middle of an otherwise valid name** (not just leading/trailing) must be rejected with a clear message, not silently truncated or accepted.
- **The Medienübersicht's multi-select "Löschen" with a mix of deletable and non-deletable (still-used) rows selected together**: the button must be disabled for the whole selection, not delete the deletable ones and silently skip the rest.

---

### Task 1: `MediaRepository` additions

**Files:**
- Modify: `src/klientenverwaltung/repositories/media_repository.py`

**Interfaces:**
- Consumes: `Media`, `SessionMedia` (existing), `Client`, `TreatmentSession` (new imports into this file)
- Produces on `MediaRepository`:
  - `list_all() -> list[Media]`
  - `usage_counts_for_media(media_ids: Sequence[int]) -> dict[int, int]`
  - `delete(media: Media) -> None`
  - `list_usages_for_media(media_id: int) -> list[tuple[str, str, datetime]]` (first_name, last_name, session date)
  - `list_media_ids_for_client(client_id: int) -> list[int]`
  - `list_unlinked_for_session(session_id: int, search: str | None = None) -> list[Media]`

No dedicated test file — every method here is exercised through `MediaService`'s tests in Tasks 2-5, the same way Auftrag C1's `MediaRepository` additions were.

- [ ] **Step 1: Add the imports and methods**

At the top of `src/klientenverwaltung/repositories/media_repository.py`, change:

```python
from klientenverwaltung.models import Media, SessionMedia
```

to:

```python
from klientenverwaltung.models import Client, Media, SessionMedia, TreatmentSession
```

Add these methods to the `MediaRepository` class (anywhere after `__init__`; suggested right after `add`):

```python
    def list_all(self) -> list[Media]:
        return list(self._session.scalars(select(Media)))

    def delete(self, media: Media) -> None:
        self._session.delete(media)
```

Add after `count_for_sessions`:

```python
    def usage_counts_for_media(self, media_ids: Sequence[int]) -> dict[int, int]:
        if not media_ids:
            return {}
        stmt = (
            select(SessionMedia.media_id, func.count(SessionMedia.session_id))
            .where(SessionMedia.media_id.in_(media_ids))
            .group_by(SessionMedia.media_id)
        )
        return dict(self._session.execute(stmt).all())

    def list_usages_for_media(self, media_id: int) -> list[tuple[str, str, datetime]]:
        stmt = (
            select(Client.first_name, Client.last_name, TreatmentSession.date)
            .select_from(SessionMedia)
            .join(TreatmentSession, TreatmentSession.id == SessionMedia.session_id)
            .join(Client, Client.id == TreatmentSession.client_id)
            .where(SessionMedia.media_id == media_id)
            .order_by(TreatmentSession.date.desc())
        )
        return list(self._session.execute(stmt).all())

    def list_media_ids_for_client(self, client_id: int) -> list[int]:
        stmt = (
            select(SessionMedia.media_id)
            .join(TreatmentSession, TreatmentSession.id == SessionMedia.session_id)
            .where(TreatmentSession.client_id == client_id)
            .distinct()
        )
        return list(self._session.scalars(stmt))

    def list_unlinked_for_session(
        self, session_id: int, search: str | None = None
    ) -> list[Media]:
        linked_subquery = select(SessionMedia.media_id).where(
            SessionMedia.session_id == session_id
        )
        stmt = select(Media).where(Media.id.not_in(linked_subquery))
        if search:
            stmt = stmt.where(Media.original_filename.ilike(f"%{search}%"))
        stmt = stmt.order_by(Media.original_filename)
        return list(self._session.scalars(stmt))
```

- [ ] **Step 2: ruff**

Run: `uv run ruff check src/klientenverwaltung/repositories/media_repository.py`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/klientenverwaltung/repositories/media_repository.py
git commit -m "feat: add Medienübersicht/rename/aufräumen queries to MediaRepository"
```

---

### Task 2: `MediaService` — Medienübersicht read side

**Files:**
- Modify: `src/klientenverwaltung/services/media_service.py`
- Modify: `src/klientenverwaltung/services/__init__.py`
- Test: `tests/test_media_service.py`

**Interfaces:**
- Consumes: `MediaRepository.list_all`, `.usage_counts_for_media`, `.list_usages_for_media` (Task 1)
- Produces:
  - `MediaOverviewEntry` dataclass: `media_id: int | None`, `stored_filename: str`, `original_filename: str | None`, `media_kind: MediaKind`, `size_bytes: int`, `created_at: datetime | None`, `usage_count: int`, `file_missing: bool`
  - `MediaUsageEntry` dataclass: `client_name: str`, `session_date: datetime`
  - `MediaService.list_all_media() -> list[MediaOverviewEntry]`
  - `MediaService.list_usages(media_id: int) -> list[MediaUsageEntry]`
  - `MediaService.count_sessions_for_media(media_id: int) -> int`
  - `MediaService.resolve_media_path_for_stored_filename(stored_filename: str) -> Path`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_media_service.py`:

```python
def test_list_all_media_reports_usage_count_and_normal_entries(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 20)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.link_existing_media(other_session.id, [outcome.media.id])

    entries = media_service.list_all_media()

    assert len(entries) == 1
    entry = entries[0]
    assert entry.media_id == outcome.media.id
    assert entry.original_filename == "foto.jpg"
    assert entry.usage_count == 2
    assert entry.file_missing is False
    assert entry.size_bytes == 20


def test_list_all_media_detects_a_missing_file(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.resolve_media_path(outcome.media).unlink()  # simulate manual deletion

    entries = media_service.list_all_media()

    assert len(entries) == 1
    assert entries[0].media_id == outcome.media.id
    assert entries[0].file_missing is True
    assert entries[0].usage_count == 1  # the DB link still exists


def test_list_all_media_detects_an_unknown_file_but_ignores_part_files(
    media_service: MediaService, tmp_path: Path
) -> None:
    media_dir = media_service.resolve_media_path_for_stored_filename("x").parent
    media_dir.mkdir(parents=True)
    unknown = media_dir / "12345678deadbeef.png"
    unknown.write_bytes(b"?" * 7)
    in_progress = media_dir / "abcdef0123456789.mp4.part"
    in_progress.write_bytes(b"partial")

    entries = media_service.list_all_media()

    assert len(entries) == 1
    entry = entries[0]
    assert entry.media_id is None
    assert entry.original_filename is None
    assert entry.stored_filename == "12345678deadbeef.png"
    assert entry.media_kind == "image"
    assert entry.size_bytes == 7
    assert entry.usage_count == 0


def test_list_usages_returns_client_name_and_session_date(
    media_service: MediaService,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)

    usages = media_service.list_usages(outcome.media.id)

    assert usages == [
        MediaUsageEntry(
            client_name=f"{client.first_name} {client.last_name}",
            session_date=treatment_session.date,
        )
    ]


def test_count_sessions_for_media_reflects_number_of_links(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    assert media_service.count_sessions_for_media(outcome.media.id) == 1

    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    media_service.link_existing_media(other_session.id, [outcome.media.id])
    assert media_service.count_sessions_for_media(outcome.media.id) == 2
```

Add the import at the top of `tests/test_media_service.py`:

```python
from klientenverwaltung.services.media_service import ImportOutcome, MediaUsageEntry
```

(replacing the existing `from klientenverwaltung.services.media_service import ImportOutcome` line with this one — `MediaUsageEntry` doesn't exist yet, which is expected to fail collection until Step 3.)

Note: these tests use `media_service.link_existing_media(...)`, which Task 5 adds — since Task 5 comes after this one in the plan, temporarily stub it in this task's implementation step as a thin pass-through so these tests can run (Task 5 replaces the stub with the real, tested implementation):

```python
    def link_existing_media(self, session_id: int, media_ids: Sequence[int]) -> None:
        with self._session_factory() as session:
            repo = MediaRepository(session)
            for media_id in media_ids:
                if not repo.is_linked(session_id, media_id):
                    repo.link(session_id, media_id)
            with transaction(session, "Dateien konnten nicht zugeordnet werden."):
                pass
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_media_service.py -k "list_all_media or list_usages or count_sessions_for_media" -v`
Expected: FAIL (collection error — `MediaUsageEntry` does not exist yet, and `list_all_media`/`list_usages`/`count_sessions_for_media`/`link_existing_media` are not defined).

- [ ] **Step 3: Implement**

In `src/klientenverwaltung/services/media_service.py`, add after the `ImportOutcome` dataclass:

```python
@dataclass(frozen=True)
class MediaOverviewEntry:
    """One row of the Medienübersicht (Auftrag C2) - covers three cases:
    a normal media row; a DB row whose file is missing from the medien
    folder (file_missing=True); or a file found in the medien folder with
    no matching DB row at all (media_id=None, original_filename=None,
    "Unbekannte Datei" in the UI).
    """

    media_id: int | None
    stored_filename: str
    original_filename: str | None
    media_kind: MediaKind
    size_bytes: int
    created_at: datetime | None
    usage_count: int
    file_missing: bool


@dataclass(frozen=True)
class MediaUsageEntry:
    """One session a media file is attached to (Medienübersicht's
    "Verwendet in:" panel)."""

    client_name: str
    session_date: datetime
```

Add these methods to `MediaService` (near `resolve_media_path_for_entry`):

```python
    def resolve_media_path_for_stored_filename(self, stored_filename: str) -> Path:
        return self._media_dir / stored_filename

    def list_all_media(self) -> list[MediaOverviewEntry]:
        with self._session_factory() as session:
            repo = MediaRepository(session)
            all_media = repo.list_all()
            usage = repo.usage_counts_for_media([media.id for media in all_media])
            entries = [
                MediaOverviewEntry(
                    media_id=media.id,
                    stored_filename=media.stored_filename,
                    original_filename=media.original_filename,
                    media_kind=media.media_kind,  # type: ignore[arg-type]
                    size_bytes=media.size_bytes,
                    created_at=media.created_at,
                    usage_count=usage.get(media.id, 0),
                    file_missing=not (self._media_dir / media.stored_filename).exists(),
                )
                for media in all_media
            ]
            known_stored_filenames = {media.stored_filename for media in all_media}

        if self._media_dir.exists():
            for path in sorted(self._media_dir.iterdir()):
                if (
                    not path.is_file()
                    or path.suffix == ".part"
                    or path.name in known_stored_filenames
                ):
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                entries.append(
                    MediaOverviewEntry(
                        media_id=None,
                        stored_filename=path.name,
                        original_filename=None,
                        media_kind=classify_media_kind(path.name),
                        size_bytes=stat.st_size,
                        created_at=datetime.fromtimestamp(stat.st_mtime),
                        usage_count=0,
                        file_missing=False,
                    )
                )
        return entries

    def list_usages(self, media_id: int) -> list[MediaUsageEntry]:
        with self._session_factory() as session:
            rows = MediaRepository(session).list_usages_for_media(media_id)
        return [
            MediaUsageEntry(client_name=f"{first} {last}", session_date=date)
            for first, last, date in rows
        ]

    def count_sessions_for_media(self, media_id: int) -> int:
        with self._session_factory() as session:
            usage = MediaRepository(session).usage_counts_for_media([media_id])
        return usage.get(media_id, 0)

    def link_existing_media(self, session_id: int, media_ids: Sequence[int]) -> None:
        with self._session_factory() as session:
            repo = MediaRepository(session)
            for media_id in media_ids:
                if not repo.is_linked(session_id, media_id):
                    repo.link(session_id, media_id)
            with transaction(session, "Dateien konnten nicht zugeordnet werden."):
                pass
```

(`link_existing_media` here is the Task-5-stub described above — Task 5 leaves this exact implementation in place and only adds `list_unlinked_media_for_session`/`MediaPickerEntry` alongside it, so nothing here gets thrown away.)

- [ ] **Step 4: Export from services**

In `src/klientenverwaltung/services/__init__.py`, add `MediaOverviewEntry` and `MediaUsageEntry` to both the `from klientenverwaltung.services.media_service import (...)` block and `__all__` (alphabetically sorted, matching existing style).

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_media_service.py -v`
Expected: PASS (all tests, old and new).

- [ ] **Step 6: ruff + full suite**

Run: `uv run ruff check src/klientenverwaltung/services/media_service.py src/klientenverwaltung/services/__init__.py tests/test_media_service.py`
Run: `uv run pytest -q`
Expected: all green, no lint errors.

- [ ] **Step 7: Commit**

```bash
git add src/klientenverwaltung/services/media_service.py src/klientenverwaltung/services/__init__.py tests/test_media_service.py
git commit -m "feat: add MediaService read side for the Medienübersicht"
```

---

### Task 3: `MediaService.rename_media`

**Files:**
- Modify: `src/klientenverwaltung/services/media_service.py`
- Test: `tests/test_media_service.py`

**Interfaces:**
- Consumes: `ValidationError` (existing, needs importing into media_service.py)
- Produces: `MediaService.rename_media(media_id: int, new_original_filename: str) -> Media`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_media_service.py`:

```python
def test_rename_media_updates_original_filename_only(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    stored_path = media_service.resolve_media_path(outcome.media)

    media = media_service.rename_media(outcome.media.id, "Urlaubsfoto.jpg")

    assert media.original_filename == "Urlaubsfoto.jpg"
    assert media.stored_filename == outcome.media.stored_filename
    assert stored_path.exists()  # the file on disk never moved


def test_rename_media_rejects_an_empty_name(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)

    with pytest.raises(ValidationError):
        media_service.rename_media(outcome.media.id, "   .jpg")


def test_rename_media_rejects_a_forbidden_character_anywhere_in_the_name(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)

    with pytest.raises(ValidationError):
        media_service.rename_media(outcome.media.id, "vor:nach.jpg")
```

Add `ValidationError` to the existing import in `tests/test_media_service.py`:

```python
from klientenverwaltung.services import MediaService, NotFoundError, ValidationError
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_media_service.py -k rename_media -v`
Expected: FAIL with `AttributeError: 'MediaService' object has no attribute 'rename_media'`.

- [ ] **Step 3: Implement**

In `src/klientenverwaltung/services/media_service.py`, change the errors import:

```python
from klientenverwaltung.services.errors import NotFoundError, ServiceError, ValidationError
```

Add near the top-level constants:

```python
_FORBIDDEN_FILENAME_CHARS = frozenset('\\/:*?"<>|')
```

Add this method to `MediaService`:

```python
    def rename_media(self, media_id: int, new_original_filename: str) -> Media:
        new_name = new_original_filename.strip()
        if not new_name:
            raise ValidationError("Der Name darf nicht leer sein.")
        if any(char in _FORBIDDEN_FILENAME_CHARS for char in new_name):
            raise ValidationError(
                'Der Name darf keines dieser Zeichen enthalten: \\ / : * ? " < > |'
            )
        with self._session_factory() as session:
            media = MediaRepository(session).get_by_id(media_id)
            if media is None:
                raise NotFoundError(f"Datei mit ID {media_id} wurde nicht gefunden.")
            media.original_filename = new_name
            with transaction(session, "Datei konnte nicht umbenannt werden."):
                pass
        return media
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_media_service.py -v`
Expected: PASS.

- [ ] **Step 5: ruff + full suite**

Run: `uv run ruff check src/klientenverwaltung/services/media_service.py tests/test_media_service.py`
Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add src/klientenverwaltung/services/media_service.py tests/test_media_service.py
git commit -m "feat: add MediaService.rename_media with filename validation"
```

---

### Task 4: `MediaService` — aufräumen (find-unused, delete)

**Files:**
- Modify: `src/klientenverwaltung/services/media_service.py`
- Modify: `src/klientenverwaltung/services/__init__.py`
- Test: `tests/test_media_service.py`

**Interfaces:**
- Consumes: `MediaRepository.usage_counts_for_media`, `.delete`, `.list_media_ids_for_client` (Task 1)
- Produces:
  - `MediaService.find_now_unused(media_ids: Sequence[int]) -> list[Media]`
  - `MediaService.delete_unused_media(media_ids: Sequence[int]) -> list[Media]` (returns the ones that could NOT be deleted)
  - `MediaService.delete_unknown_file(stored_filename: str) -> bool`
  - `MediaService.list_media_ids_for_client(client_id: int) -> list[int]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_media_service.py`:

```python
def test_find_now_unused_reports_media_with_no_remaining_links(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.remove_link(treatment_session.id, outcome.media.id)

    unused = media_service.find_now_unused([outcome.media.id])

    assert [m.id for m in unused] == [outcome.media.id]


def test_find_now_unused_excludes_media_still_linked_elsewhere(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.link_existing_media(other_session.id, [outcome.media.id])

    media_service.remove_link(treatment_session.id, outcome.media.id)
    unused = media_service.find_now_unused([outcome.media.id])

    assert unused == []  # still linked to other_session


def test_deleting_a_session_leaves_its_only_medium_findable_as_unused(
    media_service: MediaService, treatment_session_service, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)

    treatment_session_service.delete_session(treatment_session.id)

    assert [m.id for m in media_service.find_now_unused([outcome.media.id])] == [
        outcome.media.id
    ]


def test_delete_unused_media_removes_file_and_db_row(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.remove_link(treatment_session.id, outcome.media.id)
    stored_path = media_service.resolve_media_path(outcome.media)

    failures = media_service.delete_unused_media([outcome.media.id])

    assert failures == []
    assert not stored_path.exists()
    assert media_service.list_all_media() == []


def test_delete_unused_media_refuses_a_still_used_medium(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    stored_path = media_service.resolve_media_path(outcome.media)

    failures = media_service.delete_unused_media([outcome.media.id])

    assert failures == []  # not reported as a failure - it's simply not deleted
    assert stored_path.exists()
    assert len(media_service.list_all_media()) == 1


def test_delete_unused_media_reports_a_file_it_cannot_remove(
    media_service: MediaService, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.remove_link(treatment_session.id, outcome.media.id)
    stored_path = media_service.resolve_media_path(outcome.media)

    with stored_path.open("r+b"):  # stands in for "open in another program"
        failures = media_service.delete_unused_media([outcome.media.id])

    assert [m.id for m in failures] == [outcome.media.id]
    assert stored_path.exists()
    assert len(media_service.list_all_media()) == 1  # DB row kept, still 0x


def test_delete_unknown_file_removes_an_untracked_file(
    media_service: MediaService, tmp_path: Path
) -> None:
    media_dir = media_service.resolve_media_path_for_stored_filename("x").parent
    media_dir.mkdir(parents=True)
    unknown = media_dir / "12345678deadbeef.png"
    unknown.write_bytes(b"?")

    assert media_service.delete_unknown_file("12345678deadbeef.png") is True
    assert not unknown.exists()


def test_list_media_ids_for_client_deduplicates_a_file_shared_across_own_sessions(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    """The same file attached to two of one client's own sessions must be
    offered for deletion exactly once after that client is deleted, not
    once per session it was attached to.
    """
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    source = _make_source_file(tmp_path, "shared.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_service.link_existing_media(other_session.id, [outcome.media.id])

    ids = media_service.list_media_ids_for_client(client.id)

    assert ids == [outcome.media.id]  # not duplicated


def test_list_media_ids_for_client_covers_all_of_that_clients_sessions(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    source_a = _make_source_file(tmp_path, "a.jpg", b"a" * 5)
    source_b = _make_source_file(tmp_path, "b.jpg", b"b" * 5)
    outcome_a = media_service.import_file(treatment_session.id, source_a)
    outcome_b = media_service.import_file(other_session.id, source_b)

    ids = media_service.list_media_ids_for_client(client.id)

    assert set(ids) == {outcome_a.media.id, outcome_b.media.id}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_media_service.py -k "find_now_unused or delete_unused_media or delete_unknown_file or list_media_ids_for_client or deleting_a_session_leaves" -v`
Expected: FAIL with `AttributeError` for each missing method.

- [ ] **Step 3: Implement**

Add these methods to `MediaService`:

```python
    def find_now_unused(self, media_ids: Sequence[int]) -> list[Media]:
        if not media_ids:
            return []
        with self._session_factory() as session:
            repo = MediaRepository(session)
            usage = repo.usage_counts_for_media(media_ids)
            unused: list[Media] = []
            for media_id in media_ids:
                if usage.get(media_id, 0) > 0:
                    continue
                media = repo.get_by_id(media_id)
                if media is not None:
                    unused.append(media)
        return unused

    def delete_unused_media(self, media_ids: Sequence[int]) -> list[Media]:
        if not media_ids:
            return []
        failures: list[Media] = []
        with self._session_factory() as session:
            repo = MediaRepository(session)
            usage = repo.usage_counts_for_media(media_ids)
            for media_id in media_ids:
                if usage.get(media_id, 0) > 0:
                    continue
                media = repo.get_by_id(media_id)
                if media is None:
                    continue
                path = self._media_dir / media.stored_filename
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    failures.append(media)
                    continue
                repo.delete(media)
            with transaction(session, "Mediendateien konnten nicht gelöscht werden."):
                pass
        return failures

    def delete_unknown_file(self, stored_filename: str) -> bool:
        path = self._media_dir / stored_filename
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return False
        return True

    def list_media_ids_for_client(self, client_id: int) -> list[int]:
        with self._session_factory() as session:
            return MediaRepository(session).list_media_ids_for_client(client_id)
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_media_service.py -v`
Expected: PASS.

- [ ] **Step 5: Export from services**

Nothing new to export here — `find_now_unused`/`delete_unused_media`/`delete_unknown_file`/`list_media_ids_for_client` are plain methods on the already-exported `MediaService`.

- [ ] **Step 6: ruff + full suite**

Run: `uv run ruff check src/klientenverwaltung/services/media_service.py tests/test_media_service.py`
Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/klientenverwaltung/services/media_service.py tests/test_media_service.py
git commit -m "feat: add MediaService cleanup logic (find-unused, delete)"
```

---

### Task 5: `MediaService` — "Aus vorhandenen Medien"

**Files:**
- Modify: `src/klientenverwaltung/services/media_service.py`
- Modify: `src/klientenverwaltung/services/__init__.py`
- Test: `tests/test_media_service.py`

**Interfaces:**
- Consumes: `MediaRepository.list_unlinked_for_session` (Task 1)
- Produces:
  - `MediaPickerEntry` dataclass: `media_id: int`, `original_filename: str`, `media_kind: MediaKind`, `size_bytes: int`
  - `MediaService.list_unlinked_media_for_session(session_id: int, search: str | None = None) -> list[MediaPickerEntry]`
  - (`link_existing_media` already exists since Task 2 — nothing to add there beyond what Task 2 already implemented.)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_media_service.py`:

```python
def test_list_unlinked_media_for_session_excludes_already_linked_media(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)

    unlinked_for_original = media_service.list_unlinked_media_for_session(
        treatment_session.id
    )
    unlinked_for_other = media_service.list_unlinked_media_for_session(other_session.id)

    assert unlinked_for_original == []
    assert [e.media_id for e in unlinked_for_other] == [outcome.media.id]


def test_list_unlinked_media_for_session_filters_by_search(
    media_service: MediaService, treatment_session_service, treatment_type: TreatmentType,
    client: Client, treatment_session: TreatmentSession, tmp_path: Path,
) -> None:
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    media_service.import_file(treatment_session.id, _make_source_file(tmp_path, "urlaub.jpg", b"a" * 5))
    media_service.import_file(treatment_session.id, _make_source_file(tmp_path, "arbeit.jpg", b"b" * 5))

    results = media_service.list_unlinked_media_for_session(other_session.id, search="urla")

    assert [e.original_filename for e in results] == ["urlaub.jpg"]


def test_link_existing_media_attaches_without_copying(
    media_service: MediaService,
    treatment_session_service,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    other_session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=30,
    )
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 5)
    outcome = media_service.import_file(treatment_session.id, source)
    media_dir = media_service.resolve_media_path(outcome.media).parent

    media_service.link_existing_media(other_session.id, [outcome.media.id])

    assert len(list(media_dir.glob("*.jpg"))) == 1  # no second copy
    entries = media_service.list_media_for_session(other_session.id)
    assert [e.media_id for e in entries] == [outcome.media.id]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_media_service.py -k "list_unlinked_media_for_session or link_existing_media_attaches" -v`
Expected: FAIL with `AttributeError: 'MediaService' object has no attribute 'list_unlinked_media_for_session'` (`link_existing_media` itself already exists from Task 2 and should already pass).

- [ ] **Step 3: Implement**

Add near `SessionMediaEntry`:

```python
@dataclass(frozen=True)
class MediaPickerEntry:
    """One row of the "Aus vorhandenen Medien" picker (Auftrag C2) - media
    not yet linked to the session the picker was opened for."""

    media_id: int
    original_filename: str
    media_kind: MediaKind
    size_bytes: int
```

Add to `MediaService`:

```python
    def list_unlinked_media_for_session(
        self, session_id: int, search: str | None = None
    ) -> list[MediaPickerEntry]:
        with self._session_factory() as session:
            rows = MediaRepository(session).list_unlinked_for_session(session_id, search)
        return [
            MediaPickerEntry(
                media_id=media.id,
                original_filename=media.original_filename,
                media_kind=media.media_kind,  # type: ignore[arg-type]
                size_bytes=media.size_bytes,
            )
            for media in rows
        ]
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_media_service.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Export from services**

Add `MediaPickerEntry` to `src/klientenverwaltung/services/__init__.py`'s import block and `__all__`.

- [ ] **Step 6: ruff + full suite**

Run: `uv run ruff check src/klientenverwaltung/services/media_service.py src/klientenverwaltung/services/__init__.py tests/test_media_service.py`
Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add src/klientenverwaltung/services/media_service.py src/klientenverwaltung/services/__init__.py tests/test_media_service.py
git commit -m "feat: add MediaService support for linking existing media"
```

---

### Task 6: Dialog helpers — `ask_delete_now_unused_media` + `offer_to_delete_now_unused_media`

**Files:**
- Modify: `src/klientenverwaltung/ui/dialogs.py`
- Create: `src/klientenverwaltung/ui/media_cleanup.py`

**Interfaces:**
- Consumes: `MediaService.find_now_unused`, `.delete_unused_media` (Task 4)
- Produces:
  - `ask_delete_now_unused_media(names: list[str], *, parent: QWidget | None = None) -> bool`
  - `offer_to_delete_now_unused_media(media_service: MediaService, candidate_media_ids: Sequence[int], parent: QWidget | None) -> None`

- [ ] **Step 1: Add the message-box helper**

Append to `src/klientenverwaltung/ui/dialogs.py`:

```python
def ask_delete_now_unused_media(
    names: list[str], *, parent: QWidget | None = None
) -> bool:
    """Shown after an action (removing a link, deleting a session/client)
    that may have left one or more media files used by no session at all
    - "Löschen" removes the file(s) and their database rows right now,
    "Behalten" (the safer default) leaves them in place; either way they
    remain visible in the Medienübersicht (Auftrag C2), at 0x if kept.
    """
    count_phrase = (
        "Eine Mediendatei wird" if len(names) == 1 else f"{len(names)} Mediendateien werden"
    )
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Nicht mehr verwendete Mediendateien")
    box.setText(
        f"{count_phrase} nicht mehr verwendet: {', '.join(names)}. "
        "Jetzt endgültig löschen?"
    )
    delete_button = box.addButton("Löschen", QMessageBox.ButtonRole.DestructiveRole)
    keep_button = box.addButton("Behalten", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(keep_button)
    box.exec()
    return box.clickedButton() is delete_button
```

- [ ] **Step 2: Add the shared orchestration helper**

Create `src/klientenverwaltung/ui/media_cleanup.py`:

```python
from collections.abc import Sequence

from PySide6.QtWidgets import QWidget

from klientenverwaltung.services import MediaService
from klientenverwaltung.ui.dialogs import ask_delete_now_unused_media, show_error


def offer_to_delete_now_unused_media(
    media_service: MediaService,
    candidate_media_ids: Sequence[int],
    parent: QWidget | None,
) -> None:
    """Call right after an action that may have removed the last link to
    some media - removing one link in the Medienfenster, deleting a
    session, deleting a client. Never call this for archiving, which
    never touches media links at all.

    Checks which of candidate_media_ids are now used by no session, and
    if any are, asks once (see ask_delete_now_unused_media) whether to
    delete them for good. A file that can't actually be removed (open
    elsewhere) is reported in a plain message; its database row is kept,
    so it stays visible in the Medienübersicht as 0x.
    """
    unused = media_service.find_now_unused(candidate_media_ids)
    if not unused:
        return
    names = [media.original_filename for media in unused]
    if not ask_delete_now_unused_media(names, parent=parent):
        return
    failures = media_service.delete_unused_media([media.id for media in unused])
    if failures:
        failed_names = [media.original_filename for media in failures]
        show_error(
            "Folgende Dateien konnten nicht gelöscht werden, vermutlich weil sie "
            "gerade geöffnet sind: " + ", ".join(failed_names),
            parent=parent,
        )
```

- [ ] **Step 3: ruff**

Run: `uv run ruff check src/klientenverwaltung/ui/dialogs.py src/klientenverwaltung/ui/media_cleanup.py`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/klientenverwaltung/ui/dialogs.py src/klientenverwaltung/ui/media_cleanup.py
git commit -m "feat: add the post-action now-unused-media prompt"
```

---

### Task 7: `RenameMediaDialog`

**Files:**
- Create: `src/klientenverwaltung/ui/rename_media_dialog.py`

**Interfaces:**
- Consumes: `MediaService.rename_media` (Task 3)
- Produces: `RenameMediaDialog(media_service, media_id, current_name, usage_count, parent=None)`

- [ ] **Step 1: Write the dialog**

```python
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.services import MediaService, ServiceError
from klientenverwaltung.ui.dialogs import show_error
from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry

_GEOMETRY_SETTINGS_KEY = "rename_media/geometry"


class RenameMediaDialog(QDialog):
    """Umbenennen (Auftrag C2) - changes only Media.original_filename; the
    file on disk (stored_filename) never changes. The extension is fixed
    and shown but not editable.
    """

    def __init__(
        self,
        media_service: MediaService,
        media_id: int,
        current_name: str,
        usage_count: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._media_service = media_service
        self._media_id = media_id
        self._extension = Path(current_name).suffix
        stem = Path(current_name).stem

        self.setWindowTitle("Datei umbenennen")
        self.setModal(True)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        self._name_edit = QLineEdit(stem, self)
        self._name_edit.selectAll()

        form = QFormLayout()
        form.addRow("Name:", self._name_edit)
        form.addRow("Endung:", QLabel(self._extension, self))

        layout = QVBoxLayout(self)
        layout.addLayout(form)

        if usage_count > 1:
            hint = QLabel(
                f"Der neue Name gilt für alle {usage_count} Sitzungen, denen diese "
                "Datei zugeordnet ist.",
                self,
            )
            hint.setWordWrap(True)
            layout.addWidget(hint)

        button_box = QDialogButtonBox(self)
        save_button = button_box.addButton(
            "Speichern", QDialogButtonBox.ButtonRole.AcceptRole
        )
        button_box.addButton("Abbrechen", QDialogButtonBox.ButtonRole.RejectRole)
        save_button.setDefault(True)
        button_box.accepted.connect(self._on_save_clicked)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _on_save_clicked(self) -> None:
        new_name = self._name_edit.text().strip() + self._extension
        try:
            self._media_service.rename_media(self._media_id, new_name)
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return
        self.accept()

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)
```

- [ ] **Step 2: ruff**

Run: `uv run ruff check src/klientenverwaltung/ui/rename_media_dialog.py`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add src/klientenverwaltung/ui/rename_media_dialog.py
git commit -m "feat: add RenameMediaDialog"
```

---

### Task 8: `MediaOverviewTableModel`

**Files:**
- Modify: `src/klientenverwaltung/ui/media_table_model.py` (promote `_KIND_LABELS` to public `KIND_LABELS`)
- Create: `src/klientenverwaltung/ui/media_overview_table_model.py`

**Interfaces:**
- Consumes: `MediaOverviewEntry` (Task 2), `KIND_LABELS`/`format_size_bytes` (this task promotes/reuses)
- Produces: `COLUMN_TITLES`, `MediaOverviewTableModel(QAbstractTableModel)` with `set_entries(list[MediaOverviewEntry]) -> None`, `entry_at(row: int) -> MediaOverviewEntry`

- [ ] **Step 1: Promote `_KIND_LABELS` to public**

In `src/klientenverwaltung/ui/media_table_model.py`, rename `_KIND_LABELS` to `KIND_LABELS` (both its definition and its one use in `data()`):

```python
KIND_LABELS: dict[MediaKind, str] = {
    "image": "Bild",
    "video": "Video",
    "audio": "Audio",
    "other": "Sonstige",
}
```

```python
        if column == 1:
            return KIND_LABELS[entry.media_kind]
```

- [ ] **Step 2: Write the overview table model**

```python
from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from klientenverwaltung.services.media_service import MediaOverviewEntry
from klientenverwaltung.ui.media_table_model import KIND_LABELS, format_size_bytes

COLUMN_TITLES = ("Name", "Art", "Größe", "Hinzugefügt am", "Verwendet")
USED_COLUMN = 4


def _display_name(entry: MediaOverviewEntry) -> str:
    if entry.media_id is None:
        return "Unbekannte Datei"
    if entry.file_missing:
        return f"{entry.original_filename} (Datei fehlt)"
    return entry.original_filename or ""


def _name_sort_key(entry: MediaOverviewEntry) -> str:
    return _display_name(entry).casefold()


_SORT_KEYS: dict[int, Callable[[MediaOverviewEntry], object]] = {
    0: _name_sort_key,
    1: lambda e: e.media_kind,
    2: lambda e: e.size_bytes,
    3: lambda e: e.created_at or datetime.min,
    USED_COLUMN: lambda e: (e.usage_count, _name_sort_key(e)),
}


class MediaOverviewTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._entries: list[MediaOverviewEntry] = []

    def set_entries(self, entries: list[MediaOverviewEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def entry_at(self, row: int) -> MediaOverviewEntry:
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
        column = index.column()
        if role == Qt.ItemDataRole.TextAlignmentRole and column == USED_COLUMN:
            return Qt.AlignmentFlag.AlignCenter
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if column == 0:
            return _display_name(entry)
        if column == 1:
            return KIND_LABELS[entry.media_kind]
        if column == 2:
            return format_size_bytes(entry.size_bytes)
        if column == 3:
            return entry.created_at.strftime("%d.%m.%Y %H:%M") if entry.created_at else ""
        if column == USED_COLUMN:
            return f"{entry.usage_count}×"
        return None

    def sort(
        self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder
    ) -> None:
        key = _SORT_KEYS.get(column)
        if key is None:
            return
        self.layoutAboutToBeChanged.emit()
        self._entries.sort(key=key, reverse=order == Qt.SortOrder.DescendingOrder)
        self.layoutChanged.emit()
```

- [ ] **Step 3: ruff + full suite**

Run: `uv run ruff check src/klientenverwaltung/ui/media_table_model.py src/klientenverwaltung/ui/media_overview_table_model.py`
Run: `uv run pytest -q`
Expected: all green (the rename in Step 1 must not break anything - nothing outside `media_table_model.py` referenced the old private name).

- [ ] **Step 4: Commit**

```bash
git add src/klientenverwaltung/ui/media_table_model.py src/klientenverwaltung/ui/media_overview_table_model.py
git commit -m "feat: add MediaOverviewTableModel"
```

---

### Task 9: `MediaOverviewDialog`

**Files:**
- Create: `src/klientenverwaltung/ui/media_overview_dialog.py`

**Interfaces:**
- Consumes: `MediaService` (list_all_media, list_usages, resolve_media_path_for_stored_filename, delete_unused_media, delete_unknown_file), `MediaOverviewTableModel`/`COLUMN_TITLES`/`USED_COLUMN` (Task 8), `RenameMediaDialog` (Task 7), `ask_confirm_delete`/`show_error` (existing)
- Produces: `MediaOverviewDialog(media_service, parent=None)`

- [ ] **Step 1: Write the dialog**

```python
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.services import MediaOverviewEntry, MediaService
from klientenverwaltung.ui.dialogs import ask_confirm_delete, show_error
from klientenverwaltung.ui.media_overview_table_model import (
    COLUMN_TITLES,
    USED_COLUMN,
    MediaOverviewTableModel,
)
from klientenverwaltung.ui.media_table_model import format_size_bytes
from klientenverwaltung.ui.rename_media_dialog import RenameMediaDialog
from klientenverwaltung.ui.window_settings import (
    finalize_column_widths,
    restore_geometry,
    restore_header_state,
    save_geometry,
    save_header_state,
)

_GEOMETRY_SETTINGS_KEY = "media_overview/geometry"
_HEADER_STATE_SETTINGS_KEY = "media_overview/header_state"
_NAME_COLUMN = 0


class MediaOverviewDialog(QDialog):
    """Medienübersicht (Auftrag C2) - every media file on the drive, its
    usage count, and detection of the two mismatch cases between the
    medien folder and the database (a missing file, an untracked file).
    """

    def __init__(self, media_service: MediaService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._media_service = media_service
        self._entries: list[MediaOverviewEntry] = []

        self.setWindowTitle("Medienübersicht")
        self.setModal(True)
        self.resize(800, 560)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        self._table_model = MediaOverviewTableModel()
        self._table_view = QTableView(self)
        self._table_view.setModel(self._table_model)
        self._table_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table_view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table_view.setSortingEnabled(True)
        self._table_view.verticalHeader().setVisible(False)
        self._table_view.doubleClicked.connect(self._on_open_clicked)

        # Populated before resizeColumnsToContents() below, which otherwise
        # only has the (much shorter) column headers to measure against on
        # an empty model.
        self._entries = self._media_service.list_all_media()
        self._table_model.set_entries(self._entries)

        header = self._table_view.horizontalHeader()
        restored = restore_header_state(header, _HEADER_STATE_SETTINGS_KEY, COLUMN_TITLES)
        if not restored:
            self._table_view.resizeColumnsToContents()
            self._table_view.sortByColumn(USED_COLUMN, Qt.SortOrder.AscendingOrder)
        finalize_column_widths(header, self._table_model.columnCount(), _NAME_COLUMN, restored)
        header.sectionResized.connect(self._save_header_state)
        header.sortIndicatorChanged.connect(self._save_header_state)
        self._table_view.selectionModel().selectionChanged.connect(
            self._update_button_states
        )
        self._table_view.selectionModel().selectionChanged.connect(
            self._update_usage_panel
        )

        self._usage_heading = QLabel("Verwendet in:", self)
        usage_font = self._usage_heading.font()
        usage_font.setBold(True)
        self._usage_heading.setFont(usage_font)
        self._usage_list = QListWidget(self)
        self._usage_list.setMaximumHeight(90)
        self._usage_panel = QWidget(self)
        usage_layout = QVBoxLayout(self._usage_panel)
        usage_layout.setContentsMargins(0, 0, 0, 0)
        usage_layout.addWidget(self._usage_heading)
        usage_layout.addWidget(self._usage_list)
        self._usage_panel.setVisible(False)

        self._footer_label = QLabel(self)

        self._open_button = QPushButton("Öffnen", self)
        self._rename_button = QPushButton("Umbenennen", self)
        self._delete_button = QPushButton("Löschen", self)
        self._open_button.setEnabled(False)
        self._rename_button.setEnabled(False)
        self._delete_button.setEnabled(False)
        self._open_button.clicked.connect(self._on_open_clicked)
        self._rename_button.clicked.connect(self._on_rename_clicked)
        self._delete_button.clicked.connect(self._on_delete_clicked)
        QShortcut(QKeySequence("F2"), self, activated=self._on_rename_clicked)

        button_row = QHBoxLayout()
        button_row.addWidget(self._open_button)
        button_row.addWidget(self._rename_button)
        button_row.addWidget(self._delete_button)
        button_row.addStretch()

        close_button = QPushButton("Schließen", self)
        close_button.clicked.connect(self.accept)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table_view, 1)
        layout.addWidget(self._usage_panel)
        layout.addWidget(self._footer_label)
        layout.addLayout(button_row)
        layout.addLayout(close_row)

        self._update_footer()
        self._update_button_states()
        self._update_usage_panel()

    def _save_header_state(self) -> None:
        save_header_state(
            self._table_view.horizontalHeader(), _HEADER_STATE_SETTINGS_KEY, COLUMN_TITLES
        )

    def _apply_current_sort(self) -> None:
        header = self._table_view.horizontalHeader()
        section = header.sortIndicatorSection()
        if section >= 0:
            self._table_view.sortByColumn(section, header.sortIndicatorOrder())

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)

    def _reload(self) -> None:
        self._entries = self._media_service.list_all_media()
        self._table_model.set_entries(self._entries)
        self._apply_current_sort()
        self._update_footer()
        self._update_button_states()
        self._update_usage_panel()

    def _update_footer(self) -> None:
        total_size = sum(e.size_bytes for e in self._entries)
        unused = [e for e in self._entries if e.usage_count == 0]
        unused_size = sum(e.size_bytes for e in unused)
        self._footer_label.setText(
            f"{len(self._entries)} Dateien, {format_size_bytes(total_size)} insgesamt – "
            f"davon nicht verwendet: {len(unused)} Dateien, {format_size_bytes(unused_size)}"
        )

    def _selected_entries(self) -> list[MediaOverviewEntry]:
        rows = self._table_view.selectionModel().selectedRows()
        return [self._table_model.entry_at(row.row()) for row in rows]

    def _single_selected_entry(self) -> MediaOverviewEntry | None:
        entries = self._selected_entries()
        return entries[0] if len(entries) == 1 else None

    def _update_button_states(self) -> None:
        single = self._single_selected_entry()
        self._open_button.setEnabled(single is not None)
        self._rename_button.setEnabled(single is not None and single.media_id is not None)

        entries = self._selected_entries()
        if not entries:
            self._delete_button.setEnabled(False)
            self._delete_button.setToolTip("")
            return
        blocking = next((e for e in entries if e.usage_count > 0), None)
        if blocking is not None:
            self._delete_button.setEnabled(False)
            suffix = "en" if blocking.usage_count != 1 else ""
            self._delete_button.setToolTip(
                f"Wird noch in {blocking.usage_count} Sitzung{suffix} verwendet"
            )
        else:
            self._delete_button.setEnabled(True)
            self._delete_button.setToolTip("")

    def _update_usage_panel(self) -> None:
        entry = self._single_selected_entry()
        if entry is None or entry.media_id is None or entry.usage_count == 0:
            self._usage_panel.setVisible(False)
            return
        usages = self._media_service.list_usages(entry.media_id)
        self._usage_list.clear()
        for usage in usages:
            self._usage_list.addItem(
                f"{usage.client_name} – {usage.session_date.strftime('%d.%m.%Y, %H:%M')} Uhr"
            )
        self._usage_panel.setVisible(True)

    def _on_open_clicked(self) -> None:
        entry = self._single_selected_entry()
        if entry is None:
            return
        path = self._media_service.resolve_media_path_for_stored_filename(
            entry.stored_filename
        )
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

    def _on_rename_clicked(self) -> None:
        entry = self._single_selected_entry()
        if entry is None or entry.media_id is None:
            return
        dialog = RenameMediaDialog(
            self._media_service,
            entry.media_id,
            entry.original_filename or "",
            entry.usage_count,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _on_delete_clicked(self) -> None:
        entries = self._selected_entries()
        if not entries or any(e.usage_count > 0 for e in entries):
            return
        confirmed = ask_confirm_delete(
            "Die Dateien werden endgültig von der Datenplatte gelöscht.",
            title="Mediendateien löschen",
            parent=self,
        )
        if not confirmed:
            return
        known_ids = [e.media_id for e in entries if e.media_id is not None]
        unknown_names = [e.stored_filename for e in entries if e.media_id is None]
        failures = self._media_service.delete_unused_media(known_ids)
        failed_unknown = [
            name
            for name in unknown_names
            if not self._media_service.delete_unknown_file(name)
        ]
        if failures or failed_unknown:
            names = [f.original_filename for f in failures] + failed_unknown
            show_error(
                "Folgende Dateien konnten nicht gelöscht werden, vermutlich weil "
                "sie gerade geöffnet sind: " + ", ".join(names),
                parent=self,
            )
        self._reload()
```

- [ ] **Step 2: Write a test for the mixed-selection delete-button gate**

The Medienübersicht allows selecting several rows for "Löschen" at once. If even one selected row is still used, the whole button must be disabled — never delete the deletable ones and silently skip the rest. Create `tests/test_media_overview_dialog.py`:

```python
from pathlib import Path

from klientenverwaltung.models import Client, TreatmentSession, TreatmentType
from klientenverwaltung.services import MediaService, TreatmentSessionService
from klientenverwaltung.ui.media_overview_dialog import MediaOverviewDialog


def _make_source_file(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_delete_button_disabled_when_selection_mixes_used_and_unused(
    qapp,
    media_service: MediaService,
    treatment_session_service: TreatmentSessionService,
    treatment_type: TreatmentType,
    client: Client,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    used = media_service.import_file(
        treatment_session.id, _make_source_file(tmp_path, "used.jpg", b"a" * 5)
    )
    unused_outcome = media_service.import_file(
        treatment_session.id, _make_source_file(tmp_path, "unused.jpg", b"b" * 5)
    )
    media_service.remove_link(treatment_session.id, unused_outcome.media.id)

    dialog = MediaOverviewDialog(media_service)
    dialog._table_view.selectAll()  # selects both the used and the unused row
    dialog._update_button_states()

    assert dialog._delete_button.isEnabled() is False
    assert "Sitzung" in dialog._delete_button.toolTip()

    dialog._table_view.clearSelection()
    for row in range(dialog._table_model.rowCount()):
        if dialog._table_model.entry_at(row).media_id == unused_outcome.media.id:
            dialog._table_view.selectRow(row)
    dialog._update_button_states()

    assert dialog._delete_button.isEnabled() is True
```

- [ ] **Step 3: Run the test**

Run: `uv run pytest tests/test_media_overview_dialog.py -v`
Expected: PASS (the implementation in Step 1 already handles this correctly — this test pins it, the same way Auftrag C1 pinned already-correct behavior in a few places).

- [ ] **Step 4: ruff**

Run: `uv run ruff check src/klientenverwaltung/ui/media_overview_dialog.py tests/test_media_overview_dialog.py`
Expected: no errors (fix any import-order issues `ruff --fix` reports, matching Auftrag C1's precedent).

- [ ] **Step 5: Commit**

```bash
git add src/klientenverwaltung/ui/media_overview_dialog.py tests/test_media_overview_dialog.py
git commit -m "feat: add MediaOverviewDialog (Medienübersicht)"
```

---

### Task 10: `SelectExistingMediaDialog`

**Files:**
- Create: `src/klientenverwaltung/ui/media_picker_table_model.py`
- Create: `src/klientenverwaltung/ui/select_existing_media_dialog.py`

**Interfaces:**
- Consumes: `MediaPickerEntry` (Task 5), `MediaService.list_unlinked_media_for_session`/`.link_existing_media` (Tasks 2/5), `KIND_LABELS`/`format_size_bytes` (Task 8)
- Produces: `MediaPickerTableModel`, `SelectExistingMediaDialog(media_service, session_id, parent=None)`

- [ ] **Step 1: Write the picker table model**

`src/klientenverwaltung/ui/media_picker_table_model.py`:

```python
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from klientenverwaltung.services.media_service import MediaPickerEntry
from klientenverwaltung.ui.media_table_model import KIND_LABELS, format_size_bytes

COLUMN_TITLES = ("Name", "Art", "Größe")


class MediaPickerTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._entries: list[MediaPickerEntry] = []

    def set_entries(self, entries: list[MediaPickerEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def entry_at(self, row: int) -> MediaPickerEntry:
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
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        entry = self._entries[index.row()]
        column = index.column()
        if column == 0:
            return entry.original_filename
        if column == 1:
            return KIND_LABELS[entry.media_kind]
        if column == 2:
            return format_size_bytes(entry.size_bytes)
        return None
```

- [ ] **Step 2: Write the picker dialog**

`src/klientenverwaltung/ui/select_existing_media_dialog.py`:

```python
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from klientenverwaltung.services import MediaService
from klientenverwaltung.ui.media_picker_table_model import (
    COLUMN_TITLES,
    MediaPickerTableModel,
)
from klientenverwaltung.ui.window_settings import (
    finalize_column_widths,
    restore_geometry,
    restore_header_state,
    save_geometry,
    save_header_state,
)

_GEOMETRY_SETTINGS_KEY = "select_existing_media/geometry"
_HEADER_STATE_SETTINGS_KEY = "select_existing_media/header_state"
_SEARCH_DEBOUNCE_MS = 250
_NAME_COLUMN = 0


class SelectExistingMediaDialog(QDialog):
    """"Aus vorhandenen Medien …" (Auftrag C2) - links files already on
    the drive to a session without copying anything. Lists every media
    file not yet linked to this particular session.
    """

    def __init__(
        self, media_service: MediaService, session_id: int, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._media_service = media_service
        self._session_id = session_id

        self.setWindowTitle("Aus vorhandenen Medien")
        self.setModal(True)
        self.resize(550, 450)
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        self._search_edit = QLineEdit(self)
        self._search_edit.setPlaceholderText("Suche nach Name …")

        self._table_model = MediaPickerTableModel()
        self._table_view = QTableView(self)
        self._table_view.setModel(self._table_model)
        self._table_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._table_view.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table_view.verticalHeader().setVisible(False)

        self._table_model.set_entries(
            self._media_service.list_unlinked_media_for_session(session_id)
        )
        header = self._table_view.horizontalHeader()
        restored = restore_header_state(header, _HEADER_STATE_SETTINGS_KEY, COLUMN_TITLES)
        if not restored:
            self._table_view.resizeColumnsToContents()
        finalize_column_widths(header, self._table_model.columnCount(), _NAME_COLUMN, restored)
        header.sectionResized.connect(self._save_header_state)
        self._table_view.selectionModel().selectionChanged.connect(
            self._update_button_states
        )

        self._add_button = QPushButton("Hinzufügen", self)
        self._add_button.setEnabled(False)
        self._add_button.setDefault(True)
        self._add_button.clicked.connect(self._on_add_clicked)
        cancel_button = QPushButton("Abbrechen", self)
        cancel_button.clicked.connect(self.reject)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self._add_button)
        button_row.addWidget(cancel_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self._search_edit)
        layout.addWidget(self._table_view, 1)
        layout.addLayout(button_row)

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(_SEARCH_DEBOUNCE_MS)
        self._debounce_timer.timeout.connect(self._reload)
        self._search_edit.textChanged.connect(lambda _: self._debounce_timer.start())

    def _save_header_state(self) -> None:
        save_header_state(
            self._table_view.horizontalHeader(), _HEADER_STATE_SETTINGS_KEY, COLUMN_TITLES
        )

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)

    def _reload(self) -> None:
        search = self._search_edit.text().strip() or None
        self._table_model.set_entries(
            self._media_service.list_unlinked_media_for_session(
                self._session_id, search=search
            )
        )
        self._update_button_states()

    def _update_button_states(self) -> None:
        has_selection = bool(self._table_view.selectionModel().selectedRows())
        self._add_button.setEnabled(has_selection)

    def _on_add_clicked(self) -> None:
        rows = self._table_view.selectionModel().selectedRows()
        media_ids = [self._table_model.entry_at(row.row()).media_id for row in rows]
        if not media_ids:
            return
        self._media_service.link_existing_media(self._session_id, media_ids)
        self.accept()
```

- [ ] **Step 3: ruff**

Run: `uv run ruff check src/klientenverwaltung/ui/media_picker_table_model.py src/klientenverwaltung/ui/select_existing_media_dialog.py`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add src/klientenverwaltung/ui/media_picker_table_model.py src/klientenverwaltung/ui/select_existing_media_dialog.py
git commit -m "feat: add SelectExistingMediaDialog (Aus vorhandenen Medien)"
```

---

### Task 11: Wire it all into `MediaDialog`

**Files:**
- Modify: `src/klientenverwaltung/ui/media_dialog.py`

**Interfaces:**
- Consumes: `RenameMediaDialog` (Task 7), `SelectExistingMediaDialog` (Task 10), `offer_to_delete_now_unused_media` (Task 6), `MediaService.count_sessions_for_media` (Task 2)

- [ ] **Step 1: Rename "Datei anfügen …" to "Neue Datei …" and add the two new buttons**

In `src/klientenverwaltung/ui/media_dialog.py`, change:

```python
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
```

to:

```python
        self._attach_button = QPushButton("Neue Datei …", self)
        self._select_existing_button = QPushButton("Aus vorhandenen Medien …", self)
        self._open_button = QPushButton("Öffnen", self)
        self._rename_button = QPushButton("Umbenennen", self)
        self._remove_link_button = QPushButton("Verknüpfung entfernen", self)
        self._open_button.setEnabled(False)
        self._rename_button.setEnabled(False)
        self._remove_link_button.setEnabled(False)
        self._attach_button.clicked.connect(self._on_attach_clicked)
        self._select_existing_button.clicked.connect(self._on_select_existing_clicked)
        self._open_button.clicked.connect(self._on_open_clicked)
        self._rename_button.clicked.connect(self._on_rename_clicked)
        self._remove_link_button.clicked.connect(self._on_remove_link_clicked)
        QShortcut(QKeySequence("F2"), self, activated=self._on_rename_clicked)

        button_row = QHBoxLayout()
        button_row.addWidget(self._attach_button)
        button_row.addWidget(self._select_existing_button)
        button_row.addWidget(self._open_button)
        button_row.addWidget(self._rename_button)
        button_row.addWidget(self._remove_link_button)
        button_row.addStretch()
```

Add the new imports at the top:

```python
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
```

(merge with the existing `from PySide6.QtGui import QDesktopServices` line)

```python
from klientenverwaltung.ui.media_cleanup import offer_to_delete_now_unused_media
from klientenverwaltung.ui.rename_media_dialog import RenameMediaDialog
from klientenverwaltung.ui.select_existing_media_dialog import SelectExistingMediaDialog
```

- [ ] **Step 2: Update `_set_busy` and add the two click handlers**

Change `_set_busy` to also cover the new buttons:

```python
    def _set_busy(self, busy: bool) -> None:
        self._importing = busy
        self._attach_button.setEnabled(not busy)
        self._select_existing_button.setEnabled(not busy)
        self._close_button.setEnabled(not busy)
        self._table_view.setEnabled(not busy)
        self._update_button_states()
```

Change `_update_button_states` to also gate the rename button:

```python
    def _update_button_states(self) -> None:
        has_selection = self._selected_entry() is not None
        self._open_button.setEnabled(has_selection and not self._importing)
        self._rename_button.setEnabled(has_selection and not self._importing)
        self._remove_link_button.setEnabled(has_selection and not self._importing)
```

Add the two new handlers (near `_on_attach_clicked`):

```python
    def _on_select_existing_clicked(self) -> None:
        dialog = SelectExistingMediaDialog(self._media_service, self._session_id, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload_media()

    def _on_rename_clicked(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        usage_count = self._media_service.count_sessions_for_media(entry.media_id)
        dialog = RenameMediaDialog(
            self._media_service, entry.media_id, entry.original_filename, usage_count, parent=self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._reload_media()
```

- [ ] **Step 3: Ask about now-unused media after removing a link**

Change `_on_remove_link_clicked`:

```python
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
        offer_to_delete_now_unused_media(self._media_service, [entry.media_id], parent=self)
        self._reload_media()
```

- [ ] **Step 4: ruff + full suite**

Run: `uv run ruff check src/klientenverwaltung/ui/media_dialog.py`
Run: `uv run pytest -q`
Expected: no errors, all green (no test directly exercises these new buttons yet — Task 16 covers manual verification; the existing `tests/test_media_dialog_threading.py` tests must still pass unchanged, since they exercise `_start_import`/`_on_import_finished` directly, untouched by this task).

- [ ] **Step 5: Commit**

```bash
git add src/klientenverwaltung/ui/media_dialog.py
git commit -m "feat: add Umbenennen, Aus vorhandenen Medien, and the now-unused prompt to the Medienfenster"
```

---

### Task 12: `MainWindow` — "Medienübersicht" menu entry

**Files:**
- Modify: `src/klientenverwaltung/ui/main_window.py`

**Interfaces:**
- Consumes: `MediaOverviewDialog` (Task 9)

- [ ] **Step 1: Store `media_service` and add the menu action**

In `src/klientenverwaltung/ui/main_window.py`, change `__init__`:

```python
        super().__init__()
        self._treatment_type_service = treatment_type_service
        self._media_service = media_service
        self._engine = engine
```

Add the import:

```python
from klientenverwaltung.ui.media_overview_dialog import MediaOverviewDialog
```

In `_build_menu`, add right after the treatment-types action:

```python
        settings_menu = self.menuBar().addMenu("Einstellungen")
        treatment_types_action = settings_menu.addAction("Behandlungsarten verwalten…")
        treatment_types_action.triggered.connect(self._open_treatment_type_dialog)
        media_overview_action = settings_menu.addAction("Medienübersicht…")
        media_overview_action.triggered.connect(self._open_media_overview_dialog)
```

Add the handler near `_open_treatment_type_dialog`:

```python
    def _open_media_overview_dialog(self) -> None:
        dialog = MediaOverviewDialog(self._media_service, parent=self)
        dialog.exec()
```

- [ ] **Step 2: ruff + full suite**

Run: `uv run ruff check src/klientenverwaltung/ui/main_window.py`
Run: `uv run pytest -q`
Expected: no errors, all green.

- [ ] **Step 3: Commit**

```bash
git add src/klientenverwaltung/ui/main_window.py
git commit -m "feat: add Medienübersicht menu entry"
```

---

### Task 13: `ClientListWidget` — now-unused prompt after deleting a client

**Files:**
- Modify: `src/klientenverwaltung/ui/client_list_widget.py`

**Interfaces:**
- Consumes: `MediaService.list_media_ids_for_client` (Task 4), `offer_to_delete_now_unused_media` (Task 6)

- [ ] **Step 1: Update `_on_delete_clicked`**

Add the import:

```python
from klientenverwaltung.ui.media_cleanup import offer_to_delete_now_unused_media
```

Change `_on_delete_clicked`:

```python
    def _on_delete_clicked(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        confirmed = ask_confirm_delete(
            f'Klient "{entry.first_name} {entry.last_name}" und alle zugehörigen '
            "Sitzungen unwiderruflich löschen?\n\nDies kann nicht rückgängig gemacht werden.",
            title="Klient löschen",
            parent=self,
        )
        if not confirmed:
            return
        candidate_media_ids = self._media_service.list_media_ids_for_client(entry.id)
        try:
            self._client_service.delete_client(entry.id)
        except ServiceError as exc:
            show_error(str(exc), parent=self)
            return
        offer_to_delete_now_unused_media(self._media_service, candidate_media_ids, parent=self)
        self._reload()
```

(This does NOT touch `_on_archive_clicked` — archiving must never trigger the now-unused prompt, per the Auftrag's own instruction.)

- [ ] **Step 2: ruff + full suite**

Run: `uv run ruff check src/klientenverwaltung/ui/client_list_widget.py`
Run: `uv run pytest -q`
Expected: no errors, all green.

- [ ] **Step 3: Commit**

```bash
git add src/klientenverwaltung/ui/client_list_widget.py
git commit -m "feat: ask about now-unused media after deleting a client"
```

---

### Task 14: `ClientSessionsDialog` — now-unused prompt after deleting a session

**Files:**
- Modify: `src/klientenverwaltung/ui/client_sessions_dialog.py`

**Interfaces:**
- Consumes: `MediaService.list_media_for_session` (existing), `offer_to_delete_now_unused_media` (Task 6)

- [ ] **Step 1: Update `_on_delete_session_clicked`**

Add the import:

```python
from klientenverwaltung.ui.media_cleanup import offer_to_delete_now_unused_media
```

Change `_on_delete_session_clicked`:

```python
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
```

- [ ] **Step 2: ruff + full suite**

Run: `uv run ruff check src/klientenverwaltung/ui/client_sessions_dialog.py`
Run: `uv run pytest -q`
Expected: no errors, all green.

- [ ] **Step 3: Commit**

```bash
git add src/klientenverwaltung/ui/client_sessions_dialog.py
git commit -m "feat: ask about now-unused media after deleting a session"
```

---

### Task 15: Docs

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Extend the media rule under `### Regeln`**

In `CLAUDE.md`, change the existing Auftrag-C1 media bullet under `### Regeln` (in `## Datenmodell`):

```markdown
- Mediendateien liegen im Ordner "medien" auf der Datenplatte, benannt mit einer
  UUID statt dem Originalnamen. Eine Datei kann mehreren Sitzungen zugeordnet sein
  (Duplikate werden über den Dateiinhalt/SHA-256 erkannt, nie erneut kopiert).
  Sitzung/Klient löschen entfernt nur die Verknüpfung (`session_media`), nie die
  Datei oder den `media`-Eintrag (Aufräumen verwaister Dateien ist Auftrag C2).
  Das Original bleibt immer unverändert, wo der Anwender es ausgewählt hat -
  das Programm löscht es nie.
```

to:

```markdown
- Mediendateien liegen im Ordner "medien" auf der Datenplatte, benannt mit einer
  UUID statt dem Originalnamen. Eine Datei kann mehreren Sitzungen zugeordnet sein
  (Duplikate werden über den Dateiinhalt/SHA-256 erkannt, nie erneut kopiert).
  Das Original bleibt immer unverändert, wo der Anwender es ausgewählt hat -
  das Programm löscht es nie.
- Mediendateien werden NIE automatisch gelöscht, nur nach ausdrücklicher
  Bestätigung des Anwenders. Sitzung löschen, Klient endgültig löschen und
  "Verknüpfung entfernen" im Medienfenster entfernen zunächst nur die
  Verknüpfung (`session_media`); wird eine Datei dadurch von keiner Sitzung
  mehr verwendet, fragt das Programm danach einmal, ob sie jetzt endgültig
  gelöscht werden soll (Auftrag C2) - "Behalten" lässt sie unverändert liegen,
  sichtbar in der Medienübersicht als 0×. Gilt NICHT für Archivieren. Die
  Medienübersicht (Menü "Einstellungen") zeigt jede Datei, ihre Verwendung
  und erkennt beide Abweichungen zwischen Medienordner und Datenbank: einen
  DB-Eintrag ohne Datei ("Datei fehlt") und eine Datei ohne DB-Eintrag
  ("Unbekannte Datei").
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document the Medienübersicht and the never-auto-delete rule"
```

---

### Task 16: Final verification

**Files:** none (verification only)

- [ ] **Step 1: Full automated check**

Run: `uv run ruff check .`
Run: `uv run pytest -q`
Expected: both clean/all-green.

- [ ] **Step 2: Build the debug .exe**

Follow `docs/build.md`'s debug-build steps.

- [ ] **Step 3: Manual test, using only test data**

Using the debug build against a scratch/test data drive:
- Open "Einstellungen" → "Medienübersicht…" — confirm the list shows every media file with correct Größe/Verwendet, default-sorted 0× first then by name, and the footer totals look right.
- Select a used file — confirm "Verwendet in:" shows the right client(s)/date(s), and "Löschen" is disabled with the usage-count tooltip.
- Select an unused file — confirm "Verwendet in:" disappears and "Löschen" is enabled.
- Rename a file (button and F2) — confirm the displayed name changes everywhere (Medienübersicht, the session's Medienfenster) but the file still opens correctly.
- In a session's Medienfenster: use "Aus vorhandenen Medien …" to attach an already-imported file without copying; confirm the medien folder gains no new file.
- Remove a link that was the file's only use — confirm the "n Mediendateien werden nicht mehr verwendet" prompt appears; test both "Behalten" (file stays, shows as 0× in the Medienübersicht) and "Löschen" (file and DB row both gone).
- Delete a session/client whose only media would become unused — confirm the same prompt fires there too, and confirm archiving a client does NOT trigger it.
- Manually copy an unrelated file directly into the drive's `medien` folder (simulating a leftover file) and reopen the Medienübersicht — confirm it appears as "Unbekannte Datei" and can be deleted.

- [ ] **Step 4: Report back**

Summarize the manual verification result (pass/fail per bullet above) — no commit for this task, it's verification only.
