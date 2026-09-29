from datetime import date, datetime, timedelta, timezone

import pytest

from klientenverwaltung.models import Client, TreatmentSession, TreatmentType
from klientenverwaltung.services import (
    ClientService,
    NotFoundError,
    TreatmentSessionService,
    ValidationError,
)
from klientenverwaltung.services.client_service import ClientAddressBlock


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
    ("search", "expected_last_names"),
    [
        ("özdemir", ["Özdemir"]),  # lowercase umlaut
        ("ÖZDEMIR", ["Özdemir"]),
        ("ozdemir", ["Özdemir"]),  # typed without the umlaut
        ("über", ["Özdemir"]),  # city "Überlingen"
        ("strasse", ["Muster"]),  # "ß" typed as "ss"
        ("Anna Muster", ["Muster"]),  # first + last name
        ("muster anna", ["Muster"]),  # any order
        ("Anna Özdemir", []),  # every term must match
        ("%", []),  # no SQL wildcard semantics
        ("_", []),
    ],
)
def test_list_clients_with_last_session_search_matches_like_a_person_types(
    client_service: ClientService, search: str, expected_last_names: list[str]
) -> None:
    client_service.create_client(
        first_name="Anna", last_name="Muster", city="Großstraße-Stadt"
    )
    client_service.create_client(
        first_name="Deniz", last_name="Özdemir", city="Überlingen"
    )

    results = client_service.list_clients_with_last_session(search=search)

    assert [entry.last_name for entry in results] == expected_last_names


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
    assert entries[client.id].upcoming_appointments == []
    assert entries[other_client.id].last_session_date is None
    assert entries[other_client.id].upcoming_appointments == []


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
        duration_minutes=45,
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
    upcoming = entries[client.id].upcoming_appointments

    assert entries[client.id].last_session_date == far_past.date
    assert [a.date for a in upcoming] == [near_future.date, far_future.date]
    assert upcoming[0].duration_minutes == 45
    assert upcoming[0].treatment_type_name == treatment_type.name


@pytest.mark.parametrize(
    "birth_date,today,expected_age",
    [
        (date(1980, 3, 15), date(2026, 3, 15), 46),  # exact birthday
        (date(1980, 3, 15), date(2026, 3, 14), 45),  # day before birthday
        (date(1980, 3, 15), date(2026, 3, 16), 46),  # day after birthday
        (date(2026, 1, 1), date(2026, 1, 1), 0),  # born today
    ],
)
def test_compute_age(birth_date: date, today: date, expected_age: int) -> None:
    assert ClientService.compute_age(birth_date, today=today) == expected_age


def test_build_address_block_with_all_fields_set() -> None:
    client = Client(
        salutation="Frau",
        first_name="Erika",
        last_name="Musterfrau",
        street="Hauptstraße 1",
        postal_code="12345",
        city="Musterstadt",
        phone="0123456789",
        email="erika@example.com",
    )
    block = ClientService.build_address_block(client)
    assert block == ClientAddressBlock(
        name_line="Frau Erika Musterfrau",
        lines=["Hauptstraße 1", "12345 Musterstadt"],
        contact_lines=["Telefon: 0123456789", "E-Mail: erika@example.com"],
    )


@pytest.mark.parametrize(
    "overrides,expected_lines,expected_contact_lines",
    [
        ({"street": None}, ["12345 Musterstadt"], ["Telefon: 0123456789"]),
        (
            {"postal_code": None},
            ["Hauptstraße 1", "Musterstadt"],
            ["Telefon: 0123456789"],
        ),
        ({"city": None}, ["Hauptstraße 1", "12345"], ["Telefon: 0123456789"]),
        (
            {"postal_code": None, "city": None},
            ["Hauptstraße 1"],
            ["Telefon: 0123456789"],
        ),
        ({"phone": None}, ["Hauptstraße 1", "12345 Musterstadt"], []),
        ({"phone": None, "email": None}, ["Hauptstraße 1", "12345 Musterstadt"], []),
        (
            {"salutation": None},
            ["Hauptstraße 1", "12345 Musterstadt"],
            ["Telefon: 0123456789"],
        ),
    ],
)
def test_build_address_block_omits_missing_fields(
    overrides: dict[str, str | None],
    expected_lines: list[str],
    expected_contact_lines: list[str],
) -> None:
    fields = {
        "salutation": "Frau",
        "first_name": "Erika",
        "last_name": "Musterfrau",
        "street": "Hauptstraße 1",
        "postal_code": "12345",
        "city": "Musterstadt",
        "phone": "0123456789",
        "email": None,
        **overrides,
    }
    client = Client(**fields)
    block = ClientService.build_address_block(client)
    assert block.lines == expected_lines
    assert block.contact_lines == expected_contact_lines


def test_build_address_block_name_line_omits_missing_salutation() -> None:
    client = Client(salutation=None, first_name="Anna", last_name="Muster")
    block = ClientService.build_address_block(client)
    assert block.name_line == "Anna Muster"


def test_client_since_date_converts_utc_created_at_to_local_calendar_date() -> None:
    # created_at is stored as a naive UTC timestamp (SQLite's
    # CURRENT_TIMESTAMP) - late evening UTC rolls into the next local day
    # for a positive UTC offset.
    created_at_utc = datetime(2026, 1, 15, 23, 30)
    local_tz = timezone(timedelta(hours=2))
    assert ClientService.client_since_date(created_at_utc, local_tz=local_tz) == date(
        2026, 1, 16
    )


def test_client_since_date_keeps_same_local_day_when_no_midnight_crossing() -> None:
    created_at_utc = datetime(2026, 1, 15, 10, 0)
    local_tz = timezone(timedelta(hours=2))
    assert ClientService.client_since_date(created_at_utc, local_tz=local_tz) == date(
        2026, 1, 15
    )


@pytest.mark.parametrize("field", ["birth_date", "consent_date"])
def test_dates_in_the_future_are_rejected(
    client_service: ClientService, field: str
) -> None:
    tomorrow = date.today() + timedelta(days=1)

    with pytest.raises(ValidationError, match="Zukunft"):
        client_service.create_client(
            first_name="Anna", last_name="Muster", **{field: tomorrow}
        )

    client = client_service.create_client(first_name="Anna", last_name="Muster")
    with pytest.raises(ValidationError, match="Zukunft"):
        client_service.update_client(
            client.id, first_name="Anna", last_name="Muster", **{field: tomorrow}
        )
