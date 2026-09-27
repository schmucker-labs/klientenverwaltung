from collections.abc import Sequence

from PySide6.QtWidgets import QWidget

from klientenverwaltung.services import MediaService
from klientenverwaltung.ui.dialogs import ask_delete_now_unused_media, show_error


def offer_to_delete_now_unused_media(
    media_service: MediaService,
    candidate_media_ids: Sequence[int],
    parent: QWidget | None,
) -> None:
    """Call right after an action that may have removed the last link to
    some media - removing one link in the Medienfenster, deleting a
    session, deleting a client. Never call this for archiving, which
    never touches media links at all.

    Checks which of candidate_media_ids are now used by no session, and
    if any are, asks once (see ask_delete_now_unused_media) whether to
    delete them for good. A file that can't actually be removed (open
    elsewhere) is reported in a plain message; its database row is kept,
    so it stays visible in the Medienübersicht as 0x.
    """
    unused = media_service.find_now_unused(candidate_media_ids)
    if not unused:
        return
    names = [media.original_filename for media in unused]
    if not ask_delete_now_unused_media(names, parent=parent):
        return
    failures = media_service.delete_unused_media([media.id for media in unused])
    if failures:
        failed_names = [media.original_filename for media in failures]
        show_error(
            "Folgende Dateien konnten nicht gelöscht werden, vermutlich weil sie "
            "gerade geöffnet sind: " + ", ".join(failed_names),
            parent=parent,
        )
