# Klientenverwaltung – Projektkontext

Übergabedokument für einen neuen Chat. Stand: 29.09.2026.
Ergänzt die `CLAUDE.md` im Repo (technische Regeln) und die `TODO.md` (offene Punkte).

**Phasenstand:** Phase A (Bericht/Impulse mit Formatierung), Phase B
(Klientenübersicht, Berichtsverlauf), Phase C (Medien, Medienübersicht) und Auftrag D1
(keine Standard-Behandlungsarten) sind abgeschlossen. Danach wurde ein umfassendes
Code-Review (`CODE_REVIEW.md`) durchgeführt und vollständig umgesetzt.

---

## Worum es geht

Desktop-Anwendung für einen selbstständigen energetischen Heilbetrieb (1-Mann-Betrieb).
Der Betreiber arbeitet mit Klienten, die zu ihm kommen: Heilarbeit, Meditation,
Chakrenausgleich und Ähnliches. Das Programm verwaltet Klienten und dokumentiert die
Sitzungen. Es läuft auf einem Windows-11-Laptop, die Daten liegen verschlüsselt auf
einer externen USB-Platte und nie auf dem Laptop selbst.

Der Anwender ist kein Techniker. Die Oberfläche ist bewusst einfach und durchgehend
deutsch; im Programm heißt es immer „Klient", nie „Kunde".

**Wichtig:** Die Sitzungsnotizen enthalten Angaben zu Gesundheit und Befinden, also
besondere Kategorien personenbezogener Daten nach DSGVO Art. 9. Daraus folgt:
Verschlüsselung ist zwingend, Löschen muss vollständig sein, und beim Testen werden
ausschließlich erfundene Daten verwendet.

---

## Technischer Stand

**Stack:** Python 3.12+ mit `uv`, PySide6 (Qt), SQLAlchemy 2.x, Alembic, SQLite mit
SQLCipher, pytest, ruff, PyInstaller, Git.

**Architektur:** vier Schichten, jede spricht nur mit der direkt darunter.
`ui/` → `services/` (Geschäftslogik, kennt kein Qt) → `repositories/` (einziger Ort
mit Datenbankabfragen) → `models/`. Ziel: Services und Repositories sollen bei einem
späteren Umzug auf einen Server (PostgreSQL, Web-API) unverändert weiterlaufen.

**Datenmodell:** fünf Tabellen.
- `client` – Stammdaten, Anliegen, Notizen, Einwilligungsdatum, `archived`
- `treatment_type` – Behandlungsarten, frei pflegbar, `active` statt Löschen
- `session` – Sitzungen mit Datum (minutengenau), Pflicht-Dauer (höchstens 8 Std.),
  Bericht und Impulse (formatierter Text, HTML); Klient löschen löscht Sitzungen mit
  (Cascade), verwendete Behandlungsart ist nicht löschbar (Restrict)
- `media` / `session_media` – Mediendateien im Ordner `medien` der Datenplatte (UUID-Namen,
  SHA-256 zur Duplikaterkennung) und ihre Zuordnung zu Sitzungen (eine Datei kann mehreren
  Sitzungen gehören)

Annahme, noch unbestätigt: eine Sitzung hat genau eine Behandlungsart.

**Speicherung:** Die Datenplatte wird über eine Kennungsdatei (`klientenverwaltung.id`
mit UUID) gefunden, nicht über den Laufwerksbuchstaben. Die Datenbank ist mit
SQLCipher verschlüsselt, Passwortabfrage bei jedem Start, Passwortwechsel über
„Einstellungen → Passwort ändern“ (ohne Neustart). Die UUID der Platte merkt sich der
Laptop; eine andere Datenplatte wird nur nach Rückfrage verwendet.
Eine zusätzliche Plattenverschlüsselung mit BitLocker wurde bewusst verworfen, solange
auf der Platte nur die verschlüsselte Datenbank liegt (zwei Passwörter im Alltag sind
in der Praxis unsicherer als eines). Sobald dort andere Dokumente abgelegt werden,
muss BitLocker dazu.

**Sicherungen:** frei wählbarer Ordner, Kopie per `VACUUM INTO`, Rotation auf zehn
Stände, eigener Unterordner für Kopien vor einer Wiederherstellung (in der Liste als
„Vor Wiederherstellung“ selbst wiederherstellbar), zwingende Sicherung vor jeder
Migration, automatisch beim Start und beim Beenden (nur bei Änderungen). Eine Kopie auf
der Datenplatte selbst zählt nicht als Sicherung; ohne Sicherungsordner erinnert das
Programm wöchentlich. Wiederherstellung prüft die Sicherung vorher und stellt Sicherungen
von vor einer Passwortänderung auf das aktuelle Passwort um. Mediendateien werden nicht
gesichert.

---

## Funktionsumfang (fertig und getestet)

- Klientenliste mit Suche, Filter für archivierte Klienten, Spalten „letzte Sitzung"
  (jüngste in der Vergangenheit) und „nächster Termin" (nächster in der Zukunft);
  Rechtsklick-Kontextmenü (Ansicht, Bearbeiten, Archivieren/Wiederherstellen, Löschen)
- Klient anlegen, bearbeiten, archivieren, endgültig löschen; automatische
  Vereinheitlichung der Groß-/Kleinschreibung bei Namen, Straße und Ort
- Klientenübersicht (reine Ansicht, kein Formular) über Doppelklick oder
  Kontextmenü „Ansicht": Adressblock im Briefstil, Alter, „Klient seit", Anliegen/
  Notizen/weitere Angaben (jeweils nur wenn vorhanden), letzte/nächste Sitzung;
  Buttons „Berichte (n)", „Sitzungen (n)", „Bearbeiten" *(Phase B)*
- Sitzungen in einem eigenen Fenster je Klient, erreichbar über einen Button im
  Klientenfenster, der Anzahl und Datum der letzten Sitzung anzeigt
- Überlappende Termine werden beim Speichern abgelehnt; direkt aneinander
  anschließende Termine sind erlaubt
- Bericht und Impulse je Sitzung in einem eigenen Formularfenster, mit Formatierung
  (fett/kursiv/unterstrichen/Überschriften), Text immer in der Theme-Farbe, robust
  gegen aus Word eingefügten formatierten Text *(Phase A)*
- Berichtsverlauf je Klient (reine Ansicht): alle Sitzungen mit Bericht oder
  Impulsen, neueste zuerst, zwei Spalten nebeneinander mit der gespeicherten
  Formatierung, leere Seite zeigt „–" statt leerer Fläche *(Phase B)*
- Medien je Sitzung (Auftrag C1), Medienübersicht mit Umbenennen, „Aus vorhandenen
  Medien“ und Rückfrage bei nicht mehr verwendeten Dateien (Auftrag C2)
- Behandlungsarten pflegen, deaktivieren statt löschen; keine Standard-Arten beim
  Einrichten (Auftrag D1)
- Einrichtungsassistent beim ersten Start (Platte, Passwort, Sicherungsordner)
- Light- und Dark-Theme in warmen Tönen, umschaltbar über Statusleiste und Menü
- Logo, Splash Screen, Über-Dialog mit Version
- Auslieferung als eigenständige .exe plus Debug-Variante mit Konsole

Aktueller Stand: alle Befunde aus `CODE_REVIEW.md` umgesetzt, über 350 Tests grün,
ruff (Lint und Format) sauber. Die gebaute `.exe` ist nach den Review-Änderungen noch
einmal auf einem Rechner ohne Python zu prüfen.

---

## Bewusst getroffene Entscheidungen

Diese Punkte wurden diskutiert und so entschieden. Wer sie ändern will, sollte den
Grund kennen.

- **Kein automatischer Neustart nach einer Wiederherstellung.** Ein aus der .exe
  heraus gestarteter Neuprozess findet die Qt-Plugins nicht zuverlässig, weil
  PyInstaller sie in einen temporären Ordner entpackt, den die beendende Instanz
  löscht. Vier Anläufe, dann verworfen. Stattdessen: Hinweistext und Beenden.
- **Kein SVG zur Laufzeit.** `PySide6.QtSvg` ließ sich nicht zuverlässig bündeln.
  SVG bleibt Quellformat, wird beim Build in PNG umgewandelt.
- **Keine Terminverwaltung im MVP.** Zukünftige Sitzungen erscheinen als „nächster
  Termin", mehr nicht.
- **Keine Abrechnung.** Läuft beim Anwender woanders; das Schema lässt sich per
  Alembic erweitern (Standardpreis in `treatment_type`, Tabelle `payment`). Dann
  greifen Aufbewahrungsfristen und Klienten mit Abrechnungen dürfen nicht mehr
  vollständig gelöscht werden.
- **Feste Spaltenauswahl statt Konfiguration**, Spaltenbreiten werden aber gespeichert.
- **Titelleisten der Fenster werden nicht angepasst** (Windows-Systemelement).

---

## Offene Punkte

- **Verschlüsselung der Mediendateien** klären (BitLocker To Go / VeraCrypt), bevor
  echte Aufnahmen gespeichert werden – siehe `TODO.md`.
- **Terminübersicht/Kalender** – vom Anwender gewünscht, noch nicht gebaut. Geplant
  war zunächst die schlanke Variante: Liste aller kommenden Termine über alle
  Klienten mit Umschaltung auf Vergangenheit, dazu ein Statusfeld für Sitzungen
  (vereinbart, wahrgenommen, abgesagt, nicht erschienen). Monatsraster erst danach
  entscheiden.
- **Vor der Übergabe:** Testdaten restlos entfernen, Passwort vom Anwender selbst
  vergeben lassen (der Entwickler sollte es nicht kennen), Wiederherstellung einmal
  gemeinsam durchspielen.
- **Rechtliches, falls es ernst wird:** Auftragsverarbeitungsvertrag, sobald bei der
  Unterstützung echte Klientendaten sichtbar werden; Gewerbefragen, falls das Programm
  an weitere Praxen gehen soll.
- **Name:** bleibt vorerst „Klientenverwaltung". Bei einer späteren Umbenennung sind
  besonders die QSettings-Schlüssel kritisch, weil bestehende Nutzer sonst ihre
  Einstellungen verlieren.

---

## Arbeitsweise, die sich bewährt hat

- **Hier wird entschieden, in Claude Code wird gebaut.** Anforderungen, Datenmodell
  und Architektur im Chat klären, Entscheidungen in die `CLAUDE.md` schreiben,
  Umsetzung in Claude Code.
- **Aufträge eng fassen**, einzeln abarbeiten, nach jedem testen.
- **Jeden wiederkehrenden Fehler als Regel in die `CLAUDE.md`**, nicht nur den Fix
  im Code. Besonders Qt-Stylesheets setzen native Darstellung außer Kraft und haben
  das mehrfach nötig gemacht.
- **Bei hartnäckigen Fehlern zuerst den Ist-Zustand zeigen lassen:** „Zeig mir alle
  Stellen, an denen X gesetzt wird, ändere noch nichts." Das hat mehr gebracht als
  weitere Reparaturversuche.
- **Neue Funktionen erst nach Rücksprache mit dem Anwender bauen**, nicht auf Verdacht.
- **Das Risiko zuerst angehen** und jede Änderung am Build auf einem Rechner ohne
  Python prüfen.
