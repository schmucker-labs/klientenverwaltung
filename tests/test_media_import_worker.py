from pathlib import Path

from klientenverwaltung.models import TreatmentSession
from klientenverwaltung.services import MediaService
from klientenverwaltung.ui.media_import_worker import MediaImportWorker


def test_run_emits_failed_for_a_non_service_error_instead_of_hanging(
    session_factory, treatment_session: TreatmentSession, tmp_path: Path
) -> None:
    """Regression: run() only caught ServiceError, so a plain OSError -
    e.g. shutil.disk_usage() raising because the drive vanished mid-copy,
    an ordinary event for an external USB drive - escaped uncaught. With
    no finished/failed signal ever emitted, the caller's modal
    LoadingDialog is left on screen forever with no way out (Abbrechen
    delivers to a worker that already crashed out of its event loop).
    """
    source = tmp_path / "foto.jpg"
    source.write_bytes(b"x")
    # A drive_root that does not exist makes shutil.disk_usage() inside
    # import_file() raise a plain OSError, before any ServiceError check.
    service = MediaService(session_factory, tmp_path / "does-not-exist")
    worker = MediaImportWorker(service, treatment_session.id, source)

    results: dict[str, object] = {}
    worker.finished.connect(lambda outcome: results.setdefault("finished", outcome))
    worker.failed.connect(lambda message: results.setdefault("failed", message))

    worker.run()

    assert "failed" in results
    assert "finished" not in results
    assert isinstance(results["failed"], str)
    assert results["failed"]
