from collections.abc import Iterator
from datetime import datetime

import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from klientenverwaltung.models import Base, Client, TreatmentSession, TreatmentType
from klientenverwaltung.repositories import TreatmentSessionRepository


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


def test_get_last_and_next_session_dates_treats_now_as_future(
    db_session: Session,
) -> None:
    client = Client(first_name="Anna", last_name="Muster")
    treatment_type = TreatmentType(name="Chakrenausgleich")
    db_session.add_all([client, treatment_type])
    db_session.flush()

    now = datetime(2026, 6, 15, 12, 0)
    past = TreatmentSession(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 6, 15, 11, 59, 59),
    )
    exactly_now = TreatmentSession(
        client_id=client.id, treatment_type_id=treatment_type.id, date=now
    )
    future = TreatmentSession(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 6, 15, 12, 0, 1),
    )
    db_session.add_all([past, exactly_now, future])
    db_session.commit()

    result = TreatmentSessionRepository(db_session).get_last_and_next_session_dates(
        now=now
    )

    last_date, next_date = result[client.id]
    assert last_date == past.date
    assert next_date == exactly_now.date, (
        "a session at exactly 'now' counts as upcoming"
    )


def test_get_last_and_next_session_dates_none_when_no_sessions(
    db_session: Session,
) -> None:
    client = Client(first_name="Anna", last_name="Muster")
    db_session.add(client)
    db_session.commit()

    result = TreatmentSessionRepository(db_session).get_last_and_next_session_dates(
        [client.id]
    )

    assert result == {}
