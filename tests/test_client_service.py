from datetime import datetime

import pytest

from klientenverwaltung.models import Client, TreatmentSession, TreatmentType
from klientenverwaltung.services import (
    ClientService,
    NotFoundError,
    TreatmentSessionService,
    ValidationError,
)


def test_create_client_persists_and_returns_client(
    client_service: ClientService,
) -> None:
    client = client_service.create_client(
        first_name="Berta", last_name="Beispiel", city="Wien"
    )

    fetched = client_service.get_client(client.id)
    assert fetched.first_name == "Berta"
    assert fetched.last_name == "Beispiel"
    assert fetched.city == "Wien"
    assert fetched.archived is False


@pytest.mark.parametrize(
    "first_name,last_name", [("", "Muster"), ("Anna", "  "), ("", "")]
)
def test_create_client_requires_first_and_last_name(
    client_service: ClientService, first_name: str, last_name: str
) -> None:
    with pytest.raises(ValidationError):
        client_service.create_client(first_name=first_name, last_name=last_name)


def test_get_client_raises_not_found_for_unknown_id(
    client_service: ClientService,
) -> None:
    with pytest.raises(NotFoundError):
        client_service.get_client(999)


def test_list_clients_excludes_archived_by_default(
    client_service: ClientService, client: Client
) -> None:
    client_service.archive_client(client.id)
    client_service.create_client(first_name="Clara", last_name="Neu")

    active_only = client_service.list_clients()
    assert client.id not in [c.id for c in active_only]

    including_archived = client_service.list_clients(include_archived=True)
    assert client.id in [c.id for c in including_archived]


def test_list_clients_filters_by_search_term(client_service: ClientService) -> None:
    client_service.create_client(first_name="Anna", last_name="Muster", city="Graz")
    client_service.create_client(first_name="Berta", last_name="Beispiel", city="Linz")

    results = client_service.list_clients(search="graz")
    assert [c.city for c in results] == ["Graz"]

    results = client_service.list_clients(search="beispiel")
    assert [c.last_name for c in results] == ["Beispiel"]


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("anna", "Anna"),
        ("müller", "Müller"),
        ("MÜLLER", "MÜLLER"),
        ("mcdonald", "Mcdonald"),
        ("anna-maria", "Anna-Maria"),
        ("o'brien", "O'Brien"),
        ("von meyer", "Von Meyer"),
        ("anna von meyer", "Anna von Meyer"),
        ("van der berg", "Van der Berg"),
    ],
)
def test_create_client_normalizes_last_name_casing(
    client_service: ClientService, raw: str, expected: str
) -> None:
    client = client_service.create_client(first_name="Anna", last_name=raw)
    assert client.last_name == expected


def test_create_client_leaves_mixed_case_last_name_untouched(
    client_service: ClientService,
) -> None:
    client = client_service.create_client(first_name="Anna", last_name="McDonald")
    assert client.last_name == "McDonald"


def test_create_client_normalizes_street_but_not_house_number(
    client_service: ClientService,
) -> None:
    client = client_service.create_client(
        first_name="Anna", last_name="Muster", street="hauptstraße 12a"
    )
    assert client.street == "Hauptstraße 12a"


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("herr", "Herr"),
        ("frau", "Frau"),
        ("herr dr.", "Herr Dr."),
        ("frau dr.", "Frau Dr."),
    ],
)
def test_create_client_normalizes_salutation_casing(
    client_service: ClientService, raw: str, expected: str
) -> None:
    client = client_service.create_client(
        first_name="Anna", last_name="Muster", salutation=raw
    )
    assert client.salutation == expected


def test_list_clients_with_last_session_includes_salutation(
    client_service: ClientService,
) -> None:
    client = client_service.create_client(
        first_name="Anna", last_name="Muster", salutation="frau dr."
    )

    entries = {
        entry.id: entry for entry in client_service.list_clients_with_last_session()
    }

    assert entries[client.id].salutation == "Frau Dr."


def test_create_client_normalizes_city_casing(client_service: ClientService) -> None:
    client = client_service.create_client(
        first_name="Anna", last_name="Muster", city="sankt anna am aigen"
    )
    assert client.city == "Sankt Anna Am Aigen"


def test_update_client_normalizes_casing(client_service: ClientService) -> None:
    client = client_service.create_client(first_name="Anna", last_name="Muster")

    updated = client_service.update_client(
        client.id, first_name="anna-lena", last_name="von der leyen"
    )

    assert updated.first_name == "Anna-Lena"
    assert updated.last_name == "Von der Leyen"


def test_update_client_changes_fields(
    client_service: ClientService, client: Client
) -> None:
    updated = client_service.update_client(
        client.id, first_name="Annamarie", last_name=client.last_name, city="Salzburg"
    )

    assert updated.first_name == "Annamarie"
    assert updated.city == "Salzburg"


def test_archive_and_unarchive_client(
    client_service: ClientService, client: Client
) -> None:
    client_service.archive_client(client.id)
    assert client_service.get_client(client.id).archived is True

    client_service.unarchive_client(client.id)
    assert client_service.get_client(client.id).archived is False


def test_delete_client_removes_client_and_cascades_sessions(
    client_service: ClientService,
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_session: TreatmentSession,
) -> None:
    client_service.delete_client(client.id)

    with pytest.raises(NotFoundError):
        client_service.get_client(client.id)

    assert treatment_session_service.list_sessions_for_client(client.id) == []


def test_list_clients_with_last_session_reports_latest_past_date_per_client(
    client_service: ClientService,
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    other_client = client_service.create_client(first_name="Ohne", last_name="Sitzung")
    treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2020, 1, 1, 10, 0),
        duration_minutes=60,
    )
    latest = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2020, 2, 1, 10, 0),
        duration_minutes=60,
    )

    entries = {
        entry.id: entry for entry in client_service.list_clients_with_last_session()
    }

    assert entries[client.id].last_session_date == latest.date
    assert entries[client.id].next_appointment_date is None
    assert entries[other_client.id].last_session_date is None
    assert entries[other_client.id].next_appointment_date is None


def test_list_clients_with_last_session_separates_next_appointment_from_last_session(
    client_service: ClientService,
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    far_past = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2020, 1, 1, 10, 0),
        duration_minutes=60,
    )
    near_future = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2999, 1, 1, 10, 0),
        duration_minutes=60,
    )
    far_future = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2999, 6, 1, 10, 0),
        duration_minutes=60,
    )

    entries = {
        entry.id: entry for entry in client_service.list_clients_with_last_session()
    }

    assert entries[client.id].last_session_date == far_past.date
    assert entries[client.id].next_appointment_date == near_future.date
    assert entries[client.id].next_appointment_date != far_future.date
