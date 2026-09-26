# Build & Auslieferung

Hinweise zu PyInstaller, Hidden Imports und Icon-/Asset-Erzeugung. Lesen, bevor an den
`.spec`-Dateien, `scripts/pyinstaller_common.py`, `scripts/build_exe.py`,
`scripts/generate_icons.py` gearbeitet wird oder ein neues Qt-Modul bzw. eine neue
Alembic-Migration hinzukommt.

- PySide6-Untermodule werden von PyInstaller nicht immer zuverlässig erkannt und
  müssen dann in HIDDEN_IMPORTS stehen. Bei jedem neuen Qt-Modul im Code prüfen,
  ob es dort ergänzt werden muss. QtSvg/QtSvgWidgets insbesondere: siehe Regel
  weiter unten, die Anwendung lädt zur Laufzeit ausschließlich PNG.
- alembic/env.py und alembic/versions/*.py werden als Datendateien gebündelt und von
  PyInstaller nicht auf Imports analysiert. Jedes dort importierte Modul muss deshalb
  ausdrücklich in HIDDEN_IMPORTS stehen (z. B. logging.config), sonst fehlt es nur im
  Build ohne Python-Installation. Bei jeder neuen Migration prüfen, ob sie neue Imports
  mitbringt.
- Es werden immer zwei Builds erzeugt: Release ohne Konsole und eine Debug-Variante mit
  Konsole für die Fehlersuche beim Anwender.
- Die Anwendung lädt zur Laufzeit ausschließlich PNG, kein SVG: PySide6.QtSvg lässt
  sich mit PyInstaller nicht zuverlässig bündeln. SVG-Dateien bleiben Quellformat und
  werden beim Build in PNG umgewandelt.
- Die Anwendung startet sich nicht selbst neu: Ein aus der .exe heraus gestarteter
  Neuprozess findet die Qt-Plugins nicht zuverlässig, weil PyInstaller sie in einen
  temporären Ordner entpackt, den die beendende Instanz löscht. Wo ein Neustart nötig
  ist, wird der Nutzer darauf hingewiesen und die Anwendung beendet sich.