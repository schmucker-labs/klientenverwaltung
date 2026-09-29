from typing import Literal

from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QMessageBox, QWidget


def _exec_in_front(box: QMessageBox) -> None:
    """Runs box modally - raised and activated first when it has no parent
    window, like the startup messages ("Datenplatte nicht gefunden", ...)
    shown while the splash screen is up: otherwise such a box can open
    behind the splash, or without keyboard focus (see ask_for_password)."""
    if box.parentWidget() is None:
        box.show()
        box.raise_()
        box.activateWindow()
    box.exec()


_NAMES_SHOWN = 5


def summarize_names(names: list[str]) -> str:
    """A readable list for a message box: the first few names, then how
    many more - a client with dozens of media files must not produce a
    message taller than the screen."""
    if len(names) <= _NAMES_SHOWN:
        return ", ".join(names)
    shown = ", ".join(names[:_NAMES_SHOWN])
    return f"{shown} und {len(names) - _NAMES_SHOWN} weitere"


def show_about(
    program_name: str,
    version: str,
    author: str,
    icon: QPixmap,
    *,
    parent: QWidget | None = None,
) -> None:
    """Shows the "Über"/about dialog: name, version, logo, attribution."""
    box = QMessageBox(parent)
    box.setWindowTitle(f"Über {program_name}")
    box.setIconPixmap(icon)
    box.setText(
        f"<b>{program_name}</b><br>Version {version}<br><br>Product by {author}"
    )
    box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    _exec_in_front(box)


def show_error(
    message: str, *, title: str = "Fehler", parent: QWidget | None = None
) -> None:
    """Shows a plain, German, traceback-free error dialog with a single OK button."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setWindowTitle(title)
    box.setText(message)
    box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    _exec_in_front(box)


def show_info(
    message: str, *, title: str = "Information", parent: QWidget | None = None
) -> None:
    """Shows a plain, German, informational dialog with a single OK button."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle(title)
    box.setText(message)
    box.addButton("OK", QMessageBox.ButtonRole.AcceptRole)
    _exec_in_front(box)


def ask_retry(message: str, *, title: str, parent: QWidget | None = None) -> bool:
    """Shows a warning with "Erneut versuchen" / "Abbrechen"; returns True to retry."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(message)
    retry_button = box.addButton("Erneut versuchen", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(retry_button)
    _exec_in_front(box)
    return box.clickedButton() is retry_button


def ask_retry_or_setup(
    message: str, *, title: str, parent: QWidget | None = None
) -> Literal["retry", "setup", "cancel"]:
    """Like ask_retry, plus a third option to set up a brand-new data drive."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(message)
    retry_button = box.addButton("Erneut versuchen", QMessageBox.ButtonRole.AcceptRole)
    setup_button = box.addButton(
        "Neue Datenplatte einrichten…", QMessageBox.ButtonRole.ActionRole
    )
    box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(retry_button)
    _exec_in_front(box)
    clicked = box.clickedButton()
    if clicked is retry_button:
        return "retry"
    if clicked is setup_button:
        return "setup"
    return "cancel"


def ask_use_other_data_drive(
    message: str, *, parent: QWidget | None = None
) -> Literal["use", "retry", "cancel"]:
    """A data drive other than the recorded one was found; defaults to
    "Erneut versuchen" (e.g. after plugging in the usual drive)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Andere Datenplatte gefunden")
    box.setText(message)
    use_button = box.addButton(
        "Diese Platte verwenden", QMessageBox.ButtonRole.AcceptRole
    )
    retry_button = box.addButton("Erneut versuchen", QMessageBox.ButtonRole.ActionRole)
    box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(retry_button)
    _exec_in_front(box)
    clicked = box.clickedButton()
    if clicked is use_button:
        return "use"
    if clicked is retry_button:
        return "retry"
    return "cancel"


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
    _exec_in_front(box)
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
    _exec_in_front(box)
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
    _exec_in_front(box)
    return box.clickedButton() is delete_button


def ask_confirm_restore(
    message: str, *, title: str, parent: QWidget | None = None
) -> bool:
    """Shows an unambiguous overwrite warning for restoring a backup.

    Defaults to "Abbrechen" (safe default) - restoring overwrites the
    current database and cannot be undone.
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(message)
    restore_button = box.addButton(
        "Wiederherstellen", QMessageBox.ButtonRole.DestructiveRole
    )
    cancel_button = box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(cancel_button)
    _exec_in_front(box)
    return box.clickedButton() is restore_button


def ask_set_up_backup_folder(*, parent: QWidget | None = None) -> bool:
    """The (at most weekly) reminder while no backup folder is set up;
    True for "Jetzt einrichten…"."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Keine Sicherungen eingerichtet")
    box.setText(
        "Es ist noch kein Sicherungsordner eingerichtet. Ihre Daten liegen damit "
        "nur auf der Datenplatte - geht sie verloren oder kaputt, sind alle Daten "
        "weg.\n\nBitte einen Sicherungsordner auf einem anderen Datenträger "
        "wählen, zum Beispiel auf einer zweiten Festplatte."
    )
    set_up_button = box.addButton("Jetzt einrichten…", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Später", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(set_up_button)
    _exec_in_front(box)
    return box.clickedButton() is set_up_button


def ask_use_questionable_backup_folder(
    warning: str, *, parent: QWidget | None = None
) -> bool:
    """Shows backup.backup_folder_warning()'s text; defaults to choosing
    another folder. True for "Trotzdem verwenden"."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("Sicherungsordner prüfen")
    box.setText(warning)
    use_button = box.addButton("Trotzdem verwenden", QMessageBox.ButtonRole.AcceptRole)
    other_button = box.addButton(
        "Anderen Ordner wählen", QMessageBox.ButtonRole.RejectRole
    )
    box.setDefaultButton(other_button)
    _exec_in_front(box)
    return box.clickedButton() is use_button


def ask_use_existing_file(
    original_filename: str, *, parent: QWidget | None = None
) -> bool:
    """Shown when an imported file's content already exists in the media
    store under a possibly different name; Ja links the existing file
    without copying again, Nein skips attaching this file at all (the
    duplicate is not stored a second time - Auftrag C1's dedup would
    otherwise be pointless).
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Datei bereits vorhanden")
    box.setText(
        f'Diese Datei ist bereits vorhanden als "{original_filename}". '
        "Vorhandene Datei verwenden?"
    )
    yes_button = box.addButton("Ja", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("Nein", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(yes_button)
    _exec_in_front(box)
    return box.clickedButton() is yes_button


def ask_create_treatment_type(
    message: str, *, parent: QWidget | None = None
) -> bool:
    """Shown from "Neue Sitzung" when there is no active treatment type to
    select (Auftrag D1); "Behandlungsart anlegen" opens the existing
    treatment-type management, "Abbrechen" backs out of creating a session.
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Information)
    box.setWindowTitle("Keine aktive Behandlungsart")
    box.setText(message)
    create_button = box.addButton(
        "Behandlungsart anlegen", QMessageBox.ButtonRole.AcceptRole
    )
    box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(create_button)
    _exec_in_front(box)
    return box.clickedButton() is create_button


def ask_delete_now_unused_media(
    names: list[str], *, parent: QWidget | None = None
) -> bool:
    """Shown after an action (removing a link, deleting a session/client)
    that may have left one or more media files used by no session at all
    - "Löschen" removes the file(s) and their database rows right now,
    "Behalten" (the safer default) leaves them in place; either way they
    remain visible in the Medienübersicht (Auftrag C2), at 0x if kept.
    """
    count_phrase = (
        "Eine Mediendatei wird" if len(names) == 1 else f"{len(names)} Mediendateien werden"
    )
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Question)
    box.setWindowTitle("Nicht mehr verwendete Mediendateien")
    box.setText(
        f"{count_phrase} nicht mehr verwendet: {summarize_names(names)}. "
        "Jetzt endgültig löschen?"
    )
    delete_button = box.addButton("Löschen", QMessageBox.ButtonRole.DestructiveRole)
    keep_button = box.addButton("Behalten", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(keep_button)
    _exec_in_front(box)
    return box.clickedButton() is delete_button
