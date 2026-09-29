import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import Connection

from alembic import context
from klientenverwaltung.models import Base
from klientenverwaltung.storage import create_encrypted_engine, foreign_keys_disabled

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# alembic.ini's logging setup is for manual `alembic` CLI runs only. Inside
# the application (which passes its open connection) it must not run: it
# would disable every logger the app already created and install its own
# stderr handler - on every single start.
if config.config_file_name is not None and "connection" not in config.attributes:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _dev_db_path_and_password() -> tuple[Path, str]:
    """Read connection details for standalone CLI use (e.g. --autogenerate).

    alembic.ini deliberately has no sqlalchemy.url: the real application
    passes an already-open, encrypted connection via config.attributes at
    startup (see main.py), since path and password are only known once the
    USB-Datenplatte was found and the user entered the password. For manual
    `alembic` CLI invocations during development, these two environment
    variables stand in for that.
    """
    path = os.environ.get("KLIENTENVERWALTUNG_DB_PATH")
    password = os.environ.get("KLIENTENVERWALTUNG_DB_PASSWORD")
    if not path or not password:
        raise RuntimeError(
            "Keine offene Verbindung übergeben und "
            "KLIENTENVERWALTUNG_DB_PATH / KLIENTENVERWALTUNG_DB_PASSWORD sind "
            "nicht gesetzt. Für manuelle alembic-Aufrufe (z. B. "
            "--autogenerate) beide Umgebungsvariablen setzen."
        )
    return Path(path), password


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script generation)."""
    db_path, password = _dev_db_path_and_password()
    engine = create_encrypted_engine(db_path, password)
    context.configure(
        url=engine.url.render_as_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode against a real connection."""
    connection = config.attributes.get("connection")

    if connection is not None:
        # Provided by the application at startup: an already-open,
        # encrypted connection to the database on the USB-Datenplatte.
        _run_with_foreign_keys_disabled(connection)
        return

    db_path, password = _dev_db_path_and_password()
    connectable = create_encrypted_engine(db_path, password)
    with connectable.connect() as dev_connection:
        _run_with_foreign_keys_disabled(dev_connection)


def _run_with_foreign_keys_disabled(connection: Connection) -> None:
    # Never run a migration with foreign keys enforced: batch mode's
    # DROP TABLE would cascade into every child table (see
    # storage.foreign_keys_disabled).
    with foreign_keys_disabled(connection):
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
