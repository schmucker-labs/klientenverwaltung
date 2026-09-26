from datetime import datetime

import pytest

from klientenverwaltung.models import Client, TreatmentSession, TreatmentType
from klientenverwaltung.services import (
    NotFoundError,
    SessionOverlapError,
    ValidationError,
)
from klientenverwaltung.services.client_service import ClientService
from klientenverwaltung.services.treatment_session_service import (
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


def test_list_sessions_for_client_allows_reading_treatment_type_name_after_close(
    treatment_session_service: TreatmentSessionService,
    treatment_session: TreatmentSession,
    treatment_type: TreatmentType,
) -> None:
    """treatment_type must be eager-loaded, or this raises DetachedInstanceError."""
    sessions = treatment_session_service.list_sessions_for_client(
        treatment_session.client_id
    )

    assert sessions[0].treatment_type.name == treatment_type.name


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
