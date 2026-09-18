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


def test_get_last_session_dates_excludes_sessions_at_or_after_now(
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
        duration_minutes=60,
    )
    exactly_now = TreatmentSession(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=now,
        duration_minutes=60,
    )
    db_session.add_all([past, exactly_now])
    db_session.commit()

    result = TreatmentSessionRepository(db_session).get_last_session_dates(now=now)

    assert result[client.id] == past.date, "a session at exactly 'now' is not past"


def test_get_last_session_dates_absent_when_no_past_sessions(
    db_session: Session,
) -> None:
    client = Client(first_name="Anna", last_name="Muster")
    db_session.add(client)
    db_session.commit()

    result = TreatmentSessionRepository(db_session).get_last_session_dates([client.id])

    assert result == {}


def test_get_upcoming_sessions_includes_session_at_exactly_now_soonest_first(
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
        duration_minutes=60,
    )
    exactly_now = TreatmentSession(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=now,
        duration_minutes=60,
    )
    later = TreatmentSession(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 6, 20, 9, 0),
        duration_minutes=30,
    )
    db_session.add_all([past, exactly_now, later])
    db_session.commit()

    result = TreatmentSessionRepository(db_session).get_upcoming_sessions(now=now)

    assert [s.id for s in result[client.id]] == [exactly_now.id, later.id]


def test_get_upcoming_sessions_absent_when_no_future_sessions(
    db_session: Session,
) -> None:
    client = Client(first_name="Anna", last_name="Muster")
    db_session.add(client)
    db_session.commit()

    result = TreatmentSessionRepository(db_session).get_upcoming_sessions([client.id])

    assert result == {}
