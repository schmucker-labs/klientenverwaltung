from klientenverwaltung.ui.loading_dialog import LoadingDialog


def test_finish_actually_closes_an_already_visible_dialog(qapp) -> None:
    """Regression: finish() called close(), and QDialog's default
    closeEvent() handler calls reject() when nothing else does - which
    landed right back on LoadingDialog's own overridden reject() (there
    to make Escape/the window's X act like clicking "Abbrechen"), which
    only re-emits `cancelled` and never actually closes anything. Once
    the dialog had become visible (past the 500ms delay), calling
    finish() from the real import-completion handler therefore left it
    stuck on screen forever - modal, blocking the whole application,
    with the spinner still animating (its hideEvent, which stops the
    timer, never fired either) - exactly what required a Task Manager
    kill to recover from.
    """
    dialog = LoadingDialog()
    dialog._show_timer.stop()  # bypass the delay - simulate it already being on screen
    dialog.show()
    assert dialog.isVisible()

    dialog.finish()

    assert not dialog.isVisible()
    # The spinner's own rotation timer only stops in its hideEvent() - if
    # the dialog never actually closes, this keeps ticking (and repainting)
    # forever, exactly the "circles kept moving" half of the report.
    assert not dialog._spinner._timer.isActive()
