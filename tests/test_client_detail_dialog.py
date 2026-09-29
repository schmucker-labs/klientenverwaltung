from PySide6.QtWidgets import QApplication

from klientenverwaltung.app_context import AppServices
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
