import pytest
from PySide6.QtWidgets import QApplication

from klientenverwaltung.app_context import AppServices
from klientenverwaltung.ui import client_detail_dialog
from klientenverwaltung.ui.client_detail_dialog import ClientDetailDialog


def test_saving_shows_the_stored_normalized_values(
    qapp: QApplication, app_services: AppServices
) -> None:
    """The service normalizes casing ("anna" -> "Anna"); the form must show
    what was actually stored, not keep the raw input."""
    dialog = ClientDetailDialog(app_services, None)
    dialog._first_name_edit.setText("anna")
    dialog._last_name_edit.setText("von muster")

    dialog._on_save_clicked()

    assert dialog._first_name_edit.text() == "Anna"
    assert dialog._last_name_edit.text() == "Von Muster"
    assert not dialog._is_dirty()


def test_an_existing_name_is_saved_only_after_the_warning_was_confirmed(
    qapp: QApplication, app_services: AppServices, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_services.clients.create_client(first_name="Anna", last_name="Muster")
    warnings: list[str] = []
    answer = False

    def ask(message: str, **_kwargs: object) -> bool:
        warnings.append(message)
        return answer

    monkeypatch.setattr(client_detail_dialog, "ask_save_possible_duplicate", ask)
    dialog = ClientDetailDialog(app_services, None)
    dialog._first_name_edit.setText("Anna")
    dialog._last_name_edit.setText("Muster")

    # "Abbrechen": nothing is saved, the form stays as it is.
    dialog._on_save_clicked()
    assert len(warnings) == 1 and "• Anna Muster" in warnings[0]
    assert dialog.client_id is None
    assert len(app_services.clients.list_clients()) == 1

    answer = True
    dialog._on_save_clicked()
    assert dialog.client_id is not None
    assert len(app_services.clients.list_clients()) == 2

    # Once saved, further saves of the same client do not ask again.
    dialog._city_edit.setText("Musterstadt")
    dialog._on_save_clicked()
    assert len(warnings) == 2
