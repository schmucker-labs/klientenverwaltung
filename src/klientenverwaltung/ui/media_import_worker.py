import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from klientenverwaltung.services import MediaService, ServiceError


class MediaImportWorker(QObject):
    """Runs MediaService.import_file() on a background QThread.

    duplicate_found must be connected with Qt.ConnectionType.BlockingQueuedConnection
    to a GUI-thread slot that shows a QMessageBox and calls
    set_duplicate_answer() before returning - that connection type is what
    makes emit() here block this worker thread until the GUI thread's slot
    has actually finished, which is the only safe way to show a modal
    dialog in response to something happening on a non-GUI thread.
    """

    progress = Signal(int, int)
    duplicate_found = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, media_service: MediaService, session_id: int, source_path: Path) -> None:
        super().__init__()
        self._media_service = media_service
        self._session_id = session_id
        self._source_path = source_path
        self._cancel_event = threading.Event()
        self._duplicate_answer = False

    def cancel(self) -> None:
        self._cancel_event.set()

    def set_duplicate_answer(self, answer: bool) -> None:
        self._duplicate_answer = answer

    @Slot()
    def run(self) -> None:
        try:
            outcome = self._media_service.import_file(
                self._session_id,
                self._source_path,
                progress_callback=lambda done, total: self.progress.emit(done, total),
                should_cancel=self._cancel_event.is_set,
                confirm_duplicate=self._ask_duplicate,
            )
        except ServiceError as exc:
            self.failed.emit(str(exc))
            return
        except Exception:  # noqa: BLE001
            # Anything other than a ServiceError (e.g. a plain OSError from
            # shutil.disk_usage()/Path.stat() if the drive vanishes
            # mid-copy) must still reach the GUI thread as
            # a failed signal, never propagate silently off a background
            # thread - an uncaught exception here leaves the caller's modal
            # LoadingDialog on screen forever with no way to dismiss it,
            # since finished/failed would otherwise never fire at all.
            self.failed.emit("Die Datei konnte nicht übernommen werden.")
            return
        self.finished.emit(outcome)

    def _ask_duplicate(self, original_filename: str) -> bool:
        self._duplicate_answer = False
        self.duplicate_found.emit(original_filename)
        return self._duplicate_answer
