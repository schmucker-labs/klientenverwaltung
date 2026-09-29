import shutil
from datetime import datetime
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from klientenverwaltung import storage
from klientenverwaltung.models import (
    Base,
    Client,
    Media,
    SessionMedia,
    TreatmentSession,
    TreatmentType,
)

_PASSWORD = "ein-sehr-sicheres-passwort"

_REBUILD_REVISION = '''\
"""test only: rebuild client and session the way SQLite batch mode does"""

from alembic import op

revision = "fffffffffff0"
down_revision = "{down_revision}"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("client", recreate="always"):
        pass
    with op.batch_alter_table("session", recreate="always"):
        pass


def downgrade() -> None:
    pass
'''


@pytest.fixture(autouse=True)
def _isolated_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))


def _set_up_drive(tmp_path: Path) -> tuple[Path, Engine]:
    drive = tmp_path / "drive"
    drive.mkdir()
    return drive, storage.set_up_data_drive(drive, _PASSWORD)


def test_migrations_produce_exactly_the_schema_of_the_models(tmp_path: Path) -> None:
    """A model change without a matching migration would otherwise only
    surface on the user's machine - the other tests build their schema
    with Base.metadata.create_all(), not through Alembic."""
    _drive, engine = _set_up_drive(tmp_path)
    try:
        with engine.connect() as connection:
            differences = compare_metadata(
                MigrationContext.configure(connection), Base.metadata
            )
        assert differences == []
    finally:
        engine.dispose()


def test_table_rebuild_during_a_migration_keeps_dependent_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SQLite batch migrations rebuild a table via DROP TABLE, which - with
    foreign keys enforced - cascades into every child table. Rebuilding
    client must not delete sessions, rebuilding session must not delete
    media links."""
    _drive, engine = _set_up_drive(tmp_path)
    try:
        with Session(engine) as session:
            client = Client(first_name="Anna", last_name="Muster")
            treatment_type = TreatmentType(name="Meditation")
            session.add_all([client, treatment_type])
            session.flush()
            treatment_session = TreatmentSession(
                client_id=client.id,
                treatment_type_id=treatment_type.id,
                date=datetime(2026, 1, 15, 10, 0),
                duration_minutes=60,
            )
            media = Media(
                stored_filename="a.jpg",
                original_filename="a.jpg",
                media_kind="image",
                size_bytes=1,
                sha256="0" * 64,
            )
            session.add_all([treatment_session, media])
            session.flush()
            session.add(SessionMedia(session_id=treatment_session.id, media_id=media.id))
            session.commit()

        bundle_copy = tmp_path / "bundle"
        shutil.copytree(
            storage._bundle_root() / "alembic",
            bundle_copy / "alembic",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        shutil.copy(storage._bundle_root() / "alembic.ini", bundle_copy)
        head = ScriptDirectory.from_config(storage._alembic_config()).get_current_head()
        (bundle_copy / "alembic" / "versions" / "fffffffffff0_rebuild.py").write_text(
            _REBUILD_REVISION.format(down_revision=head), encoding="utf-8"
        )
        monkeypatch.setattr(storage, "_bundle_root", lambda: bundle_copy)

        storage.apply_migrations(engine)

        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(Client)) == 1
            assert session.scalar(select(func.count()).select_from(TreatmentSession)) == 1
            assert session.scalar(select(func.count()).select_from(SessionMedia)) == 1
    finally:
        engine.dispose()


def test_existing_session_times_are_truncated_to_whole_minutes(tmp_path: Path) -> None:
    from alembic import command

    drive = tmp_path / "drive"
    drive.mkdir()
    engine = storage.create_encrypted_engine(drive / storage.DB_FILENAME, _PASSWORD)
    try:
        with engine.connect() as connection:
            command.upgrade(storage._alembic_config(connection), "c66a9fbe6d01")
        with Session(engine) as session:
            client = Client(first_name="Anna", last_name="Muster")
            treatment_type = TreatmentType(name="Meditation")
            session.add_all([client, treatment_type])
            session.flush()
            session.add(
                TreatmentSession(
                    client_id=client.id,
                    treatment_type_id=treatment_type.id,
                    date=datetime(2026, 3, 1, 14, 0, 47, 123000),
                    duration_minutes=60,
                )
            )
            session.commit()

        storage.apply_migrations(engine)

        with Session(engine) as session:
            stored = session.scalars(select(TreatmentSession.date)).one()
        assert stored == datetime(2026, 3, 1, 14, 0)
    finally:
        engine.dispose()


def test_foreign_keys_are_enforced_again_after_migrations(tmp_path: Path) -> None:
    _drive, engine = _set_up_drive(tmp_path)
    try:
        storage.apply_migrations(engine)
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    finally:
        engine.dispose()
