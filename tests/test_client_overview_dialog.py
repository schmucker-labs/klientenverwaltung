import pytest
from PySide6.QtWidgets import QDialog

from klientenverwaltung.models import Client
from klientenverwaltung.services import (
    ClientService,
    MediaService,
    TreatmentSessionService,
    TreatmentTypeService,
)
from klientenverwaltung.ui.client_overview_dialog import ClientOverviewDialog


def test_edit_and_sessions_buttons_construct_their_dialogs_without_error(
    qapp,
    monkeypatch: pytest.MonkeyPatch,
    client_service: ClientService,
    treatment_type_service: TreatmentTypeService,
    treatment_session_service: TreatmentSessionService,
    media_service: MediaService,
    client: Client,
) -> None:
    """Regression: _on_edit_clicked() constructed ClientDetailDialog
    without media_service - a call site missed when MediaService was
    threaded through the whole client/session window chain (Auftrag C1).
    Neither ruff nor a plain import-smoke-test catches a missing
    positional argument at a call site; it only surfaced when a real
    user clicked "Bearbeiten" in the running app.
    """
    # QDialog.exec() would otherwise show a real modal dialog and block
    # this test forever waiting for a click that never comes - the bug
    # under test is in the constructor call, which already happened (or
    # already raised) by the time exec() would run.
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    dialog = ClientOverviewDialog(
        client_service,
        treatment_type_service,
        treatment_session_service,
        media_service,
        client.id,
    )

    dialog._on_edit_clicked()
    dialog._on_sessions_clicked()
