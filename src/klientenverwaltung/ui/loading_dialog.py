from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from klientenverwaltung.ui.loading_spinner import LoadingSpinnerWidget
from klientenverwaltung.ui.theme import get_palette, load_theme_mode

_SHOW_DELAY_MS = 500


class LoadingDialog(QDialog):
    """A themed progress indicator for a long-running background operation
    (Auftrag C1's media import). Never appears for an operation that
    finishes within _SHOW_DELAY_MS, so a small file's import never flashes
    it on screen - call finish() exactly once, from the operation's
    completion handler, whether or not this ever became visible.
    """

    cancelled = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Bitte warten")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)

        palette = get_palette(load_theme_mode())
        self._spinner = LoadingSpinnerWidget(self)
        self._spinner.set_colors(palette.accent, palette.accent_secondary)

        self._percent_label = QLabel("0 %", self)
        self._percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        cancel_button = QPushButton("Abbrechen", self)
        cancel_button.clicked.connect(self._on_cancel_clicked)

        layout = QVBoxLayout(self)
        layout.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(self._percent_label)
        layout.addWidget(cancel_button, 0, Qt.AlignmentFlag.AlignHCenter)

        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.setInterval(_SHOW_DELAY_MS)
        self._show_timer.timeout.connect(self.show)
        self._show_timer.start()

    def set_progress(self, done: int, total: int) -> None:
        percent = 0 if total <= 0 else min(100, round(done * 100 / total))
        self._percent_label.setText(f"{percent} %")

    def finish(self) -> None:
        """Call exactly once when the underlying operation is done
        (success, failure, or cancelled) - stops the delayed-show timer
        (so it can't pop the dialog back up afterwards) and closes it,
        harmless even if it was never shown at all.

        Uses done() rather than close(): QDialog's default closeEvent()
        calls reject() when nothing else does, which would loop straight
        back into this class's own overridden reject() below (there to
        make Escape/the window's X act like "Abbrechen") - which only
        re-emits `cancelled` and never actually closes anything. done()
        hides the dialog directly without going through closeEvent/reject
        at all.
        """
        self._show_timer.stop()
        self.done(QDialog.DialogCode.Rejected)

    def _on_cancel_clicked(self) -> None:
        self.cancelled.emit()

    def reject(self) -> None:
        # Escape/close button acts exactly like the Abbrechen button - the
        # caller is still responsible for actually closing this dialog via
        # finish() once the cancellation has taken effect, so this must
        # NOT call super().reject() itself.
        self._on_cancel_clicked()
