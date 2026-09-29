import ctypes
import string
import sys
import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path

# SQLAlchemy resolves the "pysqlcipher" dialect by string name at runtime, so
# it must be imported explicitly here to end up in a PyInstaller-frozen build.
import sqlalchemy.dialects.sqlite.pysqlcipher  # noqa: F401
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.exc import DatabaseError, SQLAlchemyError

from alembic import command
from klientenverwaltung import config

IDENTIFIER_FILENAME = "klientenverwaltung.id"
DB_FILENAME = "klientenverwaltung.db"
MIN_PASSWORD_LENGTH = 12
DRIVE_CHECK_TIMEOUT_SECONDS = 2.0


class StorageError(Exception):
    """Base class for storage-layer errors (Datenplatte/Verbindung); message text is German."""


class DataDriveNotFoundError(StorageError):
    """No drive carrying a valid identifier file was found."""


class MultipleDataDrivesFoundError(StorageError):
    """More than one drive carries a valid identifier file; cannot pick one automatically."""

    def __init__(self, message: str, candidate_paths: list[Path]) -> None:
        super().__init__(message)
        self.candidate_paths = candidate_paths


class IncorrectPasswordError(StorageError):
    """The given password does not decrypt the database."""


class DataDriveDisconnectedError(StorageError):
    """The connection to the data drive was lost while the application was running."""


class WeakPasswordError(StorageError):
    """The given password is shorter than MIN_PASSWORD_LENGTH."""


def create_encrypted_engine(db_path: Path, password: str) -> Engine:
    url = f"sqlite+pysqlcipher://:{password}@/{db_path.as_posix()}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA synchronous = FULL")
        cursor.close()

    return engine


def _assigned_drive_letters() -> list[str]:
    """Windows drive letters currently assigned, via a fast bitmask query (never blocks)."""
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]
    return [
        letter for i, letter in enumerate(string.ascii_uppercase) if bitmask & (1 << i)
    ]


def _read_identifier_file(drive_root: Path) -> str | None:
    try:
        content = (drive_root / IDENTIFIER_FILENAME).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        uuid.UUID(content)
    except ValueError:
        return None
    return content


def _read_identifier_file_bounded(
    drive_root: Path,
    *,
    reader: Callable[[Path], str | None],
    timeout: float,
) -> str | None:
    """Reads the identifier file with a timeout, so one unresponsive drive can't hang the search."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(reader, drive_root)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError:
            return None


def _scan_for_identifier(
    candidate_roots: Sequence[Path],
    *,
    reader: Callable[[Path], str | None],
    timeout: float,
) -> list[Path]:
    if not candidate_roots:
        return []
    candidates: list[Path] = []
    with ThreadPoolExecutor(max_workers=len(candidate_roots)) as pool:
        future_to_root = {pool.submit(reader, root): root for root in candidate_roots}
        for future, root in future_to_root.items():
            try:
                content = future.result(timeout=timeout)
            except FutureTimeoutError:
                continue
            if content is not None:
                candidates.append(root)
    return candidates


def _find_data_drive_among(
    candidate_roots: Sequence[Path],
    *,
    last_known_path: Path | None,
    reader: Callable[[Path], str | None] = _read_identifier_file,
    timeout: float = DRIVE_CHECK_TIMEOUT_SECONDS,
) -> Path:
    """Core, dependency-injected drive search: checks last_known_path first, then all candidates.

    Kept separate from find_data_drive() so tests can exercise it against
    temporary directories standing in for drives, and inject a slow reader to
    verify that an unresponsive drive is skipped rather than blocking the
    whole search.
    """
    if last_known_path is not None:
        content = _read_identifier_file_bounded(
            last_known_path, reader=reader, timeout=timeout
        )
        if content is not None:
            return last_known_path

    candidates = _scan_for_identifier(candidate_roots, reader=reader, timeout=timeout)

    if not candidates:
        raise DataDriveNotFoundError(
            "Datenplatte wurde nicht gefunden. Bitte Datenplatte anschliessen und erneut versuchen."
        )
    if len(candidates) > 1:
        joined = ", ".join(str(path) for path in candidates)
        raise MultipleDataDrivesFoundError(
            f"Es wurden mehrere Laufwerke mit einer Kennungsdatei gefunden: {joined}. "
            "Bitte nur die richtige Datenplatte anschliessen.",
            candidates,
        )
    return candidates[0]


def find_data_drive() -> Path:
    """Finds the real data drive among currently assigned Windows drive letters."""
    last_known = config.get_last_known_drive_path()
    candidate_roots = [Path(f"{letter}:\\") for letter in _assigned_drive_letters()]
    found = _find_data_drive_among(candidate_roots, last_known_path=last_known)
    config.set_last_known_drive_path(found)
    return found


def _bundle_root() -> Path:
    """Where alembic.ini and alembic/ live.

    In a normal dev checkout, that's the repo root. Frozen into a
    PyInstaller .exe, source files no longer exist on disk as such -
    sys._MEIPASS is the extraction directory (onefile) or the app's own
    install directory (onedir), either way wherever klientenverwaltung.spec's
    `datas` placed its copies of alembic.ini/alembic/.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[2]


def _alembic_config(connection: Connection | None = None) -> Config:
    bundle_root = _bundle_root()
    alembic_cfg = Config(str(bundle_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(bundle_root / "alembic"))
    if connection is not None:
        alembic_cfg.attributes["connection"] = connection
    return alembic_cfg


def open_database(db_path: Path, password: str) -> Engine:
    """Opens an existing encrypted database, verifying the password up front.

    Raises IncorrectPasswordError instead of letting SQLCipher's generic
    "file is not a database" error (indistinguishable from real corruption)
    reach callers unexplained. Also registers a handler that turns a mid-
    operation loss of the drive into DataDriveDisconnectedError.
    """
    if not db_path.exists():
        raise StorageError(f"Datenbankdatei wurde nicht gefunden: {db_path}")

    engine = create_encrypted_engine(db_path, password)
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT count(*) FROM sqlite_master")
    except DatabaseError as exc:
        engine.dispose()
        raise IncorrectPasswordError("Das eingegebene Passwort ist falsch.") from exc
    except SQLAlchemyError as exc:
        engine.dispose()
        raise StorageError("Datenbank konnte nicht geoeffnet werden.") from exc

    @event.listens_for(engine, "handle_error")
    def _translate_disconnect(context) -> None:
        if not db_path.exists():
            raise DataDriveDisconnectedError(
                "Die Verbindung zur Datenplatte wurde unterbrochen. Bitte Datenplatte "
                "wieder anschliessen und die Anwendung neu starten."
            ) from context.original_exception

    return engine


def set_up_data_drive(drive_root: Path, password: str) -> Engine:
    """Einrichtungsfunktion: identifier file, encrypted DB (via Alembic).

    No treatment types are created here - the user creates their own,
    per Auftrag D1 ("Keine Standard-Behandlungsarten mehr").
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Das Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein."
        )

    identifier_path = drive_root / IDENTIFIER_FILENAME
    if identifier_path.exists():
        raise StorageError(
            f"Auf diesem Laufwerk existiert bereits eine Kennungsdatei: {identifier_path}"
        )

    db_path = drive_root / DB_FILENAME
    if db_path.exists():
        raise StorageError(
            f"Auf diesem Laufwerk existiert bereits eine Datenbankdatei: {db_path}"
        )

    identifier_path.write_text(str(uuid.uuid4()), encoding="utf-8")

    engine = create_encrypted_engine(db_path, password)
    try:
        apply_migrations(engine)
    except StorageError:
        # Never leave a half-set-up drive behind: a failure here must look,
        # from the outside, exactly like set_up_data_drive() was never
        # called.
        engine.dispose()
        identifier_path.unlink(missing_ok=True)
        db_path.unlink(missing_ok=True)
        raise

    config.set_last_known_drive_path(drive_root)
    return engine


def list_available_drives() -> list[Path]:
    """Currently assigned Windows drive letters, as candidate roots to set up."""
    return [Path(f"{letter}:\\") for letter in _assigned_drive_letters()]


_DRIVE_TYPE_FALLBACK_NAMES = {
    2: "Wechseldatenträger",  # DRIVE_REMOVABLE
    3: "Lokaler Datenträger",  # DRIVE_FIXED
    4: "Netzlaufwerk",  # DRIVE_REMOTE
    5: "CD-/DVD-Laufwerk",  # DRIVE_CDROM
}


def describe_drive(drive_root: Path) -> str:
    """Drive path plus its Windows volume name, e.g. "D:\\ (USB-Datenträger)".

    Mirrors what Windows Explorer shows: the actual volume label if one is
    set, otherwise a generic name for the drive's media type (matching the
    label Explorer itself falls back to for an unlabeled drive) - never
    just the bare drive letter, which alone rarely helps the user recognize
    the correct one among several plugged-in drives.
    """
    root = f"{str(drive_root)[0]}:\\"
    volume_name_buffer = ctypes.create_unicode_buffer(261)
    success = ctypes.windll.kernel32.GetVolumeInformationW(  # type: ignore[attr-defined]
        root, volume_name_buffer, len(volume_name_buffer), None, None, None, None, 0
    )
    label = volume_name_buffer.value.strip() if success else ""
    if not label:
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(root)  # type: ignore[attr-defined]
        label = _DRIVE_TYPE_FALLBACK_NAMES.get(drive_type, "Datenträger")
    return f"{drive_root} ({label})"


def is_removable_drive(drive_root: Path) -> bool:
    """True if Windows reports this drive's media as removable (e.g. a USB stick).

    Note: many external USB hard drives are reported as DRIVE_FIXED rather
    than DRIVE_REMOVABLE by Windows - this is a media-type check, not a
    "is it plugged in via USB" check. Used only to show a dismissible
    warning during setup, never to block a choice outright.
    """
    drive_removable = 2
    root = f"{str(drive_root)[0]}:\\"
    return ctypes.windll.kernel32.GetDriveTypeW(root) == drive_removable  # type: ignore[attr-defined]


def drive_already_set_up(drive_root: Path) -> bool:
    """True if drive_root already carries a valid Kennungsdatei."""
    return _read_identifier_file(drive_root) is not None


def apply_migrations(engine: Engine) -> None:
    """Applies pending Alembic migrations against an already-open, encrypted engine.

    Called both by set_up_data_drive() and on every normal startup, per
    "Migrationen werden beim Programmstart automatisch angewendet".
    """
    try:
        with engine.connect() as connection:
            command.upgrade(_alembic_config(connection), "head")
    except SQLAlchemyError as exc:
        raise StorageError("Datenbank konnte nicht aktualisiert werden.") from exc


def has_pending_migrations(engine: Engine) -> bool:
    """True if the database is not yet at the latest Alembic revision.

    Used to decide, when the mandatory pre-migration backup fails
    everywhere, whether that is fatal (a migration is about to run
    unprotected) or just a visible warning (nothing is about to change).
    """
    with engine.connect() as connection:
        current_revision = MigrationContext.configure(connection).get_current_revision()
    script_directory = ScriptDirectory.from_config(_alembic_config())
    return current_revision != script_directory.get_current_head()
