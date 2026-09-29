from datetime import datetime

import pytest
from sqlalchemy.orm import Session, sessionmaker

from klientenverwaltung.models import Client, TreatmentSession, TreatmentType
from klientenverwaltung.services import (
    NotFoundError,
    SessionOverlapError,
    ValidationError,
)
from klientenverwaltung.services.client_service import ClientService
from klientenverwaltung.services.treatment_session_service import (
    MAX_SESSION_DURATION_MINUTES,
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


def test_back_to_back_appointments_are_allowed_despite_leftover_seconds(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    """The session dialog shows HH:mm only, but a start derived from "now"
    carries hidden seconds - 14:00:47 + 60 min must not collide with a
    session the user sees starting at 15:00."""
    first = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 14, 0, 47, 123000),
        duration_minutes=60,
    )
    second = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 15, 0, 5),
        duration_minutes=60,
    )

    assert first.date == datetime(2026, 3, 1, 14, 0)
    assert second.date == datetime(2026, 3, 1, 15, 0)


def test_update_session_stores_the_date_at_minute_precision(
    treatment_session_service: TreatmentSessionService,
    treatment_session: TreatmentSession,
    treatment_type: TreatmentType,
) -> None:
    updated = treatment_session_service.update_session(
        treatment_session.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 4, 1, 8, 0, 59, 999999),
        duration_minutes=45,
    )

    assert updated.date == datetime(2026, 4, 1, 8, 0)


def test_update_session_keeps_a_since_deactivated_treatment_type(
    treatment_session_service: TreatmentSessionService,
    treatment_type_service: TreatmentTypeService,
    treatment_session: TreatmentSession,
    treatment_type: TreatmentType,
) -> None:
    """Deactivating a type must not lock its historical sessions: correcting
    date or duration keeps the (now inactive) type unchanged."""
    treatment_type_service.deactivate_treatment_type(treatment_type.id)

    updated = treatment_session_service.update_session(
        treatment_session.id,
        treatment_type_id=treatment_type.id,
        date=treatment_session.date,
        duration_minutes=75,
    )

    assert updated.duration_minutes == 75
    assert updated.treatment_type_id == treatment_type.id


def test_update_session_rejects_switching_to_a_deactivated_treatment_type(
    treatment_session_service: TreatmentSessionService,
    treatment_type_service: TreatmentTypeService,
    treatment_session: TreatmentSession,
) -> None:
    inactive = treatment_type_service.create_treatment_type(name="Reiki")
    treatment_type_service.deactivate_treatment_type(inactive.id)

    with pytest.raises(ValidationError):
        treatment_session_service.update_session(
            treatment_session.id,
            treatment_type_id=inactive.id,
            date=treatment_session.date,
            duration_minutes=60,
        )


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
    )

    assert updated.date == datetime(2026, 4, 1, 8, 0)
    assert updated.duration_minutes == 45


def test_delete_session(
    treatment_session_service: TreatmentSessionService,
    treatment_session: TreatmentSession,
) -> None:
    treatment_session_service.delete_session(treatment_session.id)

    with pytest.raises(NotFoundError):
        treatment_session_service.get_session(treatment_session.id)


def test_session_entries_carry_the_treatment_type_name(
    treatment_session_service: TreatmentSessionService,
    treatment_type_service: TreatmentTypeService,
    treatment_session: TreatmentSession,
    treatment_type: TreatmentType,
) -> None:
    """Returned as a plain value - no relationship to lazy-load after the
    session closed (which raised DetachedInstanceError) - and current after
    the type was changed."""
    sessions = treatment_session_service.list_sessions_for_client(
        treatment_session.client_id
    )
    assert sessions[0].treatment_type_name == treatment_type.name

    other_type = treatment_type_service.create_treatment_type(name="Reiki")
    updated = treatment_session_service.update_session(
        treatment_session.id,
        treatment_type_id=other_type.id,
        date=treatment_session.date,
        duration_minutes=treatment_session.duration_minutes,
    )
    assert updated.treatment_type_name == "Reiki"
    assert (
        treatment_session_service.get_session(updated.id).treatment_type_name == "Reiki"
    )


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


def test_get_session_summary_splits_past_and_future(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    now = datetime(2026, 6, 15, 12, 0)
    treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 6, 1, 10, 0),
        duration_minutes=60,
    )
    treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 7, 1, 10, 0),
        duration_minutes=60,
    )

    summary = treatment_session_service.get_session_summary(client.id, now=now)

    assert summary.last_session_date == datetime(2026, 6, 1, 10, 0)
    assert summary.next_session_date == datetime(2026, 7, 1, 10, 0)


def test_get_session_summary_does_not_treat_future_session_as_last(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    """The exact bug this method exists to fix: with only a future session,
    "last" must stay None rather than picking the most recently created one."""
    now = datetime(2026, 6, 15, 12, 0)
    treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 7, 1, 10, 0),
        duration_minutes=60,
    )

    summary = treatment_session_service.get_session_summary(client.id, now=now)

    assert summary.last_session_date is None
    assert summary.next_session_date == datetime(2026, 7, 1, 10, 0)


def test_save_report_persists_report_and_impulses(
    treatment_session_service: TreatmentSessionService,
    treatment_session: TreatmentSession,
) -> None:
    updated = treatment_session_service.save_report(
        treatment_session.id,
        report="<p>Ruhiger Verlauf.</p>",
        impulses="<p>Weiter Atemübungen.</p>",
    )

    fetched = treatment_session_service.get_session(treatment_session.id)
    assert updated.report == "<p>Ruhiger Verlauf.</p>"
    assert fetched.report == "<p>Ruhiger Verlauf.</p>"
    assert fetched.impulses == "<p>Weiter Atemübungen.</p>"


def test_save_report_unknown_session_raises_not_found(
    treatment_session_service: TreatmentSessionService,
) -> None:
    with pytest.raises(NotFoundError):
        treatment_session_service.save_report(999, report="Text", impulses=None)


@pytest.mark.parametrize(
    "blank_value",
    [
        None,
        "",
        "   \n\t ",
        "<p>   </p><p><br/></p>",
        # A realistic empty Qt QTextEdit document: only whitespace text
        # content, but with a <style> block whose CSS text must not be
        # mistaken for real content.
        """<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.0//EN" "http://www.w3.org/TR/REC-html40/strict.dtd">
<html><head><meta name="qrichtext" content="1" /><style type="text/css">
p, li { white-space: pre-wrap; }
</style></head><body style=" font-family:'Segoe UI';">
<p style=" margin-top:0px;"><br /></p></body></html>""",
    ],
)
def test_save_report_blank_content_stored_as_none(
    treatment_session_service: TreatmentSessionService,
    treatment_session: TreatmentSession,
    blank_value: str | None,
) -> None:
    updated = treatment_session_service.save_report(
        treatment_session.id, report=blank_value, impulses=blank_value
    )

    assert updated.report is None
    assert updated.impulses is None


def test_list_sessions_with_content_orders_newest_first_and_excludes_contentless(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    older = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 10, 9, 0),
        duration_minutes=60,
    )
    newer = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 20, 9, 0),
        duration_minutes=60,
    )
    without_content = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 25, 9, 0),
        duration_minutes=60,
    )
    treatment_session_service.save_report(older.id, report="<p>Alt</p>", impulses=None)
    treatment_session_service.save_report(newer.id, report="<p>Neu</p>", impulses=None)
    treatment_session_service.save_report(
        without_content.id, report=None, impulses=None
    )

    result = treatment_session_service.list_sessions_with_content(client.id)

    assert [s.id for s in result] == [newer.id, older.id]


def test_list_sessions_with_content_breaks_same_date_ties_deterministically(
    treatment_session_service: TreatmentSessionService,
    session_factory: sessionmaker[Session],
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    """Two sessions at the exact same date must still come back in a fixed,
    repeatable order (newest-inserted first) rather than whatever order
    SQLite happens to return ties in - Berichtsverlauf must not visibly
    reshuffle same-timestamp sessions between opens. create_session() itself
    rejects overlapping sessions (see SessionOverlapError), so an exact tie
    can never arise through the service's own API - this writes both rows
    directly to reach the tie in the first place."""
    same_date = datetime(2026, 1, 10, 9, 0)
    with session_factory() as db_session:
        first = TreatmentSession(
            client_id=client.id,
            treatment_type_id=treatment_type.id,
            date=same_date,
            duration_minutes=60,
            report="<p>Erste</p>",
        )
        second = TreatmentSession(
            client_id=client.id,
            treatment_type_id=treatment_type.id,
            date=same_date,
            duration_minutes=60,
            report="<p>Zweite</p>",
        )
        db_session.add_all([first, second])
        db_session.commit()
        first_id, second_id = first.id, second.id

    result = treatment_session_service.list_sessions_with_content(client.id)

    assert [s.id for s in result] == [second_id, first_id]


def test_list_sessions_with_content_is_scoped_to_the_given_client(
    treatment_session_service: TreatmentSessionService,
    client_service: ClientService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    """A session with content belonging to a different client must never
    leak into this client's Berichtsverlauf (Auftrag B2) - this renders
    health data verbatim under a named client, so a client_id mix-up here
    would be this app's worst-case bug."""
    other_client = client_service.create_client(first_name="Ohne", last_name="Zugriff")
    other_session = treatment_session_service.create_session(
        client_id=other_client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 10, 9, 0),
        duration_minutes=60,
    )
    treatment_session_service.save_report(
        other_session.id,
        report="<p>Gehört einem anderen Klienten</p>",
        impulses=None,
    )

    assert treatment_session_service.list_sessions_with_content(client.id) == []


def test_list_sessions_with_content_includes_session_with_only_impulses(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 10, 9, 0),
        duration_minutes=60,
    )
    treatment_session_service.save_report(
        session.id, report=None, impulses="<p>Impuls</p>"
    )

    result = treatment_session_service.list_sessions_with_content(client.id)

    assert [s.id for s in result] == [session.id]


def test_list_sessions_with_content_excludes_empty_string_content(
    treatment_session_service: TreatmentSessionService,
    session_factory: sessionmaker[Session],
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    """save_report() normalizes blank content to None before it ever reaches
    the database, so this bypasses it to write empty strings directly -
    proving the query itself treats "" as no content, not just that
    save_report() never lets one through."""
    session = treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 1, 14, 9, 0),
        duration_minutes=60,
    )
    with session_factory() as db_session:
        treatment_session = db_session.get(TreatmentSession, session.id)
        treatment_session.report = ""
        treatment_session.impulses = ""
        db_session.commit()

    assert treatment_session_service.list_sessions_with_content(client.id) == []


def test_create_session_rejects_a_duration_beyond_the_maximum(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    """The maximum bounds the overlap query (only sessions that start at
    most that long before a new one can still overlap it)."""
    with pytest.raises(ValidationError):
        treatment_session_service.create_session(
            client_id=client.id,
            treatment_type_id=treatment_type.id,
            date=datetime(2026, 3, 1, 9, 0),
            duration_minutes=MAX_SESSION_DURATION_MINUTES + 1,
        )


def test_a_long_session_still_blocks_a_later_start_within_it(
    treatment_session_service: TreatmentSessionService,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 8, 0),
        duration_minutes=MAX_SESSION_DURATION_MINUTES,
    )

    with pytest.raises(SessionOverlapError):
        treatment_session_service.create_session(
            client_id=client.id,
            treatment_type_id=treatment_type.id,
            date=datetime(2026, 3, 1, 15, 59),
            duration_minutes=30,
        )


def test_session_counts_match_the_lists(
    treatment_session_service: TreatmentSessionService,
    treatment_session: TreatmentSession,
    client: Client,
    treatment_type: TreatmentType,
) -> None:
    treatment_session_service.create_session(
        client_id=client.id,
        treatment_type_id=treatment_type.id,
        date=datetime(2026, 3, 1, 9, 0),
        duration_minutes=60,
    )
    treatment_session_service.save_report(
        treatment_session.id, report="<p>Bericht</p>", impulses=None
    )

    assert treatment_session_service.count_sessions_for_client(client.id) == 2
    assert treatment_session_service.count_sessions_with_content(client.id) == 1
