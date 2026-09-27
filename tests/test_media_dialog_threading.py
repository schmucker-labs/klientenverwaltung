import contextlib
import os
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import QCoreApplication

from klientenverwaltung.models import TreatmentSession
from klientenverwaltung.services import MediaService, TreatmentSessionService
from klientenverwaltung.ui import media_dialog as media_dialog_module
from klientenverwaltung.ui.media_dialog import MediaDialog

_WATCHDOG_SECONDS = 15.0


@contextlib.contextmanager
def _hang_watchdog() -> Iterator[None]:
    """Hard-kills the whole test process if the block does not finish in
    time. A wrong Qt cross-thread connection (this file's whole reason to
    exist) can call QMessageBox.exec() from a non-GUI thread, which does
    not raise or time out on its own - it hangs the process indefinitely
    (confirmed while diagnosing the bug these tests pin). A plain
    assertion failure could never surface from inside that hang, so
    without this, a regression here would silently hang CI forever
    instead of failing fast.
    """
    timer = threading.Timer(_WATCHDOG_SECONDS, lambda: os._exit(1))
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()


def _make_source_file(tmp_path: Path, name: str, content: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def _process_events_until(condition, timeout_seconds: float = 5.0) -> None:
    """Pumps the (real, not mocked) Qt event loop from the test's own
    thread - exactly what a running application does - until `condition`
    becomes true or the timeout is hit. Needed because MediaDialog's
    import spins up a real background QThread; without pumping events,
    any AutoConnection/QueuedConnection signal delivery back to this
    (GUI) thread would never actually run.
    """
    deadline = time.monotonic() + timeout_seconds
    while not condition():
        QCoreApplication.processEvents()
        if time.monotonic() > deadline:
            pytest.fail("timed out waiting for the import to finish")


def _eager_session(
    treatment_session_service: TreatmentSessionService,
    treatment_session: TreatmentSession,
) -> TreatmentSession:
    """A session with treatment_type already loaded, the way every real
    caller of MediaDialog gets one (via list_sessions_for_client's
    joinedload) - the plain `treatment_session` fixture's object was
    returned from a now-closed session and would raise
    DetachedInstanceError the moment MediaDialog's heading reads
    session.treatment_type.name.
    """
    return treatment_session_service.list_sessions_for_client(
        treatment_session.client_id
    )[0]


class _ThreadRecordingMediaDialog(MediaDialog):
    """Records which OS thread _on_import_finished actually ran on.

    A real subclass override, not an instance-attribute monkeypatch: Qt's
    AutoConnection only recognizes a *bound method of a QObject* as
    carrying a receiver context to queue through. Assigning a plain
    function onto `self._on_import_finished` as an instance attribute
    would not be a bound method at all (no descriptor binding happens for
    an instance-dict entry) and would silently defeat the very thing this
    test needs to observe - falling back to the same "direct call in the
    emitting thread" behavior as the lambda bug being pinned, regardless
    of whether the fix is present.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.handler_thread_ids: list[int] = []

    def _on_import_finished(self, outcome) -> None:
        self.handler_thread_ids.append(threading.get_ident())
        super()._on_import_finished(outcome)


def test_successful_import_completion_runs_on_the_gui_thread(
    qapp,
    monkeypatch: pytest.MonkeyPatch,
    media_service: MediaService,
    treatment_session_service: TreatmentSessionService,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    """Regression for a lambda-connected `finished` signal running the
    completion handler on the worker thread instead of the GUI thread
    (no receiver QObject for AutoConnection to queue through) - which in
    the real dialog goes on to stop a GUI-thread QTimer and exec() a
    QMessageBox from off-thread, hanging the application on every
    successful import.

    show_info is stubbed out: a successful import's real completion
    handler shows one, and this test's job is to check which thread that
    handler ran on, not to click through a real modal QMessageBox (which
    would otherwise block this test forever waiting for a click that
    never comes).
    """
    monkeypatch.setattr(media_dialog_module, "show_info", lambda *a, **k: None)
    session = _eager_session(treatment_session_service, treatment_session)
    dialog = _ThreadRecordingMediaDialog(media_service, session, "Anna Muster")
    source = _make_source_file(tmp_path, "foto.jpg", b"a" * 1000)

    with _hang_watchdog():
        dialog._start_import(source)
        _process_events_until(lambda: dialog._thread is None)

    assert dialog.handler_thread_ids == [threading.get_ident()]


def test_cancel_via_loading_dialog_actually_cancels_the_worker(
    qapp,
    media_service: MediaService,
    treatment_session_service: TreatmentSessionService,
    treatment_session: TreatmentSession,
    tmp_path: Path,
) -> None:
    """Regression for `cancelled.connect(self._worker.cancel)` resolving
    to a QueuedConnection into the worker thread's own event loop - which
    never runs while the worker is inside import_file(), so the click
    handler for "Abbrechen" could never actually deliver the cancellation
    before the copy had already finished on its own.
    """
    session = _eager_session(treatment_session_service, treatment_session)
    dialog = MediaDialog(media_service, session, "Anna Muster")
    source = _make_source_file(tmp_path, "video.mp4", b"x" * 5000)

    with _hang_watchdog():
        dialog._start_import(source)
        assert dialog._loading_dialog is not None
        # Exactly what clicking "Abbrechen" does.
        dialog._loading_dialog.cancelled.emit()

        _process_events_until(lambda: dialog._thread is None)

    assert media_service.list_media_for_session(session.id) == []
