from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from html.parser import HTMLParser

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


class _VisibleTextExtractor(HTMLParser):
    """Collects human-visible text from an HTML fragment, ignoring markup
    and any <script>/<style> content (a Qt rich-text document always
    carries a <style> block, whose CSS text would otherwise be mistaken
    for real content)."""

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._chunks: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._chunks.append(data)

    def is_blank(self) -> bool:
        return not "".join(self._chunks).strip()


def _normalize_html(value: str | None) -> str | None:
    """None for missing or blank content - including a Qt rich-text
    document (e.g. an untouched QTextEdit's toHtml()) that only contains
    whitespace once markup and styling are stripped away - so the database
    only ever stores None or genuinely entered content.
    """
    if value is None:
        return None
    extractor = _VisibleTextExtractor()
    extractor.feed(value)
    extractor.close()
    return None if extractor.is_blank() else value


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

    def count_sessions_with_content(self, client_id: int) -> int:
        """Sessions with a Bericht or Impulse entered (Auftrag A2's report
        window) - drives the "Berichte (n)" button on the Klientenübersicht
        (Auftrag B1)."""
        sessions = self.list_sessions_for_client(client_id)
        return sum(1 for session in sessions if session.report or session.impulses)

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
            with transaction(session, "Sitzung konnte nicht gespeichert werden."):
                pass
        return treatment_session

    def save_report(
        self, session_id: int, *, report: str | None, impulses: str | None
    ) -> TreatmentSession:
        """Saves a session's Bericht/Impulse (the report window from Auftrag
        A2). Blank content - including an untouched Qt rich-text document
        containing only whitespace - is normalized to None.
        """
        with self._session_factory() as session:
            repo = TreatmentSessionRepository(session)
            treatment_session = repo.get_by_id(session_id)
            if treatment_session is None:
                raise NotFoundError(
                    f"Sitzung mit ID {session_id} wurde nicht gefunden."
                )
            treatment_session.report = _normalize_html(report)
            treatment_session.impulses = _normalize_html(impulses)
            with transaction(session, "Bericht konnte nicht gespeichert werden."):
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
