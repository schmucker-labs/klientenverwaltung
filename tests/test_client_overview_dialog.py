import pytest
from PySide6.QtWidgets import QDialog

from klientenverwaltung.app_context import AppServices
from klientenverwaltung.models import Client
from klientenverwaltung.ui.client_overview_dialog import ClientOverviewDialog


def test_edit_and_sessions_buttons_construct_their_dialogs_without_error(
    qapp,
    monkeypatch: pytest.MonkeyPatch,
    app_services: AppServices,
    client: Client,
) -> None:
    """Regression: _on_edit_clicked() once constructed ClientDetailDialog
    without media_service - a call site missed when MediaService was
    threaded through the whole client/session window chain (Auftrag C1).
    Neither ruff nor a plain import-smoke-test catches a missing
    positional argument at a call site; it only surfaced when a real
    user clicked "Bearbeiten" in the running app. (The windows now share
    one AppServices bundle, which makes that class of bug unlikely.)
    """
    # QDialog.exec() would otherwise show a real modal dialog and block
    # this test forever waiting for a click that never comes - the bug
    # under test is in the constructor call, which already happened (or
    # already raised) by the time exec() would run.
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Rejected)

    dialog = ClientOverviewDialog(app_services, client.id)

    dialog._on_edit_clicked()
    dialog._on_sessions_clicked()
