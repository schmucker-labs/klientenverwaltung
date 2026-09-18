"""Risk prototype: SQLCipher + SQLAlchemy, buildable as a standalone Windows .exe.

Verifies the riskiest technical assumption before any further work on the
real application: that an SQLCipher-encrypted SQLite database can be created,
written to, and read back through SQLAlchemy, and that the resulting script
still works once frozen with PyInstaller.

Run directly with `uv run python prototype/risk_prototype.py`, or after
`pyinstaller --onefile --name risk_prototype prototype/risk_prototype.py`,
run `dist/risk_prototype.exe`.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# PyInstaller cannot see this import: SQLAlchemy resolves the "pysqlcipher"
# dialect by string name at runtime, so the module must be imported explicitly
# here to end up in the frozen executable.
import sqlalchemy.dialects.sqlite.pysqlcipher  # noqa: F401
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

PASSPHRASE = "correct-horse-battery-staple"
WRONG_PASSPHRASE = "wrong-passphrase"


class Base(DeclarativeBase):
    pass


class Note(Base):
    __tablename__ = "note"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str]


def make_engine(db_path: Path, passphrase: str) -> Engine:
    url = f"sqlite+pysqlcipher://:{passphrase}@/{db_path.as_posix()}"
    engine = create_engine(url)

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA synchronous = FULL")
        cursor.close()

    return engine


def write_and_read_back(db_path: Path) -> None:
    engine = make_engine(db_path, PASSPHRASE)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(Note(content="hallo aus dem risiko-prototyp"))
        session.commit()

    engine.dispose()

    engine = make_engine(db_path, PASSPHRASE)
    with Session(engine) as session:
        note = session.query(Note).one()
        assert note.content == "hallo aus dem risiko-prototyp", note.content
    engine.dispose()
    print("OK: Schreiben und Lesen mit korrektem Passwort erfolgreich.")


def verify_file_is_encrypted(db_path: Path) -> None:
    raw = db_path.read_bytes()
    assert b"hallo aus dem risiko-prototyp" not in raw
    assert not raw.startswith(b"SQLite format 3")
    print(
        "OK: Datei auf der Platte ist verschluesselt (kein Klartext, kein SQLite-Header)."
    )


def verify_wrong_passphrase_fails(db_path: Path) -> None:
    engine = make_engine(db_path, WRONG_PASSPHRASE)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT COUNT(*) FROM note"))
    except SQLAlchemyError:
        print("OK: Falsches Passwort wird abgelehnt.")
    else:
        raise AssertionError("Falsches Passwort haette fehlschlagen muessen.")
    finally:
        engine.dispose()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "risk_prototype.db"
        write_and_read_back(db_path)
        verify_file_is_encrypted(db_path)
        verify_wrong_passphrase_fails(db_path)
    print("Alle Pruefungen erfolgreich.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
