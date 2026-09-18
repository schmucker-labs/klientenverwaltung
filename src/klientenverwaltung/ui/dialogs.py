from PySide6.QtWidgets import QMessageBox, QWidget


def show_error(
    message: str, *, title: str = "Fehler", parent: QWidget | None = None
) -> None:
    """Shows a plain, German, traceback-free error dialog with a single OK button."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(title)
    box.setText(message)
    box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    box.exec()


def ask_retry(message: str, *, title: str, parent: QWidget | None = None) -> bool:
    """Shows a warning with "Erneut versuchen" / "Abbrechen"; returns True to retry."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(message)
    retry_button = box.addButton("Erneut versuchen", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(retry_button)
    box.exec()
    return box.clickedButton() is retry_button


def ask_save_discard_cancel(
    message: str,
    *,
    title: str = "Ungespeicherte Änderungen",
    parent: QWidget | None = None,
) -> str:
    """Shows the classic 3-way unsaved-changes prompt. Returns "save", "discard" or "cancel"."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(message)
    save_button = box.addButton("Speichern", QMessageBox.ButtonRole.AcceptRole)
    discard_button = box.addButton(
        "Änderungen verwerfen", QMessageBox.ButtonRole.DestructiveRole
    )
    box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(save_button)
    box.exec()
    clicked = box.clickedButton()
    if clicked is save_button:
        return "save"
    if clicked is discard_button:
        return "discard"
    return "cancel"


def ask_confirm_deactivate(
    message: str, *, title: str, parent: QWidget | None = None
) -> bool:
    """Shows a "Deaktivieren"/"Abbrechen" confirmation; defaults to Deaktivieren.

    Unlike deleting, deactivating is easily reversible, so the safe default
    here is the action itself rather than Abbrechen.
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(title)
    box.setText(message)
    deactivate_button = box.addButton("Deaktivieren", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(deactivate_button)
    box.exec()
    return box.clickedButton() is deactivate_button


def ask_confirm_delete(
    message: str, *, title: str, parent: QWidget | None = None
) -> bool:
    """Shows an unambiguous delete confirmation; defaults to "Abbrechen" (safe default)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(message)
    delete_button = box.addButton("Löschen", QMessageBox.ButtonRole.DestructiveRole)
    cancel_button = box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_button)
    box.exec()
    return box.clickedButton() is delete_button
