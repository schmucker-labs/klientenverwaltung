from datetime import datetime

import pytest

from klientenverwaltung.models import Client, TreatmentSession, TreatmentType
from klientenverwaltung.services import NotFoundError, ValidationError
from klientenverwaltung.services.treatment_session_service import (
    TreatmentSessionService,
)
from klientenverwaltung.services.treatment_type_service import TreatmentTypeService


def test_create_session_persists(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    session_entry = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 30),
        duration_minutes=60,
        notes="Erste Sitzung",
    )

    fetched = treatment_session_service.get_session(session_entry.id)
    assert fetched.client_id == client.id
    assert fetched.treatment_type_id == treatment_type.id
    assert fetched.duration_minutes == 60


def test_create_session_unknown_client_raises_not_found(
    treatment_session_service: TreatmentSessionService, treatment_type: TreatmentType
) -> None:
    with pytest.raises(NotFoundError):
        treatment_session_service.create_session(
            client_id=999,
            treatment_type_id=treatment_type.id,
            date=datetime(2026, 3, 1, 9, 30),
        )


def test_create_session_unknown_treatment_type_raises_not_found(
    treatment_session_service: TreatmentSessionService, client: Client
) -> None:
    with pytest.raises(NotFoundError):
        treatment_session_service.create_session(
            client_id=client.id,
            treatment_type_id=999,
            date=datetime(2026, 3, 1, 9, 30),
        )


def test_create_session_rejects_inactive_treatment_type(
    treatment_session_service: TreatmentSessionService,
    treatment_type_service: TreatmentTypeService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    treatment_type_service.deactivate_treatment_type(treatment_type.id)

    with pytest.raises(ValidationError):
        treatment_session_service.create_session(
            client_id=client.id,
            treatment_type_id=treatment_type.id,
            date=datetime(2026, 3, 1, 9, 30),
        )


def test_update_session_changes_fields(
    treatment_session_service: TreatmentSessionService,
    treatment_session: TreatmentSession,
    treatment_type: TreatmentType,
) -> None:
    updated = treatment_session_service.update_session(
        treatment_session.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 4, 1, 8, 0),
        duration_minutes=45,
        notes="Angepasst",
    )

    assert updated.date == datetime(2026, 4, 1, 8, 0)
    assert updated.duration_minutes == 45
    assert updated.notes == "Angepasst"


def test_delete_session(
    treatment_session_service: TreatmentSessionService,
    treatment_session: TreatmentSession,
) -> None:
    treatment_session_service.delete_session(treatment_session.id)

    with pytest.raises(NotFoundError):
        treatment_session_service.get_session(treatment_session.id)


def test_list_sessions_for_client_allows_reading_treatment_type_name_after_close(
    treatment_session_service: TreatmentSessionService,
    treatment_session: TreatmentSession,
    treatment_type: TreatmentType,
) -> None:
    """treatment_type must be eager-loaded, or this raises DetachedInstanceError."""
    sessions = treatment_session_service.list_sessions_for_client(
        treatment_session.client_id
    )

    assert sessions[0].treatment_type.name == treatment_type.name


def test_list_sessions_for_client_orders_newest_first(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    older = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 1, 10, 0),
    )
    newer = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 2, 1, 10, 0),
    )

    sessions = treatment_session_service.list_sessions_for_client(client.id)
    assert [s.id for s in sessions] == [newer.id, older.id]
