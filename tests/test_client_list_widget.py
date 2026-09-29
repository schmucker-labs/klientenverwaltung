from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from klientenverwaltung.app_context import AppServices
from klientenverwaltung.ui.client_list_widget import ClientListWidget


def test_the_list_starts_sorted_by_last_name(
    qapp: QApplication, app_services: AppServices, isolated_qsettings: None
) -> None:
    widget = ClientListWidget(app_services)
    header = widget._table_view.horizontalHeader()

    assert header.sortIndicatorSection() == 1
    assert header.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder


def test_reloading_keeps_the_selected_client_selected(
    qapp: QApplication, app_services: AppServices, isolated_qsettings: None
) -> None:
    app_services.clients.create_client(first_name="Anna", last_name="Albers")
    berta = app_services.clients.create_client(first_name="Berta", last_name="Brandt")
    widget = ClientListWidget(app_services)
    row = next(
        row
        for row in range(widget._table_model.rowCount())
        if widget._table_model.entry_at(row).id == berta.id
    )
    widget._table_view.selectRow(row)
    app_services.clients.create_client(first_name="Aaron", last_name="Aach")

    widget._reload()

    selected = widget._selected_entry()
    assert selected is not None
    assert selected.id == berta.id
