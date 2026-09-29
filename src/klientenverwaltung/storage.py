import ctypes
import string
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

# SQLAlchemy resolves the "pysqlcipher" dialect by string name at runtime, so
# it must be imported explicitly here to end up in a PyInstaller-frozen build.
import sqlalchemy.dialects.sqlite.pysqlcipher  # noqa: F401
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.script.revision import RevisionError
from alembic.util import CommandError
from sqlalchemy import URL, Connection, Engine, create_engine, event
from sqlalchemy.engine import ExceptionContext
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


class DifferentDataDriveError(StorageError):
    """Exactly one data drive was found, but not the one this laptop
    recorded - e.g. a second, separately set-up data drive."""

    def __init__(self, message: str, drive_root: Path) -> None:
        super().__init__(message)
        self.drive_root = drive_root


class IncorrectPasswordError(StorageError):
    """The given password does not decrypt the database."""


class WeakPasswordError(StorageError):
    """The given password is shorter than MIN_PASSWORD_LENGTH."""


def create_encrypted_engine(db_path: Path, password: str) -> Engine:
    """An engine for the SQLCipher database at db_path, keyed with password.

    The URL is built with URL.create() rather than as a string: a string
    URL is parsed by SQLAlchemy, which cuts the password off at the first
    "@" and percent-decodes "%XX" sequences - so a perfectly valid password
    would either crash engine creation or silently become a different key.

    hide_parameters keeps bound SQL parameters (client data) out of every
    exception message, which may otherwise end up in the crash log on the
    laptop.
    """
    url = URL.create(
        "sqlite+pysqlcipher", password=password, database=db_path.as_posix()
    )
    engine = create_engine(url, hide_parameters=True)

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


def _call_for_each_within[T](
    func: Callable[[Path], T], roots: Sequence[Path], timeout: float
) -> dict[Path, T]:
    """Calls func(root) for every root concurrently and returns the results
    that arrived within timeout seconds; a root whose call is still running
    then (an offline network drive can hang for 20-60 s), or that raised,
    is simply absent from the result.

    Each call runs on its own daemon thread that is never waited for past
    the deadline. A ThreadPoolExecutor cannot do this: leaving its `with`
    block (or interpreter exit) joins every worker, so one hung drive
    would still block the caller - and the GUI thread with it - until the
    read finally gave up.
    """
    results: dict[Path, T] = {}
    lock = threading.Lock()

    def _run(root: Path) -> None:
        try:
            value = func(root)
        except Exception:  # noqa: BLE001 - an unreadable drive is just skipped
            return
        with lock:
            results[root] = value

    threads = [
        threading.Thread(target=_run, args=(root,), daemon=True, name=f"probe {root}")
        for root in roots
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))
    with lock:
        return dict(results)


def _identifiers_of(
    roots: Sequence[Path],
    *,
    reader: Callable[[Path], str | None],
    timeout: float,
) -> dict[Path, str]:
    """root -> identifier for every root whose identifier file could be read
    in time, in the roots' given order."""
    contents = _call_for_each_within(reader, roots, timeout)
    return {
        root: identifier
        for root in roots
        if (identifier := contents.get(root)) is not None
    }


def _find_data_drive_among(
    candidate_roots: Sequence[Path],
    *,
    last_known_path: Path | None,
    expected_id: str | None = None,
    reader: Callable[[Path], str | None] = _read_identifier_file,
    timeout: float = DRIVE_CHECK_TIMEOUT_SECONDS,
) -> Path:
    """Core, dependency-injected drive search: checks last_known_path first, then all candidates.

    expected_id is the identifier of the data drive this laptop worked
    with so far (None if none was recorded yet). A drive carrying it wins
    over other data drives; a single drive carrying a different one raises
    DifferentDataDriveError so the user decides. (A 1:1 clone of the drive
    carries the same identifier - two of those remain "multiple drives".)

    Kept separate from find_data_drive() so tests can exercise it against
    temporary directories standing in for drives, and inject a slow reader to
    verify that an unresponsive drive is skipped rather than blocking the
    whole search.
    """
    if last_known_path is not None:
        last_known = _identifiers_of([last_known_path], reader=reader, timeout=timeout)
        if last_known and expected_id in (None, last_known[last_known_path]):
            return last_known_path

    found = _identifiers_of(candidate_roots, reader=reader, timeout=timeout)
    if expected_id is not None:
        matching = [
            root for root, identifier in found.items() if identifier == expected_id
        ]
        if len(matching) == 1:
            return matching[0]
    candidates = list(found)

    if not candidates:
        raise DataDriveNotFoundError(
            "Datenplatte wurde nicht gefunden. Bitte Datenplatte anschließen und "
            "erneut versuchen."
        )
    if len(candidates) > 1:
        joined = ", ".join(str(path) for path in candidates)
        raise MultipleDataDrivesFoundError(
            f"Es wurden mehrere Laufwerke mit einer Kennungsdatei gefunden: {joined}. "
            "Bitte nur die richtige Datenplatte anschließen.",
            candidates,
        )
    if expected_id is not None:
        raise DifferentDataDriveError(
            f"Auf dem Laufwerk {candidates[0]} wurde eine andere Datenplatte gefunden "
            "als die, mit der auf diesem Computer bisher gearbeitet wurde. Nur "
            "fortfahren, wenn Sie bewusst mit dieser Platte weiterarbeiten wollen.",
            candidates[0],
        )
    return candidates[0]


def _drive_roots() -> list[Path]:
    return [Path(f"{letter}:\\") for letter in _assigned_drive_letters()]


def find_data_drive() -> Path:
    """Finds the real data drive among currently assigned Windows drive letters."""
    found = _find_data_drive_among(
        _drive_roots(),
        last_known_path=config.get_last_known_drive_path(),
        expected_id=config.get_data_drive_id(),
    )
    _remember_data_drive(found)
    return found


def accept_data_drive(drive_root: Path) -> None:
    """Records drive_root as this laptop's data drive from now on - after
    the user confirmed working with a different one."""
    _remember_data_drive(drive_root)


def _remember_data_drive(drive_root: Path) -> None:
    identifier = _read_identifier_file(drive_root)
    try:
        config.set_last_known_drive_path(drive_root)
        if identifier is not None:
            config.set_data_drive_id(identifier)
    except OSError:
        pass  # only a search shortcut / safety check for the next start


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
    reach callers unexplained.

    Also registers a handler that reports a mid-operation loss of the drive
    as a disconnect: the resulting DBAPIError carries
    connection_invalidated=True (which the service layer turns into a
    German DataUnavailableError), and the pool drops its dead connections -
    once the drive is plugged back in under the same letter, the next
    operation simply works again, no restart needed.
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
        raise StorageError("Datenbank konnte nicht geöffnet werden.") from exc

    @event.listens_for(engine, "handle_error")
    def _report_vanished_drive_as_disconnect(context: ExceptionContext) -> None:
        if not db_path.exists():
            context.is_disconnect = True

    return engine


def set_up_data_drive(drive_root: Path, password: str) -> Engine:
    """Einrichtungsfunktion: encrypted DB (via Alembic), then identifier file.

    The identifier file is written last, only once the database is fully
    migrated - a drive only counts as set up (and is only ever found by
    find_data_drive()) when everything on it is complete. Any failure,
    whatever its type, removes what this call created, so the drive looks
    exactly as if setup never ran and can simply be set up again.

    A drive carrying an identifier file but no database is the leftover of
    an interrupted setup (by an older version, or a crash/power loss right
    in between): it is completed here, not refused. A drive that already
    holds a database is always refused - never overwrite data.

    No treatment types are created here - the user creates their own,
    per Auftrag D1 ("Keine Standard-Behandlungsarten mehr").
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Das Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein."
        )

    identifier_path = drive_root / IDENTIFIER_FILENAME
    db_path = drive_root / DB_FILENAME
    if db_path.exists():
        raise StorageError(
            f"Auf diesem Laufwerk existiert bereits eine Datenbankdatei: {db_path}"
        )

    engine = create_encrypted_engine(db_path, password)
    try:
        apply_migrations(engine)
        identifier_path.write_text(str(uuid.uuid4()), encoding="utf-8")
    except BaseException as exc:
        engine.dispose()
        db_path.unlink(missing_ok=True)
        db_path.with_name(db_path.name + "-journal").unlink(missing_ok=True)
        # identifier_path is written last, so if we got here it is either
        # untouched (a leftover from an interrupted setup, kept as it was)
        # or absent - never half-written by this call.
        if isinstance(exc, OSError):
            raise StorageError(
                f"Auf dem Laufwerk {drive_root} kann nicht geschrieben werden."
            ) from exc
        raise

    # A newly set-up drive is deliberately this laptop's data drive now.
    _remember_data_drive(drive_root)
    return engine


def list_available_drives() -> list[Path]:
    """Currently assigned Windows drive letters, as candidate roots to set up."""
    return _drive_roots()


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


class DriveSetupState(StrEnum):
    FREE = "free"
    """Neither identifier file nor database - can be set up."""
    INCOMPLETE = "incomplete"
    """Identifier file but no database: an interrupted setup, completable."""
    SET_UP = "set_up"
    """A complete data drive."""
    FOREIGN_DATABASE = "foreign_database"
    """A database file without identifier file - never overwritten."""


def drive_setup_state(drive_root: Path) -> DriveSetupState:
    has_identifier = _read_identifier_file(drive_root) is not None
    has_database = (drive_root / DB_FILENAME).exists()
    if has_identifier and has_database:
        return DriveSetupState.SET_UP
    if has_identifier:
        return DriveSetupState.INCOMPLETE
    if has_database:
        return DriveSetupState.FOREIGN_DATABASE
    return DriveSetupState.FREE


def drive_already_set_up(drive_root: Path) -> bool:
    """True if drive_root carries a valid Kennungsdatei *and* a database."""
    return drive_setup_state(drive_root) is DriveSetupState.SET_UP


@dataclass(frozen=True)
class DriveInfo:
    """What the setup wizard shows about one drive letter."""

    root: Path
    description: str
    setup_state: DriveSetupState | None
    """None if the drive did not answer in time (e.g. an offline network drive)."""
    removable: bool


def inspect_drives(
    drives: Sequence[Path], timeout: float = DRIVE_CHECK_TIMEOUT_SECONDS
) -> list[DriveInfo]:
    """Label, setup state and media type of every drive, probed all at once
    and bounded by timeout - one unresponsive drive must not freeze the
    setup wizard."""

    def _probe(root: Path) -> tuple[str, DriveSetupState, bool]:
        return describe_drive(root), drive_setup_state(root), is_removable_drive(root)

    probed = _call_for_each_within(_probe, drives, timeout)
    infos: list[DriveInfo] = []
    for root in drives:
        if root in probed:
            description, setup_state, removable = probed[root]
            infos.append(DriveInfo(root, description, setup_state, removable))
        else:
            infos.append(DriveInfo(root, f"{root} (reagiert nicht)", None, False))
    return infos


@contextmanager
def foreign_keys_disabled(connection: Connection) -> Iterator[None]:
    """Runs a migration with SQLite's foreign key enforcement switched off.

    SQLite cannot alter most column/constraint definitions in place, so
    Alembic's batch mode rebuilds the table: copy into a new table, DROP the
    old one, rename. With foreign keys enforced, that DROP TABLE is an
    implicit DELETE that fires ON DELETE CASCADE - rebuilding `client` would
    silently delete every session, rebuilding `session` every media link.
    SQLite's own documented procedure for such schema changes is to turn
    enforcement off for the duration and verify integrity afterwards with
    PRAGMA foreign_key_check, which is exactly what this does.

    PRAGMA foreign_keys is a no-op inside an open transaction, hence the
    commits around it (the driver never has a real BEGIN pending here).
    """
    connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
    connection.commit()
    try:
        yield
        if connection.in_transaction():
            connection.commit()
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        connection.commit()
        if violations:
            raise StorageError(
                "Nach der Datenbank-Aktualisierung passen gespeicherte Verknüpfungen "
                "nicht mehr zusammen. Bitte die Sicherung von vor der Aktualisierung "
                "wiederherstellen."
            )
    finally:
        if connection.in_transaction():
            connection.rollback()
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
        connection.commit()


def _require_known_schema(connection: Connection) -> None:
    """Raises StorageError if the database carries a schema revision this
    program version does not know - it was migrated by a newer version
    (an older .exe still in use, or a backup made by a newer version)."""
    current_revision = MigrationContext.configure(connection).get_current_revision()
    if current_revision is None:
        return
    script_directory = ScriptDirectory.from_config(_alembic_config())
    known_revisions = {script.revision for script in script_directory.walk_revisions()}
    if current_revision not in known_revisions:
        raise StorageError(
            "Diese Daten wurden mit einer neueren Version der Klientenverwaltung "
            "bearbeitet und können mit dieser Version nicht geöffnet werden. Bitte "
            "die neueste Version des Programms verwenden."
        )


def apply_migrations(engine: Engine) -> None:
    """Applies pending Alembic migrations against an already-open, encrypted engine.

    Called both by set_up_data_drive() and on every normal startup, per
    "Migrationen werden beim Programmstart automatisch angewendet".
    """
    try:
        with engine.connect() as connection:
            _require_known_schema(connection)
            connection.rollback()  # end the read before migrations begin
            command.upgrade(_alembic_config(connection), "head")
    except (SQLAlchemyError, CommandError, RevisionError) as exc:
        raise StorageError("Datenbank konnte nicht aktualisiert werden.") from exc


def verify_database_file(db_path: Path, password: str) -> None:
    """Checks - without changing it - that db_path is an intact database
    this program version can open with password.

    Raises IncorrectPasswordError if it cannot be decrypted (wrong password
    or no database at all - SQLCipher cannot tell the two apart), and
    StorageError if it is damaged or comes from a newer program version.
    Used before a backup is restored over the live database.
    """
    if not db_path.exists():
        raise StorageError(f"Die Datei wurde nicht gefunden: {db_path}")
    engine = create_encrypted_engine(db_path, password)
    try:
        # A wrong key already fails while connecting (the connect-time
        # pragmas are the first statements to touch the file).
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT count(*) FROM sqlite_master")
            if connection.exec_driver_sql("PRAGMA quick_check").scalar() != "ok":
                raise StorageError("Die Datei ist beschädigt.")
            _require_known_schema(connection)
    except DatabaseError as exc:
        raise IncorrectPasswordError(
            "Die Datei lässt sich mit diesem Passwort nicht öffnen (falsches "
            "Passwort oder keine gültige Sicherung)."
        ) from exc
    except SQLAlchemyError as exc:
        raise StorageError("Die Datei konnte nicht geprüft werden.") from exc
    finally:
        engine.dispose()


def rekey_database_file(db_path: Path, old_password: str, new_password: str) -> None:
    """Re-encrypts the database file at db_path from old_password to
    new_password (SQLCipher's PRAGMA rekey). The file must not be open
    anywhere else - callers dispose their engine first.

    Raises IncorrectPasswordError if old_password does not open it (then
    nothing is changed) and WeakPasswordError for a too-short new_password.
    """
    if len(new_password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Das Passwort muss mindestens {MIN_PASSWORD_LENGTH} Zeichen lang sein."
        )
    verify_database_file(db_path, old_password)
    engine = create_encrypted_engine(db_path, old_password)
    try:
        with engine.connect() as connection:
            # Quoted exactly like SQLAlchemy quotes the key itself, so any
            # character - including quotes - is taken literally.
            quoted = connection.dialect.identifier_preparer.quote_identifier(
                new_password
            )
            connection.exec_driver_sql(f"PRAGMA rekey = {quoted}")
    except SQLAlchemyError as exc:
        raise StorageError("Das Passwort konnte nicht geändert werden.") from exc
    finally:
        engine.dispose()
    verify_database_file(db_path, new_password)


def has_pending_migrations(engine: Engine) -> bool:
    """True if the database is not yet at the latest Alembic revision.

    Used to decide, when the mandatory pre-migration backup fails
    everywhere, whether that is fatal (a migration is about to run
    unprotected) or just a visible warning (nothing is about to change).
    """
    try:
        with engine.connect() as connection:
            current_revision = MigrationContext.configure(
                connection
            ).get_current_revision()
    except SQLAlchemyError as exc:
        raise StorageError("Datenbank konnte nicht gelesen werden.") from exc
    script_directory = ScriptDirectory.from_config(_alembic_config())
    return current_revision != script_directory.get_current_head()
