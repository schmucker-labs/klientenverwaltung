from __future__ import annotations

import hashlib
import logging
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
from klientenverwaltung.services.errors import (
    NotFoundError,
    ServiceError,
    ValidationError,
)
from klientenverwaltung.services.transaction import transaction

_logger = logging.getLogger(__name__)

MEDIA_FOLDER_NAME = "medien"
_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB per progress tick
_FORBIDDEN_FILENAME_CHARS = frozenset('\\/:*?"<>|')

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
class MediaPickerEntry:
    """One row of the "Aus vorhandenen Medien" picker (Auftrag C2) - media
    not yet linked to the session the picker was opened for."""

    media_id: int
    original_filename: str
    media_kind: MediaKind
    size_bytes: int


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

    def resolve_media_path_for_entry(self, entry: SessionMediaEntry) -> Path:
        return self._media_dir / entry.stored_filename

    def resolve_media_path_for_stored_filename(self, stored_filename: str) -> Path:
        return self._media_dir / stored_filename

    def rename_media(self, media_id: int, new_original_filename: str) -> Media:
        new_name = new_original_filename.strip()
        # The visible part is everything before the last dot - a name that
        # is only whitespace plus an extension (e.g. "   .jpg") must still
        # count as empty. Checked via the last "." rather than
        # Path(...).stem/.suffix: pathlib treats a name that *starts* with
        # a dot as a dotfile with no suffix at all (Path(".jpg").stem ==
        # ".jpg"), which would let "   .jpg" straight through.
        visible_part = new_name[: new_name.rfind(".")] if "." in new_name else new_name
        if not visible_part.strip():
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

    def cleanup_orphaned_part_files(self) -> int:
        """Removes .part files left behind by an import that never
        finished (a hard kill, power loss, a dead battery) - by
        definition incomplete and never recorded in the database, so
        removing them loses nothing. Only ever touches files directly
        inside the medien folder whose name ends in ".part"; nothing else
        there, and nothing outside it.

        Nothing in this program currently stops two instances from
        running at once against the same data drive. If another running
        instance is mid-import, its .part file is still open for writing,
        and Windows refuses to delete an open file out from under it -
        that failure is exactly the expected outcome for a file that
        turns out not to be orphaned after all, so it is skipped silently
        (counted, but never logged with the filename) rather than treated
        as an error.
        """
        if not self._media_dir.exists():
            return 0
        removed = 0
        skipped = 0
        for path in self._media_dir.glob("*.part"):
            try:
                path.unlink()
                removed += 1
            except OSError:
                skipped += 1
        if skipped:
            _logger.warning(
                "%d liegengebliebene .part-Datei(en) konnten nicht entfernt "
                "werden (vermutlich durch eine andere laufende Instanz in "
                "Benutzung).",
                skipped,
            )
        return removed
