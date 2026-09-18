from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session, sessionmaker

from klientenverwaltung.models import TreatmentSession, TreatmentType
from klientenverwaltung.repositories import (
    ClientRepository,
    TreatmentSessionRepository,
    TreatmentTypeRepository,
)
from klientenverwaltung.services.errors import NotFoundError, ValidationError
from klientenverwaltung.services.transaction import transaction


class TreatmentSessionService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def create_session(
        self,
        *,
        client_id: int,
        treatment_type_id: int,
        date: datetime,
        duration_minutes: int | None = None,
        notes: str | None = None,
    ) -> TreatmentSession:
        with self._session_factory() as session:
            if ClientRepository(session).get_by_id(client_id) is None:
                raise NotFoundError(f"Klient mit ID {client_id} wurde nicht gefunden.")

            treatment_type = TreatmentTypeRepository(session).get_by_id(
                treatment_type_id
            )
            self._require_active_treatment_type(treatment_type, treatment_type_id)

            treatment_session = TreatmentSession(
                client_id=client_id,
                treatment_type_id=treatment_type_id,
                date=date,
                duration_minutes=duration_minutes,
                notes=notes,
            )
            with transaction(session, "Sitzung konnte nicht gespeichert werden."):
                TreatmentSessionRepository(session).add(treatment_session)
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

    def update_session(
        self,
        session_id: int,
        *,
        treatment_type_id: int,
        date: datetime,
        duration_minutes: int | None = None,
        notes: str | None = None,
    ) -> TreatmentSession:
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
