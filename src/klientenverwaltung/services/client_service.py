from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, tzinfo

from sqlalchemy.orm import Session, sessionmaker

from klientenverwaltung.models import Client
from klientenverwaltung.repositories import ClientRepository, TreatmentSessionRepository
from klientenverwaltung.services.errors import NotFoundError, ValidationError
from klientenverwaltung.services.search import matches, search_terms
from klientenverwaltung.services.transaction import database_errors_as, transaction

_LOAD_ERROR = "Die Klientendaten konnten nicht geladen werden."

# German nobiliary/prefix particles: stay lowercase unless they open the field
# (e.g. "anna von meyer" -> "Anna von Meyer", but "von meyer" -> "Von Meyer").
_NAME_PARTICLES = frozenset({"von", "van", "de", "der", "zu", "den", "del", "di"})
_WORD_PART_SPLIT_RE = re.compile(r"([-'])")


def _normalize_casing(text: str) -> str:
    """Title-case words that are entirely lowercase; leave everything else alone.

    Mixed-case input (e.g. "McDonald") and tokens with no letters (e.g. a
    house number) are left untouched. Hyphen- and apostrophe-joined parts of
    a word (e.g. "anna-maria", "o'brien") are capitalized individually.
    """
    words = text.split(" ")
    return " ".join(
        _normalize_word(word, is_first=index == 0) for index, word in enumerate(words)
    )


def _normalize_word(word: str, *, is_first: bool) -> str:
    if not word.islower():
        return word
    if word in _NAME_PARTICLES and not is_first:
        return word
    return "".join(
        part if part in ("-", "'") else part.capitalize()
        for part in _WORD_PART_SPLIT_RE.split(word)
    )


def _filter_by_search(clients: list[Client], search: str | None) -> list[Client]:
    """Clients matching the search box: name or city, see services.search."""
    terms = search_terms(search)
    if not terms:
        return clients
    return [
        client
        for client in clients
        if matches(terms, client.first_name, client.last_name, client.city)
    ]


@dataclass(frozen=True)
class UpcomingAppointment:
    """One future session, as needed to display it in the client list."""

    date: datetime
    duration_minutes: int
    treatment_type_name: str


@dataclass(frozen=True)
class ClientAddressBlock:
    """The Klientenübersicht's letter-style address block (Auftrag B1).

    name_line is always present (first/last name are mandatory); lines and
    contact_lines contain only the address/contact lines the client
    actually has, in display order, so the dialog can render exactly what
    exists with no empty-field placeholders.
    """

    name_line: str
    lines: list[str]
    contact_lines: list[str]


@dataclass(frozen=True)
class ClientListEntry:
    """One row of the client list: exactly the fields that screen shows."""

    id: int
    salutation: str | None
    first_name: str
    last_name: str
    city: str | None
    phone: str | None
    archived: bool
    last_session_date: datetime | None
    upcoming_appointments: list[UpcomingAppointment]


class ClientService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    @database_errors_as("Klient konnte nicht gespeichert werden.")
    def create_client(
        self,
        *,
        first_name: str,
        last_name: str,
        salutation: str | None = None,
        birth_date: date | None = None,
        street: str | None = None,
        postal_code: str | None = None,
        city: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        concern: str | None = None,
        referral_source: str | None = None,
        consent_date: date | None = None,
        notes: str | None = None,
    ) -> Client:
        first_name, last_name = self._validate_name(first_name, last_name)
        salutation = self._normalize_optional(salutation)
        street = self._normalize_optional(street)
        city = self._normalize_optional(city)
        client = Client(
            first_name=first_name,
            last_name=last_name,
            salutation=salutation,
            birth_date=birth_date,
            street=street,
            postal_code=postal_code,
            city=city,
            phone=phone,
            email=email,
            concern=concern,
            referral_source=referral_source,
            consent_date=consent_date,
            notes=notes,
        )
        with (
            self._session_factory() as session,
            transaction(session, "Klient konnte nicht gespeichert werden."),
        ):
            ClientRepository(session).add(client)
        return client

    @database_errors_as(_LOAD_ERROR)
    def get_client(self, client_id: int) -> Client:
        with self._session_factory() as session:
            client = ClientRepository(session).get_by_id(client_id)
        if client is None:
            raise NotFoundError(f"Klient mit ID {client_id} wurde nicht gefunden.")
        return client

    @database_errors_as(_LOAD_ERROR)
    def list_clients(
        self, *, include_archived: bool = False, search: str | None = None
    ) -> list[Client]:
        with self._session_factory() as session:
            clients = ClientRepository(session).list(include_archived=include_archived)
        return _filter_by_search(clients, search)

    @database_errors_as(_LOAD_ERROR)
    def list_clients_with_last_session(
        self, *, include_archived: bool = False, search: str | None = None
    ) -> list[ClientListEntry]:
        with self._session_factory() as session:
            clients = _filter_by_search(
                ClientRepository(session).list(include_archived=include_archived),
                search,
            )
            client_ids = [client.id for client in clients]
            session_repo = TreatmentSessionRepository(session)
            last_session_dates = session_repo.get_last_session_dates(client_ids)
            upcoming_by_client = session_repo.get_upcoming_sessions(client_ids)
            return [
                ClientListEntry(
                    id=client.id,
                    salutation=client.salutation,
                    first_name=client.first_name,
                    last_name=client.last_name,
                    city=client.city,
                    phone=client.phone,
                    archived=client.archived,
                    last_session_date=last_session_dates.get(client.id),
                    upcoming_appointments=[
                        UpcomingAppointment(
                            date=s.date,
                            duration_minutes=s.duration_minutes,
                            treatment_type_name=s.treatment_type.name,
                        )
                        for s in upcoming_by_client.get(client.id, [])
                    ],
                )
                for client in clients
            ]

    @database_errors_as("Klient konnte nicht gespeichert werden.")
    def update_client(
        self,
        client_id: int,
        *,
        first_name: str,
        last_name: str,
        salutation: str | None = None,
        birth_date: date | None = None,
        street: str | None = None,
        postal_code: str | None = None,
        city: str | None = None,
        phone: str | None = None,
        email: str | None = None,
        concern: str | None = None,
        referral_source: str | None = None,
        consent_date: date | None = None,
        notes: str | None = None,
    ) -> Client:
        first_name, last_name = self._validate_name(first_name, last_name)
        salutation = self._normalize_optional(salutation)
        street = self._normalize_optional(street)
        city = self._normalize_optional(city)
        with self._session_factory() as session:
            client = ClientRepository(session).get_by_id(client_id)
            if client is None:
                raise NotFoundError(f"Klient mit ID {client_id} wurde nicht gefunden.")
            client.first_name = first_name
            client.last_name = last_name
            client.salutation = salutation
            client.birth_date = birth_date
            client.street = street
            client.postal_code = postal_code
            client.city = city
            client.phone = phone
            client.email = email
            client.concern = concern
            client.referral_source = referral_source
            client.consent_date = consent_date
            client.notes = notes
            with transaction(session, "Klient konnte nicht gespeichert werden."):
                pass
        return client

    @database_errors_as("Klient konnte nicht aktualisiert werden.")
    def archive_client(self, client_id: int) -> None:
        self._set_archived(client_id, archived=True)

    @database_errors_as("Klient konnte nicht aktualisiert werden.")
    def unarchive_client(self, client_id: int) -> None:
        self._set_archived(client_id, archived=False)

    @database_errors_as("Klient konnte nicht gelöscht werden.")
    def delete_client(self, client_id: int) -> None:
        with self._session_factory() as session:
            repo = ClientRepository(session)
            client = repo.get_by_id(client_id)
            if client is None:
                raise NotFoundError(f"Klient mit ID {client_id} wurde nicht gefunden.")
            with transaction(session, "Klient konnte nicht gelöscht werden."):
                repo.delete(client)

    def _set_archived(self, client_id: int, *, archived: bool) -> None:
        with self._session_factory() as session:
            client = ClientRepository(session).get_by_id(client_id)
            if client is None:
                raise NotFoundError(f"Klient mit ID {client_id} wurde nicht gefunden.")
            client.archived = archived
            with transaction(session, "Klient konnte nicht aktualisiert werden."):
                pass

    @staticmethod
    def _validate_name(first_name: str, last_name: str) -> tuple[str, str]:
        first_name = first_name.strip()
        last_name = last_name.strip()
        if not first_name or not last_name:
            raise ValidationError("Vor- und Nachname sind Pflichtfelder.")
        return _normalize_casing(first_name), _normalize_casing(last_name)

    @staticmethod
    def _normalize_optional(text: str | None) -> str | None:
        return _normalize_casing(text) if text else text

    @staticmethod
    def client_since_date(created_at: datetime, *, local_tz: tzinfo | None = None) -> date:
        """The local calendar date of a client's created_at timestamp.

        created_at is stored as a naive UTC timestamp (SQLite's
        CURRENT_TIMESTAMP) while the rest of the app works with naive local
        datetimes - shown as-is, "Klient seit" would show the previous day
        for a client created late at night local time. local_tz is only
        for tests; production code always converts to the system's local
        timezone (astimezone(None)).
        """
        return created_at.replace(tzinfo=UTC).astimezone(local_tz).date()

    @staticmethod
    def compute_age(birth_date: date, *, today: date | None = None) -> int:
        today = today if today is not None else date.today()
        age = today.year - birth_date.year
        if (today.month, today.day) < (birth_date.month, birth_date.day):
            age -= 1
        return age

    @staticmethod
    def build_address_block(client: Client) -> ClientAddressBlock:
        name_line = " ".join(
            part
            for part in (client.salutation, client.first_name, client.last_name)
            if part
        )

        lines: list[str] = []
        if client.street:
            lines.append(client.street)
        postal_and_city = " ".join(
            part for part in (client.postal_code, client.city) if part
        )
        if postal_and_city:
            lines.append(postal_and_city)

        contact_lines: list[str] = []
        if client.phone:
            contact_lines.append(f"Telefon: {client.phone}")
        if client.email:
            contact_lines.append(f"E-Mail: {client.email}")

        return ClientAddressBlock(
            name_line=name_line, lines=lines, contact_lines=contact_lines
        )
