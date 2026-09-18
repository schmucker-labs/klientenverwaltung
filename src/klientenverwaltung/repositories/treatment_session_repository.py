from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, joinedload

from klientenverwaltung.models import TreatmentSession


class TreatmentSessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, treatment_session: TreatmentSession) -> TreatmentSession:
        self._session.add(treatment_session)
        self._session.flush()
        return treatment_session

    def get_by_id(self, session_id: int) -> TreatmentSession | None:
        return self._session.get(TreatmentSession, session_id)

    def delete(self, treatment_session: TreatmentSession) -> None:
        self._session.delete(treatment_session)

    def count_for_treatment_type(self, treatment_type_id: int) -> int:
        stmt = select(func.count(TreatmentSession.id)).where(
            TreatmentSession.treatment_type_id == treatment_type_id
        )
        return self._session.scalar(stmt) or 0

    def list_for_client(self, client_id: int) -> list[TreatmentSession]:
        # Eager-loads treatment_type so callers can read session.treatment_type.name
        # after this repository's session/transaction has ended.
        stmt = (
            select(TreatmentSession)
            .where(TreatmentSession.client_id == client_id)
            .options(joinedload(TreatmentSession.treatment_type))
            .order_by(TreatmentSession.date.desc())
        )
        return list(self._session.scalars(stmt))

    def get_last_and_next_session_dates(
        self, client_ids: Sequence[int] | None = None, *, now: datetime | None = None
    ) -> dict[int, tuple[datetime | None, datetime | None]]:
        """Per client: (most recent past session date, next future session date).

        Both come from one grouped query with conditional aggregation, not one
        query per client and not two separate queries.
        """
        reference = now if now is not None else datetime.now()
        last_session_date = func.max(
            case((TreatmentSession.date < reference, TreatmentSession.date))
        )
        next_appointment_date = func.min(
            case((TreatmentSession.date >= reference, TreatmentSession.date))
        )
        stmt = select(
            TreatmentSession.client_id, last_session_date, next_appointment_date
        ).group_by(TreatmentSession.client_id)
        if client_ids is not None:
            stmt = stmt.where(TreatmentSession.client_id.in_(client_ids))
        return {
            client_id: (last_date, next_date)
            for client_id, last_date, next_date in self._session.execute(stmt).all()
        }
