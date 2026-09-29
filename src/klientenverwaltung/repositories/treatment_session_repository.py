from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session, joinedload

from klientenverwaltung.models import TreatmentSession


def _has_content(column: InstrumentedAttribute[str | None]) -> ColumnElement[bool]:
    return and_(column.is_not(None), column != "")


def _any_content() -> ColumnElement[bool]:
    return or_(
        _has_content(TreatmentSession.report), _has_content(TreatmentSession.impulses)
    )


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

    def count_for_client(self, client_id: int) -> int:
        stmt = select(func.count(TreatmentSession.id)).where(
            TreatmentSession.client_id == client_id
        )
        return self._session.scalar(stmt) or 0

    def count_with_content_for_client(self, client_id: int) -> int:
        """Same filter as list_with_content_for_client(), without loading
        every report's HTML just to count it."""
        stmt = select(func.count(TreatmentSession.id)).where(
            TreatmentSession.client_id == client_id, _any_content()
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

    def list_with_content_for_client(self, client_id: int) -> list[TreatmentSession]:
        """Sessions for a client with a Bericht or Impulse entered, newest
        first - Auftrag B2's Berichtsverlauf and the "Berichte (n)" count
        on the Klientenübersicht both read this one query, so they can
        never disagree about what counts as "has content". Excludes empty
        strings as well as NULL, even though save_report() never lets a
        blank Bericht/Impulse reach the database as anything but NULL - a
        second, independent guard at the query that produces the count/list.

        Eager-loads treatment_type so callers can read session.treatment_type.name
        after this repository's session/transaction has ended.
        """
        stmt = (
            select(TreatmentSession)
            .where(TreatmentSession.client_id == client_id, _any_content())
            .options(joinedload(TreatmentSession.treatment_type))
            .order_by(TreatmentSession.date.desc(), TreatmentSession.id.desc())
        )
        return list(self._session.scalars(stmt))

    def find_overlapping(
        self,
        *,
        start: datetime,
        end: datetime,
        earliest_start: datetime,
        exclude_session_id: int | None = None,
    ) -> TreatmentSession | None:
        """First other session whose time range overlaps [start, end).

        A session that merely touches the boundary (starts exactly when the
        other ends) does not count as overlapping, so back-to-back
        appointments are allowed. An existing session's end time depends on
        its own duration_minutes, so the comparison happens in Python rather
        than as a portable SQL expression.

        Overlap is checked across all clients, not just the one being
        booked: this is a single-practitioner business, so the same person
        cannot conduct two sessions at once regardless of who they are with.

        earliest_start bounds the search: a session starting at or before it
        is over before `start` (the caller derives it from the longest
        allowed duration), so the query never loads the whole history.
        """
        stmt = (
            select(TreatmentSession)
            .where(TreatmentSession.date < end, TreatmentSession.date > earliest_start)
            .options(joinedload(TreatmentSession.client))
            .order_by(TreatmentSession.date)
        )
        if exclude_session_id is not None:
            stmt = stmt.where(TreatmentSession.id != exclude_session_id)
        for candidate in self._session.scalars(stmt):
            candidate_end = candidate.date + timedelta(
                minutes=candidate.duration_minutes
            )
            if candidate_end > start:
                return candidate
        return None

    def get_last_session_dates(
        self, client_ids: Sequence[int] | None = None, *, now: datetime | None = None
    ) -> dict[int, datetime]:
        """Per client: most recent past session date (clients with none are absent)."""
        reference = now if now is not None else datetime.now()
        stmt = (
            select(TreatmentSession.client_id, func.max(TreatmentSession.date))
            .where(TreatmentSession.date < reference)
            .group_by(TreatmentSession.client_id)
        )
        if client_ids is not None:
            stmt = stmt.where(TreatmentSession.client_id.in_(client_ids))
        return dict(self._session.execute(stmt).all())

    def get_upcoming_sessions(
        self, client_ids: Sequence[int] | None = None, *, now: datetime | None = None
    ) -> dict[int, list[TreatmentSession]]:
        """Per client: future sessions (date >= now), soonest first.

        Eager-loads treatment_type so callers can read the name after this
        repository's session/transaction has ended.
        """
        reference = now if now is not None else datetime.now()
        stmt = (
            select(TreatmentSession)
            .where(TreatmentSession.date >= reference)
            .options(joinedload(TreatmentSession.treatment_type))
            .order_by(TreatmentSession.date)
        )
        if client_ids is not None:
            stmt = stmt.where(TreatmentSession.client_id.in_(client_ids))
        upcoming: dict[int, list[TreatmentSession]] = {}
        for session in self._session.scalars(stmt):
            upcoming.setdefault(session.client_id, []).append(session)
        return upcoming
