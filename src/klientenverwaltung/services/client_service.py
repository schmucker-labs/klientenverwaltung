from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, tzinfo

from sqlalchemy.orm import Session, sessionmaker

from klientenverwaltung.models import Client
from klientenverwaltung.repositories import ClientRepository, TreatmentSessionRepository
from klientenverwaltung.services.errors import (
    DuplicateClientError,
    NotFoundError,
    ValidationError,
)
from klientenverwaltung.services.phone import (
    PhoneNumberError,
    format_phone,
    normalize_phone,
)
from klientenverwaltung.services.search import fold, matches, search_terms
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


_LETTER = r"[^\W\d_]"  # any letter, umlauts and accents included
_LETTER_OR_DIGIT = r"[^\W_]"
_EMAIL_LOCAL_CHARS = r"[\w!#$%&'*+/=?^`{|}~-]+"

# The optional contact fields, keyed by the service methods' parameter name:
# what a filled-in value must look like, and the message shown otherwise.
# Deliberately lenient - these catch slips of the keyboard (letters in a PLZ,
# a missing "@"), they cannot tell whether an address really exists.
_CONTACT_RULES: dict[str, tuple[re.Pattern[str], str]] = {
    # Street and house number: "Hauptstraße 12a", "Am Hang 3/2", "C 4, 12".
    "street": (
        re.compile(
            rf"(?=.*{_LETTER})(?=.*[0-9])(?:{_LETTER_OR_DIGIT}|[ .,'’/()-])+",
        ),
        "Straße: Bitte Straße und Hausnummer eingeben, zum Beispiel Hauptstraße 12a.",
    ),
    # No country field, so both lengths are fine anywhere: 5 digits for
    # Germany, 4 for Austria and Switzerland.
    "postal_code": (
        re.compile(r"[0-9]{4,5}"),
        (
            "PLZ: Bitte 5 Ziffern eingeben (Österreich und Schweiz: 4), "
            "zum Beispiel 80331."
        ),
    ),
    # "Frankfurt (Oder)", "St. Gallen", "Villingen-Schwenningen".
    "city": (
        re.compile(rf"{_LETTER}(?:{_LETTER}|[ .'’/()-])+"),
        "Ort: Bitte nur den Ortsnamen ohne Ziffern eingeben, zum Beispiel Bad Tölz.",
    ),
    # "phone" has no entry here: services/phone.py knows the German numbering
    # rules and also rewrites the number in the standard spelling.
    # One "@", no empty part between dots, a domain ending in letters; at
    # most 64 characters before the "@" and 254 in all (the limits mail
    # servers accept). Stored in lower case, see _validate_contact_fields.
    "email": (
        re.compile(
            rf"(?=.{{1,254}}\Z)(?=[^@]{{1,64}}@)"
            rf"{_EMAIL_LOCAL_CHARS}(?:\.{_EMAIL_LOCAL_CHARS})*"
            rf"@(?:{_LETTER_OR_DIGIT}+(?:-+{_LETTER_OR_DIGIT}+)*\.)+{_LETTER}{{2,}}"
        ),
        (
            "E-Mail: Bitte eine vollständige Adresse eingeben, "
            "zum Beispiel name@beispiel.de."
        ),
    ),
}


def _validate_contact_fields(**fields: str | None) -> dict[str, str | None]:
    """The given contact fields with surrounding/repeated whitespace removed
    (empty becomes None), the telephone number in its standard spelling and
    the e-mail address in lower case - or one ValidationError listing every
    field that does not match its rule (_CONTACT_RULES; for the telephone
    number services/phone.py), in the order the fields were passed."""
    cleaned = {
        name: " ".join((value or "").split()) or None for name, value in fields.items()
    }
    problems: list[tuple[str, str]] = []
    for name, value in cleaned.items():
        if value is None:
            continue
        if name == "phone":
            try:
                cleaned[name] = normalize_phone(value)
            except PhoneNumberError as exc:
                problems.append((name, f"Telefon: {exc}"))
            continue
        pattern, message = _CONTACT_RULES[name]
        if not pattern.fullmatch(value):
            problems.append((name, message))
        elif name == "email":
            # Mail providers do not tell "Anna@Web.de" from "anna@web.de".
            cleaned[name] = value.lower()
    if problems:
        raise ValidationError(
            "\n\n".join(message for _, message in problems), field=problems[0][0]
        )
    return cleaned


def _possible_duplicates(
    clients: list[Client],
    *,
    first_name: str,
    last_name: str,
    birth_date: date | None,
    exclude_id: int | None = None,
) -> list[Client]:
    """The clients that may be the same person: the same first and last
    name (case and accents aside, like the search), unless both have a
    birth date and the two differ."""
    name = (fold(first_name), fold(last_name))
    return [
        client
        for client in clients
        if client.id != exclude_id
        and (fold(client.first_name), fold(client.last_name)) == name
        and (
            birth_date is None
            or client.birth_date is None
            or client.birth_date == birth_date
        )
    ]


def _duplicate_error(duplicates: list[Client]) -> DuplicateClientError:
    def describe(client: Client) -> str:
        parts = [f"{client.first_name} {client.last_name}"]
        if client.birth_date is not None:
            parts.append(f"geboren am {client.birth_date.strftime('%d.%m.%Y')}")
        if client.city:
            parts.append(client.city)
        return ", ".join(parts) + (" (archiviert)" if client.archived else "")

    intro = (
        "Es gibt bereits einen Klienten mit diesem Namen:"
        if len(duplicates) == 1
        else f"Es gibt bereits {len(duplicates)} Klienten mit diesem Namen:"
    )
    listed = "\n".join(f"• {describe(client)}" for client in duplicates)
    return DuplicateClientError(f"{intro}\n\n{listed}")


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
class ClientDetails:
    """A client's full record, as the UI shows and edits it - a plain value,
    so nothing outside the service layer depends on ORM objects."""

    id: int
    salutation: str | None
    first_name: str
    last_name: str
    birth_date: date | None
    street: str | None
    postal_code: str | None
    city: str | None
    phone: str | None
    email: str | None
    concern: str | None
    referral_source: str | None
    consent_date: date | None
    notes: str | None
    archived: bool
    created_at: datetime


def _client_details(client: Client) -> ClientDetails:
    """Must run while client's session is still open: created_at is a
    server default, loaded on first access."""
    return ClientDetails(
        id=client.id,
        salutation=client.salutation,
        first_name=client.first_name,
        last_name=client.last_name,
        birth_date=client.birth_date,
        street=client.street,
        postal_code=client.postal_code,
        city=client.city,
        # Also for entries stored before the standard spelling existed.
        phone=format_phone(client.phone),
        email=client.email.lower() if client.email else client.email,
        concern=client.concern,
        referral_source=client.referral_source,
        consent_date=client.consent_date,
        notes=client.notes,
        archived=client.archived,
        created_at=client.created_at,
    )


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
        allow_duplicate: bool = False,
    ) -> ClientDetails:
        """Raises DuplicateClientError - after every other check passed - if
        the person may already exist (see _possible_duplicates), unless
        allow_duplicate is set: the user confirmed it is someone else."""
        first_name, last_name = self._validate_name(first_name, last_name)
        self._validate_dates(birth_date=birth_date, consent_date=consent_date)
        contact = _validate_contact_fields(
            street=street, postal_code=postal_code, city=city, phone=phone, email=email
        )
        salutation = self._normalize_optional(salutation)
        client = Client(
            first_name=first_name,
            last_name=last_name,
            salutation=salutation,
            birth_date=birth_date,
            street=self._normalize_optional(contact["street"]),
            postal_code=contact["postal_code"],
            city=self._normalize_optional(contact["city"]),
            phone=contact["phone"],
            email=contact["email"],
            concern=concern,
            referral_source=referral_source,
            consent_date=consent_date,
            notes=notes,
        )
        with self._session_factory() as session:
            repo = ClientRepository(session)
            if not allow_duplicate:
                duplicates = _possible_duplicates(
                    repo.list(include_archived=True),
                    first_name=first_name,
                    last_name=last_name,
                    birth_date=birth_date,
                )
                if duplicates:
                    raise _duplicate_error(duplicates)
            with transaction(session, "Klient konnte nicht gespeichert werden."):
                repo.add(client)
            return _client_details(client)

    @database_errors_as(_LOAD_ERROR)
    def get_client(self, client_id: int) -> ClientDetails:
        with self._session_factory() as session:
            client = ClientRepository(session).get_by_id(client_id)
            if client is None:
                raise NotFoundError(f"Klient mit ID {client_id} wurde nicht gefunden.")
            return _client_details(client)

    @database_errors_as(_LOAD_ERROR)
    def list_clients(
        self, *, include_archived: bool = False, search: str | None = None
    ) -> list[ClientDetails]:
        with self._session_factory() as session:
            clients = ClientRepository(session).list(include_archived=include_archived)
            return [
                _client_details(client) for client in _filter_by_search(clients, search)
            ]

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
                    phone=format_phone(client.phone),
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
        allow_duplicate: bool = False,
    ) -> ClientDetails:
        """Raises DuplicateClientError like create_client - but only when
        the name or the birth date is being changed, so a namesake that was
        confirmed once does not ask again on every save."""
        first_name, last_name = self._validate_name(first_name, last_name)
        self._validate_dates(birth_date=birth_date, consent_date=consent_date)
        contact = _validate_contact_fields(
            street=street, postal_code=postal_code, city=city, phone=phone, email=email
        )
        salutation = self._normalize_optional(salutation)
        with self._session_factory() as session:
            repo = ClientRepository(session)
            client = repo.get_by_id(client_id)
            if client is None:
                raise NotFoundError(f"Klient mit ID {client_id} wurde nicht gefunden.")
            identity_changed = (fold(first_name), fold(last_name), birth_date) != (
                fold(client.first_name),
                fold(client.last_name),
                client.birth_date,
            )
            if identity_changed and not allow_duplicate:
                duplicates = _possible_duplicates(
                    repo.list(include_archived=True),
                    first_name=first_name,
                    last_name=last_name,
                    birth_date=birth_date,
                    exclude_id=client_id,
                )
                if duplicates:
                    raise _duplicate_error(duplicates)
            client.first_name = first_name
            client.last_name = last_name
            client.salutation = salutation
            client.birth_date = birth_date
            client.street = self._normalize_optional(contact["street"])
            client.postal_code = contact["postal_code"]
            client.city = self._normalize_optional(contact["city"])
            client.phone = contact["phone"]
            client.email = contact["email"]
            client.concern = concern
            client.referral_source = referral_source
            client.consent_date = consent_date
            client.notes = notes
            with transaction(session, "Klient konnte nicht gespeichert werden."):
                pass
            return _client_details(client)

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
            raise ValidationError(
                "Vor- und Nachname sind Pflichtfelder.",
                field="last_name" if first_name else "first_name",
            )
        return _normalize_casing(first_name), _normalize_casing(last_name)

    @staticmethod
    def _validate_dates(*, birth_date: date | None, consent_date: date | None) -> None:
        today = date.today()
        if birth_date is not None and birth_date > today:
            raise ValidationError("Das Geburtsdatum liegt in der Zukunft.")
        if consent_date is not None and consent_date > today:
            raise ValidationError(
                "Das Datum der Datenschutz-Einwilligung liegt in der Zukunft."
            )

    @staticmethod
    def _normalize_optional(text: str | None) -> str | None:
        return _normalize_casing(text) if text else text

    @staticmethod
    def client_since_date(
        created_at: datetime, *, local_tz: tzinfo | None = None
    ) -> date:
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
    def build_address_block(client: ClientDetails) -> ClientAddressBlock:
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
