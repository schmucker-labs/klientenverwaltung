import shutil
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

BACKUP_FILENAME_PREFIX = "klientenverwaltung_backup_"
BACKUP_FILENAME_GLOB = f"{BACKUP_FILENAME_PREFIX}*.db"
MAX_BACKUPS_KEPT = 10

# Safety backups taken immediately before a restore live in their own
# subfolder with their own, shorter rotation, so they never compete with -
# or evict - the regular backups' MAX_BACKUPS_KEPT slots.
PRE_RESTORE_SUBFOLDER_NAME = "vor-wiederherstellung"
PRE_RESTORE_MAX_BACKUPS_KEPT = 5


class BackupError(Exception):
    """A backup could not be created or restored. Message text is German."""


_TIMESTAMP_FORMAT = "%Y%m%d_%H%M%S"


def backup_filename(timestamp: datetime) -> str:
    return f"{BACKUP_FILENAME_PREFIX}{timestamp:{_TIMESTAMP_FORMAT}}.db"


def parse_backup_timestamp(path: Path) -> datetime | None:
    """The timestamp encoded in a backup's filename, or None if it doesn't match."""
    if not path.stem.startswith(BACKUP_FILENAME_PREFIX):
        return None
    raw = path.stem[len(BACKUP_FILENAME_PREFIX) :]
    try:
        return datetime.strptime(raw, _TIMESTAMP_FORMAT)
    except ValueError:
        return None


def create_backup(
    engine: Engine,
    target_folder: Path,
    *,
    now: datetime | None = None,
    max_kept: int = MAX_BACKUPS_KEPT,
) -> Path:
    """Creates one timestamped, encrypted copy of the database in target_folder.

    Uses SQLite's VACUUM INTO against the live connection rather than a
    plain file copy, which would be unsafe while the database may be open
    for writing (SQLCipher supports VACUUM INTO the same way plain SQLite
    does - the copy comes out encrypted with the same key). Then rotates
    target_folder down to the max_kept most recent backups.
    """
    try:
        target_folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError(
            f"Sicherungsordner ist nicht erreichbar: {target_folder}"
        ) from exc

    timestamp = now if now is not None else datetime.now()
    destination = _next_available_destination(target_folder, timestamp)
    # VACUUM INTO's filename is a string literal, not a bind parameter,
    # and destination is always a program-generated path, never external
    # input - a single-quote escape is sufficient and safe here.
    escaped_destination = str(destination).replace("'", "''")
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql(f"VACUUM INTO '{escaped_destination}'")
    except SQLAlchemyError as exc:
        raise BackupError(f"Sicherung konnte nicht erstellt werden: {exc}") from exc

    _rotate_backups(target_folder, max_kept)
    return destination


def create_pre_restore_backup(
    engine: Engine, folder: Path, *, now: datetime | None = None
) -> Path:
    """A safety backup taken immediately before restoring another backup.

    Lives in folder's PRE_RESTORE_SUBFOLDER_NAME subfolder with its own,
    shorter rotation - never in folder itself, so it can never displace a
    regular backup's rotation slot.
    """
    return create_backup(
        engine,
        folder / PRE_RESTORE_SUBFOLDER_NAME,
        now=now,
        max_kept=PRE_RESTORE_MAX_BACKUPS_KEPT,
    )


def _next_available_destination(folder: Path, timestamp: datetime) -> Path:
    """The timestamp's filename, or - on a same-second collision (e.g. two
    backups triggered in quick succession) - the next free "_2", "_3", ...
    variant. VACUUM INTO refuses to write to a file that already exists."""
    candidate = folder / backup_filename(timestamp)
    if not candidate.exists():
        return candidate
    stem, suffix = backup_filename(timestamp).rsplit(".", 1)
    counter = 2
    while True:
        candidate = folder / f"{stem}_{counter}.{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def _rotate_backups(folder: Path, max_kept: int) -> None:
    for stale in list_backups(folder)[max_kept:]:
        stale.unlink(missing_ok=True)


def list_backups(folder: Path) -> list[Path]:
    """Existing backups in folder, newest first.

    Filenames encode their timestamp in a lexicographically sortable
    format, so a plain reverse name sort is enough - no need to touch
    filesystem mtimes.
    """
    try:
        if not folder.exists():
            return []
        return sorted(folder.glob(BACKUP_FILENAME_GLOB), reverse=True)
    except OSError:
        return []


def most_recent_backup(folders: Sequence[Path]) -> Path | None:
    """The newest regular backup across all given folders, or None."""
    candidates = [path for folder in folders for path in list_backups(folder)]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.name)


def is_database_unchanged_since_backup(db_path: Path, last_backup: Path | None) -> bool:
    """True if db_path was not modified after last_backup was taken.

    A False result (including "can't tell") means a fresh backup is
    warranted - this only ever suppresses a backup when it can positively
    confirm one would be redundant.
    """
    if last_backup is None:
        return False
    last_backup_time = parse_backup_timestamp(last_backup)
    if last_backup_time is None:
        return False
    try:
        db_modified_time = datetime.fromtimestamp(db_path.stat().st_mtime)
    except OSError:
        return False
    # Backup filenames only carry whole-second resolution (no microseconds),
    # so db_modified_time must be truncated to match - otherwise its
    # sub-second precision would make it look "newer" than the backup even
    # when the backup was taken immediately afterwards, in the same second.
    return db_modified_time.replace(microsecond=0) <= last_backup_time


def is_writable_directory(path: Path) -> bool:
    """True if path exists, is a directory, and a file can actually be
    written into it (existence/is_dir alone doesn't catch read-only shares
    or permission-denied cases)."""
    if not path.is_dir():
        return False
    probe = path / ".klientenverwaltung_write_test"
    try:
        probe.write_bytes(b"")
        probe.unlink()
    except OSError:
        return False
    return True


def delete_backup(path: Path) -> None:
    try:
        path.unlink()
    except OSError as exc:
        raise BackupError(f"Sicherung konnte nicht gelöscht werden: {exc}") from exc


def restore_backup(backup_path: Path, db_path: Path) -> None:
    """Overwrites db_path with backup_path's contents.

    Copies to a temporary file next to db_path first, then atomically
    replaces db_path only once that copy fully succeeded - so a failure
    partway through (disk full, network drive drops) never leaves db_path
    itself half-overwritten; it is either fully replaced or untouched.

    Callers must ensure db_path is not open by any live connection when
    calling this (the caller is expected to dispose its engine first), and
    should already have backed up the current database - this function
    only performs the overwrite itself.
    """
    if not backup_path.exists():
        raise BackupError(f"Sicherung wurde nicht gefunden: {backup_path}")
    tmp_path = db_path.with_name(db_path.name + ".restoring")
    try:
        shutil.copy2(backup_path, tmp_path)
        tmp_path.replace(db_path)
    except OSError as exc:
        tmp_path.unlink(missing_ok=True)
        raise BackupError(
            f"Sicherung konnte nicht wiederhergestellt werden: {exc}"
        ) from exc
