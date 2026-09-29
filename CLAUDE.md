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
- Öffentliches Portfolio-Repo: Commit-Messages ohne `Co-Authored-By: Claude`-Trailer
  (GitHub würde das sonst als Contributor auf dem Repo anzeigen)

## Architektur

Strikte Schichten, jede spricht nur mit der direkt darunter:

1. `ui/` – PySide6-Fenster und Dialoge. Keine Geschäftslogik, kein Datenbankzugriff.
2. `services/` – Geschäftslogik und Validierung. Kennt keine Qt-Klassen.
3. `repositories/` – einziger Ort mit SQLAlchemy-Sessions und Abfragen.
4. `models/` – SQLAlchemy-Modelle.

Ziel: Services und Repositories sollen später unverändert hinter einer Web-API (z. B. FastAPI)
laufen können, falls die Datenbank auf einen Server (PostgreSQL) umzieht. Deshalb keine
SQLite-spezifischen Abfragen in Repositories, außer in `storage.py`.

Dazu gehört:
- Services geben nur einfache Werte zurück (frozen dataclasses wie `ClientDetails`,
  `SessionEntry`, `TreatmentTypeEntry`, `StoredMedia`), nie ORM-Objekte. `ui/` importiert
  weder `models` noch `repositories`, `services/`/`repositories/` kein Qt - geprüft von
  `tests/test_architecture.py`.
- Jede öffentliche Service-Methode übersetzt SQLAlchemy-Fehler in einen `ServiceError`
  (`database_errors_as` bzw. `transaction()`), eine getrennte Datenplatte in
  `DataUnavailableError`. Ein nirgends abgefangener `ServiceError` erscheint als normale
  Meldung, das Programm läuft weiter.
- Textsuche passiert im Service (`services/search.py`: Groß-/Kleinschreibung und Umlaute
  egal, alle Suchbegriffe müssen passen) - SQLites `LIKE` kennt nur ASCII.
- `app_context.py` bündelt die Services (`AppServices`) und die offene Datenbank
  (`OpenDatabase`, inkl. Passwortwechsel) für die Oberfläche; gebaut in `main.py`.

```
klientenverwaltung/
├── CLAUDE.md
├── pyproject.toml
├── alembic/
├── src/klientenverwaltung/
│   ├── main.py          # Einstiegspunkt
│   ├── config.py        # Einstellungen (liegen unter %APPDATA%, KEINE Klientendaten)
│   ├── storage.py       # USB-Platte finden, verschlüsselte Verbindung, Migrationen
│   ├── backup.py        # Sicherungen erstellen, auflisten, wiederherstellen
│   ├── app_context.py   # AppServices + OpenDatabase für die Oberfläche
│   ├── crash_log.py     # error.log ohne Meldungstexte (keine Klientendaten)
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
| date | datetime | minutengenau (der Service kürzt Sekunden), naive lokale Zeit |
| duration_minutes | int | Pflicht, 1 bis 480 (8 Stunden) |
| report | text, optional | HTML, aus dem Berichtsfenster (Auftrag A2); leerer Inhalt wird als NULL gespeichert |
| impulses | text, optional | HTML, aus dem Berichtsfenster (Auftrag A2); leerer Inhalt wird als NULL gespeichert |
| created_at, updated_at | datetime | automatisch |

Hinweis: Der Name `session` kollidiert leicht mit SQLAlchemy-Sessions. Im Code die Modellklasse
z. B. `TreatmentSession` nennen, Tabellenname bleibt `session`.

### media
| Spalte | Typ | Hinweis |
|---|---|---|
| id | int PK | |
| stored_filename | str, eindeutig | UUID + Originalendung, relativ zum Medienordner |
| original_filename | str | ursprünglicher Dateiname, nur zur Anzeige |
| media_kind | str | "image"/"video"/"audio"/"other", aus der Endung bestimmt |
| size_bytes | int | |
| sha256 | str | für die Duplikat-Erkennung beim Import |
| created_at | datetime | automatisch |

### session_media
| Spalte | Typ | Hinweis |
|---|---|---|
| session_id | FK → session.id | Pflicht, ON DELETE CASCADE, Teil des Primärschlüssels |
| media_id | FK → media.id | Pflicht, ON DELETE RESTRICT, Teil des Primärschlüssels |
| added_at | datetime | automatisch, wann diese Sitzung mit der Datei verknüpft wurde |

### Regeln
- Zeitstempel: `session.date`, `media.created_at` und `session_media.added_at` sind naive
  lokale Zeit (Python-Default). `created_at`/`updated_at` von `client` und `session` sind
  UTC (SQLites `CURRENT_TIMESTAMP`) - für die Anzeige umrechnen (siehe
  `ClientService.client_since_date`). Neue Zeitstempel als naive lokale Zeit.
- Namen von Behandlungsarten sind ohne Beachtung der Groß-/Kleinschreibung eindeutig.
- Klient löschen löscht alle zugehörigen Sitzungen (Gesundheitsdaten dürfen nicht verwaist
  zurückbleiben). Endgültiges Löschen immer mit Sicherheitsabfrage; Alltag = archivieren.
- Behandlungsart, die in Sitzungen verwendet wird, darf nicht gelöscht werden, nur deaktiviert.
  Deaktivierte Arten erscheinen nicht in der Auswahl für neue Sitzungen, bleiben in der Historie.
- Beim Einrichten einer neuen Datenplatte werden keine Standard-Behandlungsarten angelegt;
  der Anwender legt seine Arten selbst an. Gibt es bei "Neue Sitzung" keine aktive
  Behandlungsart (keine angelegt oder alle deaktiviert), erscheint vor dem Sitzungsdialog
  ein Hinweis mit der Möglichkeit, direkt eine Behandlungsart anzulegen.
- Annahme: 1 Sitzung = genau 1 Behandlungsart (siehe offene Punkte).
- "Letzte Sitzung" ist immer die jüngste Sitzung mit Datum in der VERGANGENHEIT,
  "Nächster Termin"/"Nächste Sitzung" die nächste in der Zukunft. Beide Werte kommen
  aus derselben Repository-Abfrage und werden nirgends erneut berechnet.
- Mediendateien liegen im Ordner "medien" auf der Datenplatte, benannt mit einer
  UUID statt dem Originalnamen. Eine Datei kann mehreren Sitzungen zugeordnet sein
  (Duplikate werden über den Dateiinhalt/SHA-256 erkannt, nie erneut kopiert).
  Das Original bleibt immer unverändert, wo der Anwender es ausgewählt hat -
  das Programm löscht es nie.
- Mediendateien werden NIE automatisch gelöscht, nur nach ausdrücklicher
  Bestätigung des Anwenders. Sitzung löschen, Klient endgültig löschen und
  "Verknüpfung entfernen" im Medienfenster entfernen zunächst nur die
  Verknüpfung (`session_media`); wird eine Datei dadurch von keiner Sitzung
  mehr verwendet, fragt das Programm danach einmal, ob sie jetzt endgültig
  gelöscht werden soll (Auftrag C2) - "Behalten" lässt sie unverändert liegen,
  sichtbar in der Medienübersicht als 0×. Gilt NICHT für Archivieren. Die
  Medienübersicht (Menü "Einstellungen") zeigt jede Datei, ihre Verwendung
  und erkennt beide Abweichungen zwischen Medienordner und Datenbank: einen
  DB-Eintrag ohne Datei ("Datei fehlt") und eine Datei ohne DB-Eintrag
  ("Unbekannte Datei").

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
- Menüpunkt "Passwort ändern" (Einstellungen; SQLCipher-Rekey, vorher eine Sicherung).
  Ältere Sicherungen behalten ihr damaliges Passwort; beim Wiederherstellen fragt das
  Programm danach und stellt die Daten auf das aktuelle Passwort um.
- Bei jeder Verbindung: `PRAGMA foreign_keys = ON` und `PRAGMA synchronous = FULL` -
  außer während Migrationen (`storage.foreign_keys_disabled`, siehe docs/build.md).
- Das Passwort nie speichern oder loggen. Es wird per `URL.create` an SQLAlchemy übergeben,
  nie in einen URL-String eingesetzt (Sonderzeichen wie `@` oder `%41`). Engines laufen mit
  `hide_parameters=True`; `error.log` enthält nur Ausnahmetypen und Codestellen, nie
  Meldungstexte (`crash_log.py`).
- Die UUID der verwendeten Datenplatte wird in `config.json` gemerkt; eine andere
  Datenplatte wird nur nach Rückfrage verwendet. Eine Platte mit Kennungsdatei, aber ohne
  Datenbank ist eine abgebrochene Einrichtung und wird vom Assistenten abgeschlossen.
- Sicherungen: automatisch beim Start (vor Migrationen immer) und beim Beenden, jeweils nur
  bei Änderungen, in den Sicherungsordner; eine Kopie auf der Datenplatte selbst zählt
  nicht als Sicherung. Ohne Sicherungsordner erinnert das Programm höchstens wöchentlich.
  Eine Wiederherstellung prüft die Sicherung vorher und legt eine Sicherheitskopie an
  (in der Liste als "Vor Wiederherstellung" wieder herstellbar).
- Es läuft immer nur eine Instanz (Sperrdatei in %APPDATA%).
- Mediendateien werden nur kopiert, nie verschoben oder gelöscht, und liegen
  unverschlüsselt im Ordner "medien" auf der Datenplatte - ihr Schutz hängt
  bis auf Weiteres von der Verschlüsselung der ganzen Datenplatte ab (siehe
  TODO.md, "Vor der Übergabe"). Sie sind nicht Teil der Sicherungen.

## Build & Auslieferung

Siehe [docs/build.md](docs/build.md) für PyInstaller-Hidden-Imports, Icon-/Asset-Erzeugung
und die zwei Build-Varianten – lesen, bevor an Build-Konfiguration, einem neuen Qt-Modul
oder einer neuen Alembic-Migration gearbeitet wird.

## Vorgehen / Reihenfolge

Schritte 1–7 (Projektsetup; Risiko-Prototyp für SQLCipher+SQLAlchemy+PyInstaller;
Modelle + Alembic-Grundmigration; Repositories + Services mit Tests; storage.py;
Oberfläche; PyInstaller-Build) sind abgeschlossen. Weitere Arbeit läuft über TODO.md.

## Offene Punkte

- Können mehrere Behandlungsarten in einer Sitzung vorkommen? Falls ja: Zwischentabelle
  `session_treatment` per Alembic-Migration nachrüsten.
- Abrechnung später möglich: vermutlich Standardpreis in `treatment_type`, neue Tabelle
  `payment`. Dann Aufbewahrungspflichten beachten (Klienten mit Abrechnungen nicht komplett
  löschbar).

## UI-Regeln

Siehe [docs/ui-regeln.md](docs/ui-regeln.md) für alle Regeln zu Fenstern, Dialogen,
Tabellen und Theming – lesen, bevor ein neues Fenster, ein neuer Dialog oder ein neues
Stylesheet entsteht.