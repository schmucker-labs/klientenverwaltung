from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from klientenverwaltung.models import TreatmentSession, TreatmentType
from klientenverwaltung.repositories import (
    ClientRepository,
    TreatmentSessionRepository,
    TreatmentTypeRepository,
)
from klientenverwaltung.services.errors import (
    NotFoundError,
    SessionOverlapError,
    ValidationError,
)
from klientenverwaltung.services.transaction import transaction


@dataclass(frozen=True)
class SessionSummary:
    """A client's last-past/next-future session date, as needed to show
    "Letzte Sitzung"/"Nächste Sitzung" in the client detail view - the
    exact same past/future split as the client list's "Letzte
    Sitzung"/"Nächster Termin" columns, since both read it from
    TreatmentSessionRepository.get_last_session_dates()/
    get_upcoming_sessions() rather than each defining "last"/"next"
    independently.
    """

    last_session_date: datetime | None
    next_session_date: datetime | None


class TreatmentSessionService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_session(
        self,
        *,
        client_id: int,
        treatment_type_id: int,
        date: datetime,
        duration_minutes: int,
        notes: str | None = None,
    ) -> TreatmentSession:
        self._validate_duration(duration_minutes)
        with self._session_factory() as session:
            if ClientRepository(session).get_by_id(client_id) is None:
                raise NotFoundError(f"Klient mit ID {client_id} wurde nicht gefunden.")

            treatment_type = TreatmentTypeRepository(session).get_by_id(
                treatment_type_id
            )
            self._require_active_treatment_type(treatment_type, treatment_type_id)

            repo = TreatmentSessionRepository(session)
            self._require_no_overlap(
                repo, date, duration_minutes, exclude_session_id=None
            )

            treatment_session = TreatmentSession(
                client_id=client_id,
                treatment_type_id=treatment_type_id,
                date=date,
                duration_minutes=duration_minutes,
                notes=notes,
            )
            with transaction(session, "Sitzung konnte nicht gespeichert werden."):
                repo.add(treatment_session)
        return treatment_session

    def get_session(self, session_id: int) -> TreatmentSession:
        with self._session_factory() as session:
            treatment_session = TreatmentSessionRepository(session).get_by_id(
                session_id
            )
        if treatment_session is None:
            raise NotFoundError(f"Sitzung mit ID {session_id} wurde nicht gefunden.")
        return treatment_session

    def list_sessions_for_client(self, client_id: int) -> list[TreatmentSession]:
        with self._session_factory() as session:
            return TreatmentSessionRepository(session).list_for_client(client_id)

    def get_session_summary(
        self, client_id: int, *, now: datetime | None = None
    ) -> SessionSummary:
        with self._session_factory() as session:
            repo = TreatmentSessionRepository(session)
            last_dates = repo.get_last_session_dates([client_id], now=now)
            upcoming = repo.get_upcoming_sessions([client_id], now=now)
        next_sessions = upcoming.get(client_id, [])
        return SessionSummary(
            last_session_date=last_dates.get(client_id),
            next_session_date=next_sessions[0].date if next_sessions else None,
        )

    def update_session(
        self,
        session_id: int,
        *,
        treatment_type_id: int,
        date: datetime,
        duration_minutes: int,
        notes: str | None = None,
    ) -> TreatmentSession:
        self._validate_duration(duration_minutes)
        with self._session_factory() as session:
            repo = TreatmentSessionRepository(session)
            treatment_session = repo.get_by_id(session_id)
            if treatment_session is None:
                raise NotFoundError(
                    f"Sitzung mit ID {session_id} wurde nicht gefunden."
                )

            treatment_type = TreatmentTypeRepository(session).get_by_id(
                treatment_type_id
            )
            self._require_active_treatment_type(treatment_type, treatment_type_id)

            self._require_no_overlap(
                repo, date, duration_minutes, exclude_session_id=session_id
            )

            treatment_session.treatment_type_id = treatment_type_id
            treatment_session.date = date
            treatment_session.duration_minutes = duration_minutes
            treatment_session.notes = notes
            with transaction(session, "Sitzung konnte nicht gespeichert werden."):
                pass
        return treatment_session

    def delete_session(self, session_id: int) -> None:
        with self._session_factory() as session:
            repo = TreatmentSessionRepository(session)
            treatment_session = repo.get_by_id(session_id)
            if treatment_session is None:
                raise NotFoundError(
                    f"Sitzung mit ID {session_id} wurde nicht gefunden."
                )
            with transaction(session, "Sitzung konnte nicht gelöscht werden."):
                repo.delete(treatment_session)

    @staticmethod
    def _validate_duration(duration_minutes: int) -> None:
        if duration_minutes <= 0:
            raise ValidationError("Die Dauer muss größer als 0 Minuten sein.")

    @staticmethod
    def _require_no_overlap(
        repo: TreatmentSessionRepository,
        date: datetime,
        duration_minutes: int,
        *,
        exclude_session_id: int | None,
    ) -> None:
        end = date + timedelta(minutes=duration_minutes)
        colliding = repo.find_overlapping(
            start=date, end=end, exclude_session_id=exclude_session_id
        )
        if colliding is not None:
            raise SessionOverlapError(
                "Diese Sitzung überschneidet sich mit einem Termin von "
                f"{colliding.client.first_name} {colliding.client.last_name} am "
                f"{colliding.date.strftime('%d.%m.%Y')} um "
                f"{colliding.date.strftime('%H:%M')} Uhr."
            )

    @staticmethod
    def _require_active_treatment_type(
        treatment_type: TreatmentType | None, treatment_type_id: int
    ) -> None:
        if treatment_type is None:
            raise NotFoundError(
                f"Behandlungsart mit ID {treatment_type_id} wurde nicht gefunden."
            )
        if not treatment_type.active:
            raise ValidationError(
                f'Die Behandlungsart "{treatment_type.name}" ist deaktiviert und kann '
                "nicht für neue Sitzungen verwendet werden."
            )
