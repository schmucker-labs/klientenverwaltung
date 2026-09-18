from datetime import datetime

import pytest

from klientenverwaltung.models import Client, TreatmentSession, TreatmentType
from klientenverwaltung.services import (
    NotFoundError,
    SessionOverlapError,
    ValidationError,
)
from klientenverwaltung.services.client_service import ClientService
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
            duration_minutes=60,
        )


def test_create_session_unknown_treatment_type_raises_not_found(
    treatment_session_service: TreatmentSessionService, client: Client
) -> None:
    with pytest.raises(NotFoundError):
        treatment_session_service.create_session(
            client_id=client.id,
            treatment_type_id=999,
            date=datetime(2026, 3, 1, 9, 30),
            duration_minutes=60,
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
            duration_minutes=60,
        )


@pytest.mark.parametrize("duration_minutes", [0, -15])
def test_create_session_rejects_non_positive_duration(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
    duration_minutes: int,
) -> None:
    with pytest.raises(ValidationError):
        treatment_session_service.create_session(
            client_id=client.id,
            treatment_type_id=treatment_type.id,
            date=datetime(2026, 3, 1, 9, 30),
            duration_minutes=duration_minutes,
        )


def test_create_session_rejects_overlap_with_existing_session(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=60,
    )

    with pytest.raises(SessionOverlapError, match="09:00"):
        treatment_session_service.create_session(
            client_id=client.id,
            treatment_type_id=treatment_type.id,
            date=datetime(2026, 3, 1, 9, 30),
            duration_minutes=30,
        )


def test_create_session_overlap_check_is_practitioner_wide(
    treatment_session_service: TreatmentSessionService,
    client_service: ClientService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    """One practitioner cannot hold two sessions at once, even for different clients."""
    other_client = client_service.create_client(first_name="Otto", last_name="Fremd")
    treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=60,
    )

    with pytest.raises(
        SessionOverlapError, match=f"{client.first_name} {client.last_name}"
    ):
        treatment_session_service.create_session(
            client_id=other_client.id,
            treatment_type_id=treatment_type.id,
            date=datetime(2026, 3, 1, 9, 30),
            duration_minutes=30,
        )


def test_create_session_allows_back_to_back_appointments(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=60,
    )

    directly_after = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 10, 0),
        duration_minutes=30,
    )

    assert directly_after.duration_minutes == 30


def test_update_session_does_not_flag_overlap_with_itself(
    treatment_session_service: TreatmentSessionService,
    treatment_session: TreatmentSession,
    treatment_type: TreatmentType,
) -> None:
    updated = treatment_session_service.update_session(
        treatment_session.id,
        treatment_type_id=treatment_type.id,
        date=treatment_session.date,
        duration_minutes=90,
        notes="Verlängert",
    )

    assert updated.duration_minutes == 90


def test_update_session_rejects_overlap_with_other_session(
    treatment_session_service: TreatmentSessionService,
    treatment_session: TreatmentSession,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    """treatment_session runs 2026-01-15 10:00-11:00 (see conftest)."""
    other = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 15, 12, 0),
        duration_minutes=60,
    )

    with pytest.raises(SessionOverlapError):
        treatment_session_service.update_session(
            other.id,
            treatment_type_id=treatment_type.id,
            date=datetime(2026, 1, 15, 10, 30),
            duration_minutes=60,
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
        duration_minutes=60,
    )
    newer = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 2, 1, 10, 0),
        duration_minutes=60,
    )

    sessions = treatment_session_service.list_sessions_for_client(client.id)
    assert [s.id for s in sessions] == [newer.id, older.id]
