from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)
from sqlalchemy import Engine

from klientenverwaltung import config, storage
from klientenverwaltung.ui.dialogs import show_error
from klientenverwaltung.ui.window_settings import restore_geometry, save_geometry

_GEOMETRY_SETTINGS_KEY = "setup_wizard/geometry"


class _WelcomePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Willkommen")

        label = QLabel(
            "Diese Anwendung speichert alle Klientendaten verschlüsselt auf einer "
            "externen Datenplatte (zum Beispiel einer USB-Festplatte) - niemals "
            "auf diesem Computer selbst.\n\n"
            "Im nächsten Schritt wählen Sie die Platte, die dafür eingerichtet "
            "werden soll.",
            self,
        )
        label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(label)


class _DrivePage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Datenplatte wählen")
        self.setSubTitle(
            "Wählen Sie das Laufwerk, auf dem die Klientendaten gespeichert "
            "werden sollen."
        )

        self._drive_list = QListWidget(self)
        self._drive_list.currentItemChanged.connect(self._on_selection_changed)

        self._warning_label = QLabel(self)
        self._warning_label.setWordWrap(True)
        self._warning_label.setVisible(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self._drive_list)
        layout.addWidget(self._warning_label)

    def initializePage(self) -> None:
        self._drive_list.clear()
        for drive in storage.list_available_drives():
            item = QListWidgetItem(str(drive))
            item.setData(Qt.ItemDataRole.UserRole, drive)
            self._drive_list.addItem(item)
        self._update_warning()

    def _on_selection_changed(self) -> None:
        self._update_warning()
        self.completeChanged.emit()

    def _selected_drive(self) -> Path | None:
        item = self._drive_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _update_warning(self) -> None:
        drive = self._selected_drive()
        if drive is None:
            self._warning_label.setVisible(False)
            return
        if storage.drive_already_set_up(drive):
            self._warning_label.setText(
                f"Dieses Laufwerk ({drive}) ist bereits als Datenplatte "
                "eingerichtet. Bitte ein anderes Laufwerk wählen."
            )
            self._warning_label.setVisible(True)
        elif not storage.is_removable_drive(drive):
            self._warning_label.setText(
                f"Windows erkennt {drive} nicht als Wechseldatenträger. Falls dies "
                "die interne Festplatte dieses Computers ist, bitte ein anderes "
                "Laufwerk wählen. Externe USB-Festplatten werden von Windows "
                "manchmal ebenfalls so gemeldet und können trotzdem verwendet "
                "werden."
            )
            self._warning_label.setVisible(True)
        else:
            self._warning_label.setVisible(False)

    def isComplete(self) -> bool:
        drive = self._selected_drive()
        return drive is not None and not storage.drive_already_set_up(drive)

    def validatePage(self) -> bool:
        wizard = self.wizard()
        assert isinstance(wizard, SetupWizard)
        wizard.selected_drive = self._selected_drive()
        return True


class _PasswordPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Passwort festlegen")
        self.setSubTitle(
            f"Das Passwort muss mindestens {storage.MIN_PASSWORD_LENGTH} Zeichen "
            "lang sein."
        )

        warning = QLabel(
            "Wichtig: Ohne dieses Passwort können die Daten NICHT "
            "wiederhergestellt werden. Es gibt keine Möglichkeit, ein "
            "vergessenes Passwort zurückzusetzen.",
            self,
        )
        warning.setWordWrap(True)
        bold_font = warning.font()
        bold_font.setBold(True)
        warning.setFont(bold_font)

        self._password_edit = QLineEdit(self)
        self._password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_repeat_edit = QLineEdit(self)
        self._password_repeat_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_checkbox = QCheckBox(
            "Ich habe verstanden: Ohne dieses Passwort sind die Daten "
            "unwiederbringlich verloren.",
            self,
        )

        self._error_label = QLabel(self)
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)

        form = QFormLayout()
        form.addRow("Passwort:", self._password_edit)
        form.addRow("Passwort wiederholen:", self._password_repeat_edit)

        layout = QVBoxLayout(self)
        layout.addWidget(warning)
        layout.addLayout(form)
        layout.addWidget(self._confirm_checkbox)
        layout.addWidget(self._error_label)

        self._password_edit.textChanged.connect(self._on_changed)
        self._password_repeat_edit.textChanged.connect(self._on_changed)
        self._confirm_checkbox.toggled.connect(self._on_changed)

    def _on_changed(self) -> None:
        self._update_error()
        self.completeChanged.emit()

    def _password_long_enough(self) -> bool:
        return len(self._password_edit.text()) >= storage.MIN_PASSWORD_LENGTH

    def _passwords_match(self) -> bool:
        return self._password_edit.text() == self._password_repeat_edit.text()

    def _update_error(self) -> None:
        if not self._password_edit.text() and not self._password_repeat_edit.text():
            self._error_label.setVisible(False)
            return
        if not self._password_long_enough():
            self._error_label.setText(
                "Das Passwort muss mindestens "
                f"{storage.MIN_PASSWORD_LENGTH} Zeichen lang sein."
            )
            self._error_label.setVisible(True)
        elif not self._passwords_match():
            self._error_label.setText("Die beiden Passwörter stimmen nicht überein.")
            self._error_label.setVisible(True)
        else:
            self._error_label.setVisible(False)

    def isComplete(self) -> bool:
        return (
            self._password_long_enough()
            and self._passwords_match()
            and self._confirm_checkbox.isChecked()
        )

    def validatePage(self) -> bool:
        wizard = self.wizard()
        assert isinstance(wizard, SetupWizard)
        wizard.chosen_password = self._password_edit.text()
        return True


class _BackupFolderPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Sicherungsordner wählen")
        self.setSubTitle(
            "Hier werden automatische Sicherungen der Datenbank abgelegt, zum "
            "Beispiel auf einer zweiten Festplatte oder einem Netzwerkpfad."
        )

        self._chosen_folder: Path | None = None
        self._path_label = QLabel("Kein Sicherungsordner ausgewählt.", self)
        self._path_label.setWordWrap(True)

        choose_button = QPushButton("Ordner wählen…", self)
        choose_button.clicked.connect(self._on_choose_clicked)

        skip_note = QLabel(
            "Dieser Schritt kann übersprungen werden - Sicherungen sind dann "
            "zunächst deaktiviert und können jederzeit über Einstellungen → "
            "Sicherungsordner wählen nachgetragen werden.",
            self,
        )
        skip_note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self._path_label)
        layout.addWidget(choose_button)
        layout.addWidget(skip_note)

    def _on_choose_clicked(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Sicherungsordner wählen")
        if folder:
            self._chosen_folder = Path(folder)
            self._path_label.setText(f"Gewählt: {folder}")

    def isComplete(self) -> bool:
        return True

    def validatePage(self) -> bool:
        wizard = self.wizard()
        assert isinstance(wizard, SetupWizard)
        wizard.chosen_backup_folder = self._chosen_folder
        return True


class _SummaryPage(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Einrichtung abschließen")

        self._summary_label = QLabel(self)
        self._summary_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self._summary_label)

    def initializePage(self) -> None:
        wizard = self.wizard()
        assert isinstance(wizard, SetupWizard)
        backup_line = (
            f"Sicherungsordner: {wizard.chosen_backup_folder}"
            if wizard.chosen_backup_folder is not None
            else "Sicherungsordner: übersprungen (kann später in den "
            "Einstellungen nachgetragen werden)"
        )
        self._summary_label.setText(
            f"Datenplatte: {wizard.selected_drive}\n"
            "Passwort: festgelegt\n"
            f"{backup_line}\n\n"
            'Mit "Fertig stellen" werden jetzt die Kennungsdatei, die '
            "verschlüsselte Datenbank und die Standard-Behandlungsarten "
            "angelegt."
        )

    def validatePage(self) -> bool:
        wizard = self.wizard()
        assert isinstance(wizard, SetupWizard)
        assert wizard.selected_drive is not None
        try:
            engine = storage.set_up_data_drive(
                wizard.selected_drive, wizard.chosen_password
            )
        except storage.StorageError as exc:
            show_error(str(exc), parent=self)
            return False
        if wizard.chosen_backup_folder is not None:
            config.set_backup_folder_path(wizard.chosen_backup_folder)
        wizard.engine = engine
        wizard.drive_root = wizard.selected_drive
        return True


class SetupWizard(QWizard):
    """First-run setup: pick a drive, set a password, optionally a backup folder.

    On success, .engine and .drive_root are set to the freshly created,
    already-open database - the caller can use them directly, exactly like a
    successful login to an existing drive.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Datenplatte einrichten")
        self.setModal(True)
        self.setButtonText(QWizard.WizardButton.BackButton, "Zurück")
        self.setButtonText(QWizard.WizardButton.NextButton, "Weiter")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Fertig stellen")
        self.setButtonText(QWizard.WizardButton.CancelButton, "Abbrechen")
        restore_geometry(self, _GEOMETRY_SETTINGS_KEY)

        self.selected_drive: Path | None = None
        self.chosen_password: str = ""
        self.chosen_backup_folder: Path | None = None
        self.engine: Engine | None = None
        self.drive_root: Path | None = None

        self.addPage(_WelcomePage())
        self.addPage(_DrivePage())
        self.addPage(_PasswordPage())
        self.addPage(_BackupFolderPage())
        self.addPage(_SummaryPage())

    def done(self, result: int) -> None:
        save_geometry(self, _GEOMETRY_SETTINGS_KEY)
        super().done(result)
