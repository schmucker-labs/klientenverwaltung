# Klientenverwaltung

Desktop-Anwendung zur Klientenverwaltung für einen 1-Mann-Betrieb (energetische Heilarbeit:
Heilsitzungen, Meditation, Chakrenausgleich u. Ä.). Einzelner Nutzer, ein Windows-11-Laptop.
Die Daten liegen verschlüsselt auf einer externen USB-Festplatte, nicht auf dem Laptop.

## Tech-Stack

- Python 3.12+, Umgebung und Abhängigkeiten mit `uv`
- GUI: PySide6 (Qt)
- ORM: SQLAlchemy 2.x (typisierte `Mapped[...]`-Syntax)
- Migrationen: Alembic (werden beim Programmstart automatisch angewendet)
- Datenbank: SQLite, verschlüsselt mit SQLCipher
- Tests: pytest; Linting/Formatierung: ruff
- Auslieferung: PyInstaller (.exe)
- Versionsverwaltung: Git

## Sprache und Konventionen

- Code, Bezeichner, Tabellen, Spalten, Commit-Messages: Englisch
- Alles, was der Nutzer sieht (Oberfläche, Fehlermeldungen): Deutsch
- In der Oberfläche heißt es immer "Klient", nie "Kunde"
- Datumsformat in der Oberfläche: TT.MM.JJJJ
- Typ-Hinweise überall, ruff muss fehlerfrei durchlaufen
- Oberfläche bewusst einfach halten: Anwender ist kein Techniker

## Architektur

Strikte Schichten, jede spricht nur mit der direkt darunter:

1. `ui/` – PySide6-Fenster und Dialoge. Keine Geschäftslogik, kein Datenbankzugriff.
2. `services/` – Geschäftslogik und Validierung. Kennt keine Qt-Klassen.
3. `repositories/` – einziger Ort mit SQLAlchemy-Sessions und Abfragen.
4. `models/` – SQLAlchemy-Modelle.

Ziel: Services und Repositories sollen später unverändert hinter einer Web-API (z. B. FastAPI)
laufen können, falls die Datenbank auf einen Server (PostgreSQL) umzieht. Deshalb keine
SQLite-spezifischen Abfragen in Repositories, außer in `storage.py`.

```
klientenverwaltung/
├── CLAUDE.md
├── pyproject.toml
├── alembic/
├── src/klientenverwaltung/
│   ├── main.py          # Einstiegspunkt
│   ├── config.py        # Einstellungen (liegen unter %APPDATA%, KEINE Klientendaten)
│   ├── storage.py       # USB-Platte finden, verschlüsselte Verbindung aufbauen
│   ├── models/
│   ├── repositories/
│   ├── services/
│   └── ui/
└── tests/
```

## Datenmodell

### client
| Spalte | Typ | Hinweis |
|---|---|---|
| id | int PK | automatisch, dient als Klientennummer |
| salutation | str, optional | |
| first_name | str | Pflicht |
| last_name | str | Pflicht |
| birth_date | date, optional | |
| street | str, optional | |
| postal_code | str, optional | als Text (führende Null!) |
| city | str, optional | |
| phone | str, optional | als Text |
| email | str, optional | |
| concern | text, optional | Anliegen beim Erstkontakt |
| referral_source | str, optional | wie auf den Betrieb aufmerksam geworden |
| consent_date | date, optional | Datum der Datenschutz-Einwilligung |
| notes | text, optional | allgemeine Notizen |
| archived | bool | Standard False |
| created_at, updated_at | datetime | automatisch |

### treatment_type
| Spalte | Typ | Hinweis |
|---|---|---|
| id | int PK | |
| name | str, eindeutig | z. B. "Chakrenausgleich" |
| description | text, optional | |
| active | bool | Standard True; deaktivieren statt löschen |

### session
| Spalte | Typ | Hinweis |
|---|---|---|
| id | int PK | |
| client_id | FK → client.id | Pflicht, ON DELETE CASCADE |
| treatment_type_id | FK → treatment_type.id | Pflicht, ON DELETE RESTRICT |
| date | datetime | |
| duration_minutes | int, optional | |
| notes | text, optional | Beobachtungen, Verlauf |
| created_at, updated_at | datetime | automatisch |

Hinweis: Der Name `session` kollidiert leicht mit SQLAlchemy-Sessions. Im Code die Modellklasse
z. B. `TreatmentSession` nennen, Tabellenname bleibt `session`.

### Regeln
- Klient löschen löscht alle zugehörigen Sitzungen (Gesundheitsdaten dürfen nicht verwaist
  zurückbleiben). Endgültiges Löschen immer mit Sicherheitsabfrage; Alltag = archivieren.
- Behandlungsart, die in Sitzungen verwendet wird, darf nicht gelöscht werden, nur deaktiviert.
  Deaktivierte Arten erscheinen nicht in der Auswahl für neue Sitzungen, bleiben in der Historie.
- Annahme: 1 Sitzung = genau 1 Behandlungsart (siehe offene Punkte).

## Speicherung, Verschlüsselung, Sicherheit

- Die Daten enthalten Gesundheitsangaben (DSGVO Art. 9). Klientendaten dürfen NIE unverschlüsselt
  auf die Laptop-Festplatte geschrieben werden: keine Temp-Dateien, keine Logs mit Inhalten,
  keine unverschlüsselten Exporte ohne ausdrückliche Nutzeraktion.
- USB-Platte wird über eine Kennungsdatei (`klientenverwaltung.id`, enthält eine UUID) gefunden,
  indem alle Laufwerke durchsucht werden. Laufwerksbuchstaben nie fest verdrahten.
- Platte nicht gefunden: verständlicher Dialog "Bitte Datenplatte anschließen" mit
  "Erneut versuchen".
- Datenbank mit SQLCipher verschlüsselt, Passwortabfrage bei jedem Start.
- Erster Start: Einrichtungsassistent (Platte wählen, Passwort doppelt eingeben, Mindestlänge
  12 Zeichen, deutlicher Hinweis: Passwort verloren = Daten verloren, Bestätigung erforderlich).
- Menüpunkt "Passwort ändern" (Rekey).
- Bei jeder Verbindung: `PRAGMA foreign_keys = ON` und `PRAGMA synchronous = FULL`.
- Das Passwort nie speichern oder loggen.

## MVP-Umfang

- Klientenliste mit Suche (Name, Ort), Filter "Archivierte anzeigen"
- Klient anlegen, bearbeiten, archivieren, endgültig löschen
- Detailansicht eines Klienten mit Sitzungsliste (neueste zuerst)
- Sitzung anlegen, bearbeiten, löschen
- Behandlungsarten pflegen (anlegen, umbenennen, deaktivieren)
- Start-Ablauf: Platte suchen → Passwort → Migrationen anwenden → Hauptfenster

Nicht im MVP: Abrechnung, Termine/Erinnerungen, Export, Statistiken.

## Vorgehen / Reihenfolge

1. Projektsetup (uv, ruff, pytest, Git)
2. **Risiko-Prototyp zuerst:** Minimalskript, das eine SQLCipher-Datenbank über SQLAlchemy
   anlegt, liest und schreibt – und mit PyInstaller zu einer .exe gebaut unter Windows läuft.
   Erst wenn das funktioniert, weiterbauen.
3. Modelle + Alembic-Grundmigration
4. Repositories + Services mit Tests
5. storage.py (Platte finden, Verbindung, Einrichtung)
6. Oberfläche
7. PyInstaller-Build der vollständigen Anwendung

## Offene Punkte

- Können mehrere Behandlungsarten in einer Sitzung vorkommen? Falls ja: Zwischentabelle
  `session_treatment` per Alembic-Migration nachrüsten.
- Abrechnung später möglich: vermutlich Standardpreis in `treatment_type`, neue Tabelle
  `payment`. Dann Aufbewahrungspflichten beachten (Klienten mit Abrechnungen nicht komplett
  löschbar).
- Backup-Konzept (Schritt 8): Zeitpunkt, Ziel, Anzahl Versionen.
- Hat der Laptop Windows 11 Pro? Dann zusätzlich BitLocker To Go auf der Datenplatte.
- Mögliche spätere Migration auf Server (PostgreSQL + Web-API).
- Terminverwaltung noch offen.

## UI-Regeln
Nicht gespeicherte Änderungen abfangen. Wer ein Formular mit Änderungen schließt, bekommt "Möchten Sie die Änderungen speichern?". Sitzungsnotizen, die beim versehentlichen Schließen verschwinden, sind der sicherste Weg, das Vertrauen in das Programm zu verlieren.
Service-Fehler abfangen und die deutsche Meldung in einer QMessageBox zeigen. Niemals ein Traceback.
Ausreichend große Schrift und Klickflächen. Der Anwender ist kein Techniker und sitzt eventuell nicht optimal vor dem Bildschirm.
Keine Geschäftslogik in der Oberfläche. Wenn Claude Code anfängt, im Fenstercode zu validieren, gehört das in die Services.
Tastatur nicht vergessen: Enter speichert, Escape schließt, Tab läuft in sinnvoller Reihenfolge durch die Felder. Bei Dateneingabe spart das spürbar Zeit.

- Jedes Fenster und jeder Dialog merkt sich Fenstergröße, Position, Spaltenbreiten,
  Sortierung und Splitter-Aufteilung über QSettings unter einem eigenen Schlüssel.
  Dafür die gemeinsame Hilfsfunktion in ui/ verwenden, nicht pro Dialog neu bauen.
  Gilt auch für jeden neu hinzukommenden Dialog.
- Beim ersten Öffnen ohne gespeicherte Werte: sinnvolle Standardgröße, bei der alle
  Inhalte lesbar sind. Tabellenspalten einmalig am Inhalt ausrichten. Gespeicherte
  Werte, die unbrauchbar sind (z. B. Höhe 0, Fenster außerhalb des Bildschirms),
  werden verworfen und durch die Standardwerte ersetzt.
- Mindestbreite pro Tabellenspalte, damit Spalten nicht auf null gezogen werden können.
- Keine Tabellenspalte dauerhaft auf ResizeMode.Stretch: Eine gestreckte Spalte hat
  keinen eigenen Ziehgriff, dadurch verschiebt sich die Zuordnung aller folgenden
  Trenner um eine Position. Stattdessen alle Spalten Interactive und die Startbreiten
  beim ersten Öffnen einmalig berechnen, sodass sie die Tabellenbreite ausfüllen
- Tabellenbreite an die Fensterbreite koppeln: Beim Ändern der Fenstergröße die
  Differenz proportional auf die Spalten verteilen, damit rechts weder ein leerer
  Streifen bleibt noch die Tabelle über den Fensterrand hinausragt. Mindestbreiten
  einhalten. Beim automatischen Anpassen kein Speichern in QSettings auslösen
  (sonst Endlosschleife über sectionResized).
- Tabellen füllen immer exakt die verfügbare Breite: linker Rand der ersten und rechter
  Rand der letzten Spalte sitzen fest am Fensterrand. Am rechten Rand der letzten Spalte
  gibt es keinen Ziehgriff. Ein Trenner ändert nur die Aufteilung zwischen Spalten,
  nie die Gesamtbreite; der Platz wird von den Nachbarspalten geholt oder an sie
  abgegeben, bis zur Mindestbreite. Dabei darf keine Spalte auf Stretch stehen, sonst
  verrutscht die Zuordnung der Trenner (siehe oben). Beim automatischen Anpassen kein
  Speichern in QSettings auslösen.
  - Farben nie direkt im UI-Code, sondern ausschließlich über die zentral definierten
  Farbvariablen des aktiven Themes. Jedes Theme definiert vollständig: Hintergrund,
  Flächen, Text, Sekundärtext, Akzent, Sekundärakzent, Linien, Hover, markierte Zeile
  (Hintergrund + Text), Fehler-/Warnfarbe, deaktivierte Elemente, Fokusrahmen,
  archivierte Einträge. Stylesheets setzen nur Farben, nie Abstände oder Schriftgrößen.
  - Qt-Stylesheets ersetzen den nativen Windows-Stil eines Elements vollständig, sobald
  sie es anfassen: Innenabstände, Rundungen und Zustandsdarstellung gehen verloren und
  müssen ausdrücklich mitgesetzt werden. Für jedes gestylte Element daher auch
  border-radius, padding, min-height sowie die Zustände hover, pressed, focus und
  disabled definieren.
- Fenster-Titelleisten werden nicht angepasst (Windows-Systemelement).
- Ein Theme-Wechsel muss zur Laufzeit auf alle offenen Fenster und Dialoge wirken,
  nicht nur auf das Hauptfenster, und ohne Neustart greifen.