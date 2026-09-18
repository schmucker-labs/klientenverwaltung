from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from klientenverwaltung.models import Base, Client, TreatmentSession, TreatmentType


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def _make_client_with_session(
    db_session: Session,
) -> tuple[Client, TreatmentType, TreatmentSession]:
    client = Client(first_name="Anna", last_name="Muster")
    treatment_type = TreatmentType(name="Chakrenausgleich")
    db_session.add_all([client, treatment_type])
    db_session.flush()

    session_entry = TreatmentSession(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime.now(UTC),
    )
    db_session.add(session_entry)
    db_session.commit()
    return client, treatment_type, session_entry


def test_deleting_client_cascades_to_sessions(db_session: Session) -> None:
    client, _treatment_type, session_entry = _make_client_with_session(db_session)
    session_id = session_entry.id

    db_session.delete(client)
    db_session.commit()

    assert db_session.get(TreatmentSession, session_id) is None


def test_deleting_used_treatment_type_is_restricted(db_session: Session) -> None:
    _client, treatment_type, _session_entry = _make_client_with_session(db_session)
    treatment_type_id = treatment_type.id

    db_session.delete(treatment_type)
    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()
    assert db_session.get(TreatmentType, treatment_type_id) is not None
