# Code Review

> **Klientenverwaltung – Tiefenreview (reine Analyse, keine Codeänderungen)**
> Stand: Commit `820aeff` (Branch `master`) zuzüglich der nicht committeten Änderung in
> `src/klientenverwaltung/ui/client_sessions_dialog.py` (Beispieltext „Meditation" statt
> „Chakrenausgleich"), 29.09.2026.

### Grundlage und Methodik

- **Vollständig gelesen:** alle Dateien unter `src/`, `alembic/` (inkl. aller Migrationen),
  `scripts/`, beide `.spec`-Dateien, `pyproject.toml`, `alembic.ini`, `README.md`, `CLAUDE.md`,
  `TODO.md`, `docs/*.md`, `tests/conftest.py` sowie die vollständige Testliste und ausgewählte Tests.
- **Ausgeführt** (ohne Projektdateien zu verändern: Bytecode- und Cache-Schreiben abgeschaltet,
  Hilfsdateien nur im temporären Scratchpad, `git status` vorher/nachher identisch):
  - `pytest -p no:cacheprovider` → **198 Tests grün** (10,9 s)
  - `ruff check --no-cache .` → fehlerfrei; `ruff format --check --no-cache .` → 28 Dateien
    (davon 20 Python-Dateien) würden umformatiert
  - Gezielte Nachweise einzelner Befunde: URL-Parsing des Passworts, SQLite-`ilike` mit Umlauten,
    FK-Kaskade beim Tabellen-Neuaufbau, `QDateTimeEdit` mit versteckten Sekunden, Einfügeverhalten
    des Berichtseditors, Laufwerkssuche mit hängendem Laufwerk, Qt-Standard-Sortierindikator,
    gerendertes Theme (Hell/Dunkel)
- **Nicht geprüft:** die gebaute `.exe`, echte USB-Hardware/Laufwerkstrennung, echte
  Bedienung der Oberfläche (nur Offscreen- bzw. Render-Proben).

**Legende „Art":** *Bestätigtes Problem* = im aktuellen Code nachweisbar · *Mögliches Problem* =
tritt abhängig von Nutzung/Weiterentwicklung auf · *Empfehlung* = Verbesserung ohne akuten Fehler ·
*Präferenz* = Stilfrage (wird nur am Rand erwähnt, nicht gezählt).

---

## Executive Summary

Das Projekt ist für eine Ein-Personen-Desktopanwendung in einem **auffallend guten Zustand**:
saubere Schichtentrennung, fachlich durchdachte Lösch- und Archivierungsregeln, robuste
Sicherungs- und Wiederherstellungsmechanik (`VACUUM INTO`, Rotation, atomares Ersetzen,
Pflichtsicherung vor Migrationen), ein sorgfältig gebauter Medienimport (ein Lesedurchgang für
Hash + Kopie, `.part`-Dateien, Abbruch, Duplikaterkennung, korrekte Thread-Verdrahtung),
außergewöhnlich gute Docstrings, die das *Warum* erklären, und 198 schnelle, grüne Tests.
Im normalen Betrieb wurde **kein kritischer Fehler** gefunden, der aktuell Daten vernichtet.

Die wichtigsten Befunde:

1. **H-1 – Passwort in der Datenbank-URL:** Ein Passwort mit `@` bringt die Einrichtung zum
   Absturz, hinterlässt eine halb eingerichtete Datenplatte und schreibt einen Teil des Passworts
   im Klartext in `error.log` auf dem Laptop. `%XX`-Sequenzen verändern den Schlüssel stillschweigend.
2. **H-2 – Klientendaten im Absturzprotokoll:** SQLAlchemy übernimmt SQL-Parameter in
   Ausnahmetexte; der Crash-Handler schreibt diese unverschlüsselt auf den Laptop.
3. **H-3 – Latente Datenverlust-Falle bei Migrationen:** Wegen `PRAGMA foreign_keys = ON` löscht
   jede künftige Alembic-Batch-Migration, die `client` oder `session` neu aufbaut, per Kaskade
   alle Sitzungen bzw. Medien-Verknüpfungen – stumm. Muss vor der nächsten Schemaänderung behoben
   werden (geplant sind Statusfeld, `session_treatment`, `client_number`).
4. **H-4 – Versteckte Sekunden in Terminzeiten** führen zufällig zu falschen
   „Überschneidungs"-Fehlern bei direkt aneinander anschließenden Terminen.

Weitere Schwerpunkte: unvollständige Fehlergrenze der Services (Lesefehler, Abziehen der Platte →
generischer Absturzdialog), wirkungsloser Timeout der Laufwerkssuche, nicht erreichbare
Sicherheitskopie bei der Wiederherstellung, fehlendes „Passwort ändern", Suche ohne
Umlaut-/Vollnamen-Unterstützung, Einfügen aus Word übernimmt Bildverweise auf Laptop-Dateien,
einige Theme-/Barrierefreiheitsmängel.

---

## Project Overview

### Zweck und Rahmen
Desktop-Anwendung zur Klientenverwaltung für einen Ein-Personen-Betrieb (energetische Heilarbeit).
Ein Anwender, ein Windows-11-Laptop, kein technischer Hintergrund. Gesundheitsbezogene Daten
(DSGVO Art. 9) liegen verschlüsselt auf einer externen USB-Platte.

### Technologie
| Bereich | Umsetzung |
|---|---|
| Sprache/Umgebung | Python ≥ 3.12, `uv` (`uv.lock`), Build-Backend `uv_build` |
| GUI | PySide6 6.11.2 (Qt Widgets), zentrales Stylesheet (`ui/theme.py`) |
| Persistenz | SQLAlchemy 2.0.54 (typisierte `Mapped[...]`), SQLite + SQLCipher (`sqlcipher3-wheels` 0.5.7), Alembic 1.20.0 |
| Tests/Linting | pytest 9.1.1, ruff 0.16.8 (Standardregelsatz) |
| Auslieferung | PyInstaller 6.22.3, Onefile-Build, Release- und Debug-Variante |
| CI/CD | keine |

### Startablauf (`klientenverwaltung.main:main`)
```
sys.excepthook -> QSettings-Organisation -> [--reset-settings] -> QApplication (+2 pt, Theme)
-> Splash (Fade-in) -> _run_startup():
     storage.find_data_drive()  (Kennungsdatei klientenverwaltung.id, alle Laufwerke)
        |- nicht gefunden -> "Erneut versuchen" / Einrichtungsassistent / Abbrechen
     Passwortdialog -> storage.open_database()  (Schlüssel wird sofort geprüft)
     _run_startup_backup()  (Pflichtsicherung vor Migrationen)
     storage.apply_migrations()
     Services + MediaService.cleanup_orphaned_part_files()
     MainWindow
```

### Schichten
| Schicht | Inhalt |
|---|---|
| `ui/` (≈ 35 Module) | Hauptfenster, Klientenliste, Klientenübersicht/-detail, Sitzungs-, Bericht-, Medien-, Sicherungs- und Behandlungsart-Dialoge, Tabellenmodelle, Theme, Fenster-/Spaltenpersistenz |
| `services/` | `ClientService`, `TreatmentSessionService`, `TreatmentTypeService`, `MediaService`, `transaction()`, `ServiceError`-Hierarchie (deutsche Meldungen) |
| `repositories/` | vier Repositories, einziger Ort mit Abfragen |
| `models/` | `Client`, `TreatmentSession` (Tabelle `session`), `TreatmentType`, `Media`, `SessionMedia` |
| Infrastruktur | `storage.py` (Laufwerkssuche, Engine, Migrationen, Einrichtung), `backup.py`, `config.py` |

### Datenablage
- **Datenplatte:** `klientenverwaltung.id`, `klientenverwaltung.db` (SQLCipher), Ordner `medien/`
  (unverschlüsselt, UUID-Dateinamen), ggf. Notfall-Sicherungen.
- **Sicherungsordner (frei wählbar):** `klientenverwaltung_backup_YYYYMMDD_HHMMSS.db` (verschlüsselt),
  Rotation 10; Unterordner `vor-wiederherstellung/` (Rotation 5).
- **Laptop:** `%APPDATA%\Klientenverwaltung\config.json` (Laufwerkspfad, Sicherungsordner),
  `error.log`, QSettings (Registry: Fenstergeometrie, Spalten, Theme).

### Weitere Eigenschaften
- Eine SQLAlchemy-Session pro Service-Aufruf, `expire_on_commit=False`; Services geben teils
  ORM-Objekte, teils DTO-Dataclasses zurück.
- Nebenläufigkeit nur beim Medienimport (`QThread` + Worker); alles andere auf dem GUI-Thread.
- Authentifizierung = SQLCipher-Passwort; keine Benutzerverwaltung (Einzelplatz).

---

## Review Statistics

| Priorität | Anzahl |
|---|---|
| 🔴 CRITICAL | 0 |
| 🟠 HIGH | 4 |
| 🟡 MEDIUM | 13 |
| 🟢 LOW | 25 |
| **Gesamt** | **42** |

| Art | Anzahl |
|---|---|
| Bestätigtes Problem | 29 |
| Mögliches Problem | 7 |
| Empfehlung | 6 |

---

## 🔴 Critical Findings

Keine. Kein Befund führt im aktuellen, normalen Betrieb zu Datenverlust oder einer schweren
Sicherheitslücke. H-3 hat das Potenzial dazu und ist deshalb als Blocker vor der nächsten
Migration markiert.

---

## 🟠 High Priority Findings

### [HIGH] H-1: Passwort wird ungeschützt in die Datenbank-URL eingesetzt – `@` führt zu Absturz, halb eingerichteter Platte und Passwortfragment im Log; `%XX` verändert den Schlüssel

**Ort:** `src/klientenverwaltung/storage.py:56-58` (`create_encrypted_engine`), aufgerufen aus
`storage.py:206` (`open_database`), `storage.py:253` (`set_up_data_drive`), `alembic/env.py:46, 76`

**Art:** Bestätigtes Problem

**Problem:**
`create_encrypted_engine()` baut die URL per f-String:
`f"sqlite+pysqlcipher://:{password}@/{db_path.as_posix()}"`. SQLAlchemy zerlegt die URL mit einem
regulären Ausdruck, in dem das Passwort nur bis zum **ersten** `@` reicht
(`(?P<password>[^@]*)`), und wendet danach `urllib.parse.unquote()` darauf an:
- **Passwort mit `@`** (z. B. `Sommer@Wiese2026`): Der Rest landet im Host-Teil →
  `ArgumentError: Invalid SQLite URL` bzw. bei zusätzlichem `:` ein nackter `ValueError`
  (Port-Parsing).
- **Passwort mit `%` + zwei Hex-Zeichen** (z. B. `Sommer%41Wiese`): Als Schlüssel wird
  `SommerAWiese` verwendet. Das funktioniert, solange alle Pfade dieselbe URL-Logik nutzen,
  bricht aber, sobald ein Pfad das Passwort roh verwendet (z. B. ein künftiges `PRAGMA rekey`, M-7).

**Warum es wichtig ist:**
- `@` kommt in Passwörtern häufig vor. `_SummaryPage.validatePage` (`ui/setup_wizard.py:317-323`)
  fängt nur `StorageError` → globaler `sys.excepthook` (`main.py:249-286`) → „Unerwarteter Fehler",
  Programmende.
- Der Traceback wird nach `%APPDATA%\Klientenverwaltung\error.log` geschrieben – inklusive der
  Meldung, die den **Passwortteil nach dem `@` im Klartext** enthält. Verstößt gegen „Das
  Passwort nie speichern oder loggen" (CLAUDE.md).
- `set_up_data_drive` schreibt die Kennungsdatei **vor** dem Erzeugen der Engine (`storage.py:251`
  vs. `:253`) und räumt nur bei `StorageError` auf → es bleibt eine Kennungsdatei ohne Datenbank
  zurück (Folgen siehe M-1).

**Beleg:** Nachgestellt mit der installierten SQLAlchemy 2.0.54 (ohne Verbindungsaufbau):
```
make_url('sqlite+pysqlcipher://:abc@defghijklmn@/C:/…').password  -> 'abc'  (Host: 'defghijklmn@')
make_url('sqlite+pysqlcipher://:Sommer%41Wiese12@/C:/…').password -> 'SommerAWiese12'
create_engine(… 'abc@defghijklmn' …)
   -> ArgumentError: Invalid SQLite URL: sqlite+pysqlcipher://@defghijklmn@/C:/…
create_engine(… 'a:b@c:d@e12345678' …)
   -> ValueError: invalid literal for int() with base 10: 'd@e12345678@'
```
Der Schlüssel selbst wird von SQLAlchemy korrekt maskiert (`pragma key=` mit `quote_identifier`),
`"` ist also unproblematisch – das Problem liegt allein im URL-Parsing.

**Empfohlene Änderung:**
- URL nicht als String bauen, sondern
  `sqlalchemy.engine.URL.create("sqlite+pysqlcipher", password=password, database=str(db_path))`.
  Geprüft: `Sommer@Wiese%41"12:/?#` bleibt dabei unverändert erhalten, `repr(engine.url)` maskiert es.
- Im selben Schritt `hide_parameters=True` setzen (H-2).
- `alembic/env.py` nutzt dieselbe Funktion und profitiert automatisch.
- Regressionstest: Einrichtung + Anmeldung mit Passwörtern, die `@`, `%41`, `"`, `:`, `/`, `?`,
  `#` und Umlaute enthalten.

**Erwarteter Nutzen:** Jedes zulässige Passwort funktioniert; kein Absturz im Assistenten; kein
Passwortfragment im Log.

**Risiken / Hinweise:** Datenbanken, die bereits mit einem Passwort mit `%XX`-Sequenz angelegt
wurden, sind mit dem *dekodierten* Wert verschlüsselt. Falls es solche gibt: beim Login zusätzlich
`urllib.parse.unquote(passwort)` probieren und bei Erfolg per `PRAGMA rekey` auf den Originalwert
umschlüsseln. Laut `TODO.md` existieren noch keine echten Daten – dann entfällt dieser Schritt.

---

### [HIGH] H-2: Unbehandelte Datenbankfehler schreiben Klientendaten im Klartext in `error.log` auf dem Laptop

**Ort:** `src/klientenverwaltung/storage.py:58` (`create_engine(url)` ohne `hide_parameters`),
`src/klientenverwaltung/main.py:270-275` (`_log_and_show_crash`),
`src/klientenverwaltung/config.py:16-22`

**Art:** Bestätigtes Problem (Mechanismus nachgewiesen; tritt bei einer unerwarteten
Datenbank-Ausnahme auf)

**Problem:** SQLAlchemy übernimmt standardmäßig die gebundenen SQL-Parameter in den Text jeder
`StatementError` (`[parameters: ('Anna', …)]`). Der globale Crash-Handler schreibt
`traceback.format_exception(...)` – einschließlich verketteter Ursachen (`raise … from exc`) –
unverschlüsselt nach `%APPDATA%\Klientenverwaltung\error.log`. Die Docstrings von
`error_log_path()` und `_log_and_show_crash()` versprechen „never anything from a client record";
technisch abgesichert ist das nicht.

**Warum es wichtig ist:** CLAUDE.md: „Klientendaten dürfen NIE unverschlüsselt auf die
Laptop-Festplatte geschrieben werden … keine Logs mit Inhalten." Parameter können Namen,
Suchbegriffe, Anliegen, Notizen oder Bericht-HTML sein – Gesundheitsdaten. Lesepfade laufen nicht
durch `transaction()` (M-4): Eine `OperationalError` (z. B. „database is locked" durch eine zweite
Instanz, L-17, oder ein E/A-Fehler) in `ClientRepository.list(search=…)` landet samt Suchbegriff
im Log.

**Beleg:** `str(StatementError('boom', 'INSERT INTO client (first_name) VALUES (?)', ('Anna',), None))`
→ enthält `[parameters: ('Anna',)]` (mit der installierten Version nachgestellt).

**Empfohlene Änderung:**
1. `create_engine(..., hide_parameters=True)` in `create_encrypted_engine` (eine Zeile, zusammen mit H-1).
2. Im Crash-Handler defensiv loggen: Ausnahmetyp, Datei/Zeile, Stack – Meldungstexte von
   `sqlalchemy.exc.*` (auch in verketteten Ursachen) weglassen oder kürzen.
3. Test: eine `StatementError` mit Parameter durch `_log_and_show_crash` schicken (Dialog
   gemonkeypatcht) und prüfen, dass der Wert nicht im Log steht.

**Erwarteter Nutzen:** Die zentrale Datenschutzregel ist technisch statt nur per Konvention abgesichert.

**Risiken / Hinweise:** Etwas weniger Diagnoseinformation; die SQL-Anweisung ohne Werte reicht zur
Fehlersuche in der Regel aus.

---

### [HIGH] H-3: Künftige Alembic-Batch-Migrationen löschen wegen `PRAGMA foreign_keys = ON` stumm alle Sitzungen bzw. Medien-Verknüpfungen

**Ort:** `src/klientenverwaltung/storage.py:60-65` (Pragma bei jeder Verbindung),
`storage.py:321-331` (`apply_migrations`), `alembic/env.py:59-73` (`render_as_batch=True`, keine
Fremdschlüssel-Behandlung)

**Art:** Mögliches Problem (latent; Mechanismus nachgewiesen – tritt mit der nächsten Migration
auf, die `client` oder `session` neu aufbaut)

**Problem:** SQLite kann viele Schemaänderungen nicht per `ALTER TABLE`; Alembic baut die Tabelle
im Batch-Modus neu auf (`_alembic_tmp_x` anlegen, Daten kopieren, `DROP TABLE x`, umbenennen). Bei
aktivierten Fremdschlüsseln führt SQLite beim `DROP TABLE` ein implizites `DELETE FROM x` aus, **das
`ON DELETE CASCADE` auslöst**. Da jede Verbindung – auch die Migrationsverbindung –
`foreign_keys = ON` setzt:
- Neuaufbau von `session` → alle Zeilen in `session_media` werden gelöscht.
- Neuaufbau von `client` → **alle Sitzungen inkl. Berichte** und in der Folge alle
  Medien-Verknüpfungen werden gelöscht.

Die bisherigen Batch-Migrationen (`71b6a09c0da8`, `c311968e9a6f`) haben `session` neu aufgebaut,
*bevor* `session_media` existierte (`c66a9fbe6d01`). Deshalb ist bisher nichts passiert.

**Warum es wichtig ist:** Genau solche Änderungen sind geplant: Statusfeld für Sitzungen
(`TODO.md:43`), `session_treatment` statt `treatment_type_id` (CLAUDE.md, „Offene Punkte"),
`client_number` (`TODO.md:31`; eine UNIQUE-Spalte erzwingt in SQLite den Neuaufbau von `client`).
Der Verlust wäre **stumm**: Die Migration meldet Erfolg, das Programm startet, die Sitzungen fehlen.
Die Pflichtsicherung vor der Migration hilft nur, wenn der Verlust bemerkt wird, bevor die
Rotation (10 Stände) sie verdrängt.

**Beleg:** Nachgestellt in einer In-Memory-SQLite (3.53.1) mit identischen Fremdschlüssel-Klauseln
und dem Ablauf, den Alembic im Batch-Modus ausführt:
```
vorher:                        sessions 2, links 2
nach Neuaufbau von session:    sessions 2, links 0
nach Neuaufbau von client:     clients 1, sessions 0
```
SQLite-Dokumentation (foreignkeys.html, Abschnitt 5): „the DROP TABLE command performs an implicit
DELETE … may invoke foreign key actions".

**Empfohlene Änderung:**
- In `alembic/env.py` (Online-Pfad mit übergebener Verbindung) vor `context.begin_transaction()`
  `PRAGMA foreign_keys=OFF` ausführen (wirkt nur außerhalb einer offenen SQLite-Transaktion – beim
  Umsetzen verifizieren), nach den Migrationen `PRAGMA foreign_key_check` ausführen (muss leer sein,
  sonst `StorageError`) und `PRAGMA foreign_keys=ON` wiederherstellen – das von Alembic für
  SQLite-Batch-Migrationen dokumentierte Vorgehen.
- Regressionstest: befüllte Datenbank (Klient, Sitzung, Medium, Verknüpfung), Test-Migration mit
  `batch_alter_table("client", recreate="always")` bzw. `("session", recreate="always")`, danach
  Zeilenzahlen vergleichen.
- Bis zur Behebung eine deutliche Warnung in `docs/build.md` („Migrationen") aufnehmen.

**Erwarteter Nutzen:** Schemaänderungen werden gefahrlos; die geplanten Erweiterungen sind ohne
Datenverlustrisiko umsetzbar.

**Risiken / Hinweise:** Während der Migration ohne Fremdschlüsselprüfung muss die Konsistenz über
`foreign_key_check` nachgewiesen werden. Außerdem ist DDL mit dem pysqlite-Standardverhalten nicht
vollständig transaktional – eine mittendrin abgebrochene Migration kann ein teilmigriertes Schema
hinterlassen; die Pflichtsicherung davor bleibt daher wichtig. **Jede weitere Migration aus
diesem Review (H-4, L-13) erst nach H-3 umsetzen.**

---

### [HIGH] H-4: Versteckte Sekunden/Millisekunden in Terminen führen zu falschen „Überschneidungs"-Fehlern bei direkt anschließenden Terminen

**Ort:** `src/klientenverwaltung/ui/session_dialog.py:51-53, 94, 98-103`;
`src/klientenverwaltung/services/treatment_session_service.py:85-116, 153-184, 222-240`;
`src/klientenverwaltung/repositories/treatment_session_repository.py:74-103`

**Art:** Bestätigtes Problem

**Problem:** „Neue Sitzung" belegt das Datumsfeld mit `QDateTime(datetime.now())` – inklusive
Sekunden und Millisekunden. Das Anzeigeformat `dd.MM.yyyy HH:mm` blendet sie aus,
`QDateTimeEdit` behält sie beim Ändern von Stunde/Minute aber bei, und `toPython()` liefert sie
mit. Weder Oberfläche noch Service normalisieren auf volle Minuten; die Überschneidungsprüfung
vergleicht exakte Zeitpunkte.

**Warum es wichtig ist:** Beispiel: Termin A wird um 13:12:47 angelegt und auf 14:00 gestellt →
gespeichert 14:00:47.123, Ende 15:00:47. Termin B wird um 16:40:05 angelegt und auf 15:00
gestellt → 15:00:05. Die Prüfung meldet „überschneidet sich mit einem Termin … um 14:00 Uhr",
obwohl der Anwender 14:00–15:00 und 15:00 sieht. Das tritt zufällig (je nach Sekunden) auf, ist
nicht nachvollziehbar und widerspricht der ausdrücklichen Regel „direkt aneinander anschließende
Termine sind erlaubt" (`docs/projekt-kontext.md:76-78`).

**Beleg:** Offscreen-Probe mit PySide6 6.11.2: Wert `14:23:47.123`, Minute per Pfeil (`stepBy`)
auf 59 → Anzeige `29.09.2026 14:59`, gespeicherter Wert `2026-09-29 14:59:47.123000`. Der Test
`test_create_session_allows_back_to_back_appointments` arbeitet mit glatten Zeiten und deckt das
nicht ab.

**Empfohlene Änderung:**
- Geschäftsregel im Service: in `create_session`/`update_session`
  `date = date.replace(second=0, microsecond=0)` (Normalisierung gehört laut Architektur in `services/`).
- Oberfläche: Startwert auf volle Minute, besser auf die nächste volle Viertelstunde setzen.
- Alembic-Datenmigration, die bestehende `session.date`-Werte auf Minuten kürzt (**nach H-3**).
- Test: zwei direkt anschließende Termine mit „krummen" Sekunden.

**Erwarteter Nutzen:** Verlässliche Terminprüfung, keine unerklärlichen Fehlermeldungen.

**Risiken / Hinweise:** Das Kürzen kann zwei bisher knapp nicht überlappende Termine überlappend
machen – vor der Migration abfragen und ggf. melden.

---

## 🟡 Medium Priority Findings

### [MEDIUM] M-1: Einrichtung räumt nur bei `StorageError` auf – jede andere Ausnahme hinterlässt eine „halb eingerichtete" Datenplatte, von der der Anwender nicht wegkommt

**Ort:** `src/klientenverwaltung/storage.py:239-266` (`set_up_data_drive`),
`src/klientenverwaltung/ui/setup_wizard.py:313-328`, `src/klientenverwaltung/main.py:62-87`,
`ui/setup_wizard.py:115-135`

**Art:** Bestätigtes Problem

**Problem:** Die Kennungsdatei wird als *erster* Schritt geschrieben (`:251`), danach wird die
Engine erzeugt (`:253`, außerhalb des `try`) und migriert. Aufgeräumt wird nur bei `StorageError`;
`apply_migrations` wandelt nur `SQLAlchemyError` um. Unbehandelt bleiben z. B. `ArgumentError`/
`ValueError` (H-1), `ModuleNotFoundError` beim Laden von `alembic/env.py` im Build (genau das ist
laut `scripts/pyinstaller_common.py:39-49` schon einmal passiert), `alembic.util.CommandError`,
`OSError`. Auch der Assistent fängt nur `StorageError`.

**Warum es wichtig ist:** Danach liegt `klientenverwaltung.id` (evtl. mit leerer
`klientenverwaltung.db`) auf der Platte. Beim nächsten Start wird die Platte gefunden →
`open_database` → „Datenbankdatei wurde nicht gefunden" → Programmende. Der Assistent wird nicht
mehr angeboten und lehnt die Platte als „bereits eingerichtet" ab. Ohne manuelles Löschen der
Kennungsdatei kommt der Anwender nicht weiter – im heikelsten Moment (erster Start).

**Beleg:** Codepfad wie beschrieben; konkreter Auslöser z. B. H-1.

**Empfohlene Änderung:**
- Reihenfolge umdrehen: erst Datenbank anlegen und migrieren, **zuletzt** die Kennungsdatei
  schreiben – die Platte gilt erst als eingerichtet, wenn alles fertig ist.
- Aufräumen bei jeder Ausnahme (`except BaseException: dispose(); unlink(...); raise`).
- Im Assistenten zusätzlich `Exception` abfangen und eine verständliche Meldung zeigen.
- Beim Start: Kennungsdatei vorhanden, aber keine Datenbank → Meldung mit Angebot, die Einrichtung
  abzuschließen.

**Erwarteter Nutzen:** Kein Sackgassen-Zustand beim ersten Start.

**Risiken / Hinweise:** Test `test_cleans_up_identifier_and_database_file_when_migrations_fail`
um Nicht-`StorageError`-Fälle erweitern.

---

### [MEDIUM] M-2: Bestehende Sitzung mit inzwischen deaktivierter Behandlungsart lässt sich nicht mehr speichern

**Ort:** `src/klientenverwaltung/services/treatment_session_service.py:170-173`
(`update_session` → `_require_active_treatment_type`),
`src/klientenverwaltung/services/treatment_type_service.py:74-93`,
`src/klientenverwaltung/ui/session_dialog.py:56-62`

**Art:** Bestätigtes Problem

**Problem:** `list_selectable_for_session()` nimmt die aktuelle, inzwischen deaktivierte Art
bewusst in die Auswahl auf („editing an existing session must not lose or silently change a
historical, since-deactivated type"). `update_session()` verlangt aber immer eine *aktive* Art. Wer
bei einer alten Sitzung nur Datum oder Dauer korrigiert, erhält: „Die Behandlungsart … ist
deaktiviert und kann nicht für neue Sitzungen verwendet werden." – obwohl es keine neue Sitzung ist.

**Warum es wichtig ist:** Deaktivieren ist laut CLAUDE.md der vorgesehene Weg statt Löschen; die
Historie soll unverändert und bearbeitbar bleiben. Die Sperre widerspricht der eigenen
Designabsicht, die Meldung ist irreführend, und der Workaround (Art kurz reaktivieren) ist für den
Anwender nicht naheliegend.

**Beleg:** Nur der Anlage-Fall ist getestet (`tests/test_treatment_session_service.py:61-67`).

**Empfohlene Änderung:** In `update_session` die Aktiv-Prüfung nur ausführen, wenn sich
`treatment_type_id` ändert. Tests: (a) Dauer einer Sitzung mit deaktivierter Art ändern → erlaubt;
(b) Wechsel auf eine andere deaktivierte Art → abgelehnt.

**Erwarteter Nutzen:** Konsistente Regel „deaktiviert = nicht für Neues; Historie bleibt bearbeitbar".

**Risiken / Hinweise:** Keine.

---

### [MEDIUM] M-3: Klientensuche findet Umlaut-Namen bei Kleinschreibung nicht und keine vollständigen Namen („Anna Muster")

**Ort:** `src/klientenverwaltung/repositories/client_repository.py:30-38`; gleiches Muster in
`src/klientenverwaltung/repositories/media_repository.py:104-105`; Aufruf
`src/klientenverwaltung/ui/client_list_widget.py:158-162`

**Art:** Bestätigtes Problem

**Problem:**
1. `ilike` wird auf SQLite als `lower(spalte) LIKE lower(?)` umgesetzt; SQLites `lower()` kennt nur
   ASCII. „über" findet „Überlingen" nicht, „özdemir" findet „Özdemir" nicht, „KÖLN" findet „Köln" nicht.
2. Jede Spalte wird einzeln mit dem *gesamten* Suchtext verglichen → „Anna Muster" findet nichts.
3. `%` und `_` im Suchtext wirken als Platzhalter.

**Warum es wichtig ist:** Die Suche ist die Hauptfunktion der Startseite. Ein Anwender tippt
natürlich klein und oft den vollen Namen. Ein leeres Ergebnis wirkt wie „Klient nicht vorhanden" –
im ungünstigen Fall wird ein Duplikat angelegt.

**Beleg:** Nachgestellt mit SQLAlchemy 2.0.54/SQLite: `'über' → []`, `'Über' → [Muster]`,
`'özdemir' → []`, `'ÖZDEMIR' → [Özdemir]`, `'Anna Muster' → []`, `'KÖLN' → []`.
Erzeugtes SQL: `lower(c.first) LIKE lower(?)`.

**Empfohlene Änderung:**
- Suchtext an Leerzeichen in Begriffe zerlegen; ein Klient passt, wenn *jeder* Begriff in
  *irgendeiner* Spalte vorkommt.
- Unicode-sicherer, portabler Vergleich: Bei der zu erwartenden Menge (einige hundert Klienten) ist
  Filtern im Service mit `str.casefold()` am einfachsten und bleibt PostgreSQL-tauglich. Alternativen:
  vom Service gepflegte normalisierte Suchspalten oder eine in `storage.py` registrierte SQL-Funktion
  (SQLite-spezifisch, dort erlaubt).
- LIKE-Platzhalter escapen (`ilike(pattern, escape="\\")`), falls in SQL gefiltert wird.
- Tests mit Umlauten und Vor-/Nachname-Kombination.

**Erwarteter Nutzen:** Die Suche verhält sich so, wie ein Anwender es erwartet.

**Risiken / Hinweise:** Filtern im Service lädt alle Klienten – bei dieser Größenordnung
unkritisch; bei einem Umzug auf PostgreSQL kann es wieder in die Datenbank (dort ist `ILIKE`
Unicode-fähig).

---

### [MEDIUM] M-4: Fehlergrenze der Services ist unvollständig – Lesefehler und Abziehen der Platte führen zum „Unerwarteter Fehler … wird beendet"-Dialog

**Ort:** `src/klientenverwaltung/services/transaction.py:12-25`; Lesemethoden z. B.
`services/client_service.py:130-176`, `services/treatment_session_service.py:118-151`,
`services/media_service.py:281-298, 343-356, 390-475`; `storage.py:217-223`; ungeschützte
UI-Aufrufe u. a. `ui/client_list_widget.py:160, 258`, `ui/client_detail_dialog.py:71, 251, 261`,
`ui/client_overview_dialog.py:97-110`, `ui/client_sessions_dialog.py:82, 169, 283`,
`ui/media_dialog.py:169, 202`, `ui/media_overview_dialog.py:70, 153, 203`, `ui/media_cleanup.py:25`,
`ui/select_existing_media_dialog.py:67, 114`, `ui/treatment_type_management_dialog.py:132, 159`

**Art:** Bestätigtes Problem

**Problem:**
- `transaction()` verspricht im Docstring, dass keine SQLAlchemy-Ausnahme die Service-Schicht
  verlässt – das gilt nur für Schreibvorgänge. Lesemethoden reichen `SQLAlchemyError` roh weiter,
  die UI ruft sie ohne `try` auf.
- `DataDriveDisconnectedError` (aus dem `handle_error`-Hook in `storage.py`) ist ein
  `StorageError`, kein `SQLAlchemyError`: Er passiert `transaction()` ungefiltert, die UI fängt nur
  `ServiceError`. Ergebnis: generischer Absturzdialog + Programmende. Die eigens formulierte Meldung
  „Bitte Datenplatte wieder anschliessen …" erscheint nie (im Medienimport nur als generischer
  Text, `ui/media_import_worker.py:52-62`).

**Warum es wichtig ist:** Das Abziehen der USB-Platte ist im Alltag das wahrscheinlichste
Fehlerszenario. Ungespeicherte Eingaben in offenen Dialogen gehen verloren, der Anwender sieht nur
„unerwarteter Fehler". Verstärkt zudem H-2.

**Beleg:** Codepfade wie oben; in `ui/` gibt es keinen einzigen Handler für
`DataDriveDisconnectedError`.

**Empfohlene Änderung:**
- Lese-Wrapper (Kontextmanager oder Decorator) in `services/`, der `SQLAlchemyError` →
  `ServiceError` übersetzt – analog zu `transaction()`.
- Eigene Ausnahme für „Daten nicht erreichbar" (z. B. `DataUnavailableError(ServiceError)` in
  `services/errors.py`), die der Disconnect-Hook wirft; alternativ `StorageError` im Crash-Handler
  gesondert mit der eigenen deutschen Meldung anzeigen.
- In `ui/` ein zentraler Helfer (z. B. `call_service(parent, fn, *args)`), der `ServiceError`
  einheitlich anzeigt – ersetzt die rund 20 gleichartigen `try/except ServiceError`-Blöcke.

**Erwarteter Nutzen:** Verständliche Meldungen statt Absturz; weniger duplizierter Code.

**Risiken / Hinweise:** Im Wrapper `ServiceError`-Unterklassen (z. B. `NotFoundError`) nicht
doppelt verpacken.

---

### [MEDIUM] M-5: Timeout der Laufwerkssuche ist wirkungslos – ein hängendes Laufwerk blockiert den Programmstart

**Ort:** `src/klientenverwaltung/storage.py:90-102` (`_read_identifier_file_bounded`),
`storage.py:105-123` (`_scan_for_identifier`), `storage.py:163-169`; Test
`tests/test_storage.py:75-94`

**Art:** Bestätigtes Problem

**Problem:** Beide Funktionen nutzen `with ThreadPoolExecutor(...)`. `future.result(timeout=…)`
bricht nur das *Warten auf das Ergebnis* ab; beim Verlassen des `with`-Blocks ruft Python
`shutdown(wait=True)` auf und wartet, bis der hängende Lesevorgang wirklich endet.
`DRIVE_CHECK_TIMEOUT_SECONDS = 2.0` begrenzt also nichts. Die Suche läuft auf dem GUI-Thread.

**Warum es wichtig ist:** Typischer Auslöser ist ein verbundenes, aber nicht erreichbares
Netzlaufwerk (z. B. NAS-Laufwerksbuchstabe unterwegs). SMB-Timeouts dauern oft 20–60 s – bei jedem
Start und jedem „Erneut versuchen"; der Splash friert ein. Genau diesen Fall soll der Code laut
Docstring verhindern.

**Beleg:** Nachgestellt: Leser für ein Laufwerk schläft 3 s, `timeout=0.1` →
`_find_data_drive_among` kehrt nach **3,00 s** zurück; ebenso, wenn `last_known_path` auf das
langsame Laufwerk zeigt. Der bestehende Test prüft nur das Ergebnis, nicht die Dauer.

**Empfohlene Änderung:**
- Pro Laufwerk einen Daemon-Thread starten und mit gemeinsamer Deadline auf Ergebnisse warten
  (Queue/`Event`); hängende Threads liegen lassen. (Nicht nur `shutdown(wait=False)`:
  `ThreadPoolExecutor`-Threads werden bei Programmende gejoint und würden dann das Beenden blockieren.)
- Netz- und CD-Laufwerke (`GetDriveTypeW` 4/5) überspringen oder zuletzt prüfen.
- Test um eine Zeitschranke ergänzen.
- Dasselbe Muster im Assistenten beachten: `describe_drive()`/`drive_already_set_up()` laufen
  ohne Timeout auf dem GUI-Thread (`ui/setup_wizard.py:87-93, 115, 135`).

**Erwarteter Nutzen:** Start bleibt schnell und bedienbar, auch mit „toten" Laufwerksbuchstaben.

**Risiken / Hinweise:** Verwaiste Daemon-Threads sind unkritisch (sie lesen nur eine kleine Datei).

---

### [MEDIUM] M-6: Wiederherstellung – die Sicherheitskopie „vor Wiederherstellung" ist in der Oberfläche unsichtbar, und die gewählte Sicherung wird vor dem Überschreiben nicht geprüft

**Ort:** `src/klientenverwaltung/ui/backup_management_dialog.py:159-172, 248-301`;
`src/klientenverwaltung/backup.py:80-94, 118-130, 186-209`

**Art:** Bestätigtes Problem

**Problem:**
1. `create_pre_restore_backup` legt die Sicherheitskopie im Unterordner `vor-wiederherstellung`
   ab. `list_backups()` sucht nur im obersten Ordner; der Dialog zeigt diese Kopien nie. Ein
   versehentlich wiederhergestellter falscher Stand lässt sich in der Anwendung nicht rückgängig
   machen – nur durch manuelles Kopieren im Explorer.
2. Die Bestätigung sagt gleichzeitig „wird vorher zusätzlich gesichert" und „kann nicht rückgängig
   gemacht werden" – widersprüchlich.
3. Die gewählte Datei wird ungeprüft über die Datenbank kopiert. Ist sie beschädigt, mit einem
   anderen Passwort verschlüsselt (andere Installation; künftig nach „Passwort ändern", M-7) oder
   von einer neueren Programmversion (L-8), merkt der Anwender das erst beim nächsten Start – als
   „Passwort falsch" bzw. Absturz.

**Warum es wichtig ist:** Die Wiederherstellung ist der Notfallpfad eines nicht-technischen
Anwenders; sie muss sicher und umkehrbar sein. „Passwort falsch" nach einer Wiederherstellung ließe
den Anwender glauben, das Passwort sei verloren.

**Beleg:** `backup.list_backups` nutzt `folder.glob(BACKUP_FILENAME_GLOB)` ohne Unterordner;
Meldungstext in `backup_management_dialog.py:255-261`.

**Empfohlene Änderung:**
- Sicherheitskopien im Dialog anzeigen (Herkunft z. B. „Vor Wiederherstellung") und
  wiederherstellbar machen.
- Vor dem Überschreiben die Sicherung lesend in einer temporären Engine mit dem aktuellen Schlüssel
  öffnen (`URL` der laufenden Engine), `PRAGMA quick_check` bzw. `PRAGMA cipher_integrity_check`
  ausführen und die Alembic-Revision gegen den Programmstand prüfen; bei Fehlschlag verständliche
  Meldung, nichts überschreiben.
- Meldungstext anpassen („… wird vorher gesichert und kann über … zurückgeholt werden").

**Erwarteter Nutzen:** Sicherer, umkehrbarer Notfallpfad; kein Aussperren durch eine unpassende Sicherung.

**Risiken / Hinweise:** Die Prüfung darf die Sicherung nicht migrieren oder verändern.

---

### [MEDIUM] M-7: „Passwort ändern" (Rekey) ist gefordert, aber nicht umgesetzt

**Ort:** Anforderung in `CLAUDE.md` („Menüpunkt "Passwort ändern" (Rekey)"); Menü
`src/klientenverwaltung/ui/main_window.py:69-103`; keine Implementierung in `storage.py`

**Art:** Bestätigtes Problem (fehlende dokumentierte Anforderung)

**Problem:** Es gibt keinen Weg, das Datenbankpasswort zu ändern (`rekey` kommt nur in CLAUDE.md vor).

**Warum es wichtig ist:** Wird das Passwort bekannt (Zettel, Schulterblick, Übergabe durch den
Entwickler – `docs/projekt-kontext.md:128-130` verlangt ausdrücklich, dass der Anwender es selbst
vergibt), bleibt nur das Neueinrichten einer Platte mit manueller Datenübernahme.

**Beleg:** Codebasis, Menüstruktur.

**Empfohlene Änderung:**
- Dialog „Passwort ändern" (altes Passwort; neues doppelt; Mindestlänge; gleicher Warnhinweis wie
  im Assistenten).
- `storage.change_password(...)`: altes Passwort prüfen, Pflichtsicherung, `PRAGMA rekey` mit
  korrekt maskiertem Wert, Engine entsorgen und neu öffnen (oder – wie bei der Wiederherstellung –
  Programm beenden und neu starten lassen).
- **Vorher H-1 beheben**, sonst unterscheidet sich der per URL gesetzte vom per `rekey` gesetzten Schlüssel.
- Anzeigen, dass ältere Sicherungen das alte Passwort behalten; die Wiederherstellung muss dann ggf.
  das alte Passwort abfragen (M-6). Optional alte Sicherungen neu verschlüsseln oder löschen.

**Erwarteter Nutzen:** Erfüllt eine Kernanforderung; ein kompromittiertes Passwort ist beherrschbar.

**Risiken / Hinweise:** Vorher sichern; Abbruch während des Rekey testen.

---

### [MEDIUM] M-8: Einfügen in den Berichtseditor übernimmt Bilder (als Verweis auf Temp-Dateien des Laptops), Tabellen und Links

**Ort:** `src/klientenverwaltung/ui/report_dialog.py:50-57, 60-102, 120-122, 478-486`; Regel
`docs/ui-regeln.md:47-59`

**Art:** Bestätigtes Problem

**Problem:** `strip_disallowed_formatting` entfernt nur Farbe, Hintergrund, Schriftart und
-größe aus Zeichenformaten. Beim Einfügen aus Word bleiben
`<img src="file:///C:/Users/…/AppData/Local/Temp/msohtmlclip1/…">`, Tabellen und Hyperlinks
erhalten und werden so gespeichert. Die UI-Regel sagt: „erhalten bleiben nur fett, kursiv,
unterstrichen und die Überschriftsebene".

**Warum es wichtig ist:**
- Bilder landen nicht in der verschlüsselten Datenbank, sondern als Verweis auf eine Datei **auf
  dem Laptop**. Das (ggf. gesundheitsbezogene) Bild liegt unverschlüsselt außerhalb der
  Datenplatte, und der Bericht zeigt es nur, bis Word seine Temp-Dateien aufräumt – danach ein
  „kaputtes Bild".
- Der gespeicherte Pfad enthält den Windows-Benutzernamen.
- Tabellen und Links verhalten sich im Editor und im Berichtsverlauf uneinheitlich.

**Beleg:** Offscreen-Probe: HTML mit Farbe, Schrift, `<img src="file:///C:/Users/X/…">`,
`<table>` und `<a href>` über `_GrowingTextEdit.insertFromMimeData` + `strip_disallowed_formatting`
eingefügt → `img`, lokaler Pfad, `table` und `a href` bleiben erhalten; `color:` und `Calibri`
werden entfernt.

**Empfohlene Änderung:** In `insertFromMimeData` ein bereinigtes Fragment einfügen: Bilder
(`QTextImageFormat`) entfernen, `AnchorHref`/`IsAnchor` löschen, Tabellen in Absätze umwandeln (oder
nur Text plus fett/kursiv/unterstrichen übernehmen). Dieselbe Bereinigung vor dem Speichern
(zweite, unabhängige Stelle gemäß UI-Regel). Test mit Word-typischem HTML.

**Erwarteter Nutzen:** Berichte enthalten ausschließlich Text in der verschlüsselten Datenbank; die
UI-Regel ist tatsächlich erfüllt.

**Risiken / Hinweise:** Sollen Bilder zu einer Sitzung gehören, gehören sie in die Medienverwaltung.

---

### [MEDIUM] M-9: Archivierte Klienten im Dunkelmodus mit der Farbe des hellen Themes (Kontrast ≈ 2,9 : 1); inaktive Behandlungsarten mit nativer statt Theme-Farbe

**Ort:** `src/klientenverwaltung/ui/client_table_model.py:8, 124-125`;
`src/klientenverwaltung/ui/treatment_type_table_model.py:60-63`; Regel `docs/ui-regeln.md:76-80`

**Art:** Bestätigtes Problem

**Problem:** `ClientTableModel.data()` liefert für archivierte Zeilen immer
`QColor(LIGHT_PALETTE.text_archived)` (`#766E65`) – auch im Dunkelmodus.
`TreatmentTypeTableModel` nutzt `QApplication.palette()` (Disabled/Text), also die native
Windows-Palette, die das Theme (nur Stylesheet) gar nicht setzt.

**Warum es wichtig ist:** Im Dunkelmodus ergibt `#766E65` auf `#302923` einen Kontrast von
≈ 2,9 : 1 (WCAG AA verlangt 4,5 : 1). Vorgesehen wäre `DARK_PALETTE.text_archived` (`#B5A79A`,
≈ 6,1 : 1). Archivierte Klienten sind schlecht lesbar; die Regel „Farben nur aus dem aktiven Theme"
wird verletzt.

**Beleg:** Code; Kontraste nach WCAG-Formel aus den Palettenwerten (`ui/theme.py:135-193`) berechnet.

**Empfohlene Änderung:** In `theme.py` eine Funktion `current_palette()` bereitstellen, die
`apply_theme_mode` setzt; beide Modelle holen ihre Farben dort. Views zeichnen nach einem
Theme-Wechsel neu und übernehmen die Farbe (ggf. `viewport().update()`).

**Erwarteter Nutzen:** Lesbarkeit im Dunkelmodus; eine einzige Farbquelle.

**Risiken / Hinweise:** Keine.

---

### [MEDIUM] M-10: Sicherungsstrategie – die Arbeit des laufenden Tages liegt bis zum nächsten Start nur auf der Datenplatte

**Ort:** `src/klientenverwaltung/main.py:90-142` (`_run_startup_backup`),
`src/klientenverwaltung/backup.py:141-161`, `src/klientenverwaltung/ui/main_window.py:142-157`,
`TODO.md:26`

**Art:** Empfehlung (mit einem bestätigten Logikfehler, Punkt 3)

**Problem:**
1. Automatisch gesichert wird nur beim **Start**, also der Stand *vor* der heutigen Arbeit. Was
   heute dokumentiert wird, existiert bis zum nächsten Start nur auf der USB-Platte.
2. Ohne Sicherungsordner (im Assistenten überspringbar) gibt es gar keine automatische Sicherung;
   Hinweis nur in der Statusleiste.
3. Die Prüfung „unverändert seit letzter Sicherung" berücksichtigt auch Notfallkopien auf der
   Datenplatte selbst (`most_recent_backup([drive_root, configured_folder])`). Szenario: Tag 1
   Sicherung auf NAS, danach Arbeit; Tag 2 NAS nicht erreichbar → Kopie auf die Datenplatte, keine
   Änderungen; Tag 3 NAS wieder erreichbar → „unverändert", keine Sicherung. Die Arbeit von Tag 1
   liegt nur auf der Datenplatte, obwohl der externe Ordner verfügbar war.
4. Mediendateien werden nicht gesichert (bekannt, `TODO.md:26`).

**Warum es wichtig ist:** Eine täglich transportierte USB-Platte ist das Bauteil mit dem höchsten
Verlust- und Ausfallrisiko.

**Beleg:** Code wie oben.

**Empfohlene Änderung:**
- Zusätzlich beim Beenden sichern (vor `engine.dispose`, nur bei Änderungen, `VACUUM INTO`).
- Die Unverändert-Prüfung nur gegen den *konfigurierten* Ordner führen.
- Ohne Sicherungsordner regelmäßig (z. B. wöchentlich, Zeitpunkt in `QSettings`) einen Hinweisdialog zeigen.
- Warnen, wenn der Sicherungsordner auf der Datenplatte selbst liegt
  (`ui/backup_management_dialog.py:198-209`).
- Mittelfristig Medien in die Sicherung einbeziehen oder deutlich im UI darauf hinweisen.

**Erwarteter Nutzen:** Verlust oder Defekt der Datenplatte kostet höchstens die Arbeit seit dem
letzten Programmende.

**Risiken / Hinweise:** Die Sicherung beim Beenden darf das Schließen nicht spürbar verzögern und
muss bei getrennter Platte still scheitern.

---

### [MEDIUM] M-11: Testlücken an den riskantesten Stellen – Migrationen vs. Modelle, Startlogik, Dialog-Speicherpfade

**Ort:** `tests/conftest.py:27-46`; ohne Tests: `main._run_startup_backup`, `config.py`,
`ui/client_detail_dialog.py`, `ui/session_dialog.py`, `ui/backup_management_dialog.py`,
`ui/setup_wizard.py`

**Art:** Bestätigtes Problem (Lücke)

**Problem:**
- Service-/Repository-Tests erzeugen das Schema mit `Base.metadata.create_all`, nicht über
  Alembic. Ein Modell ohne passende Migration fällt erst beim Anwender auf.
- Kein Test führt Migrationen gegen eine **befüllte** Datenbank aus (hätte H-3 aufgedeckt, sobald
  eine solche Migration kommt).
- Die datensicherheitsrelevante Entscheidungslogik der Startsicherung (Ordner ja/nein × Migration
  ja/nein × erreichbar ja/nein × unverändert ja/nein) ist ungetestet.
- Dirty-Check und Speichern/Verwerfen/Abbrechen von `ClientDetailDialog` und `SessionDialog`
  sind ungetestet.
- Regressionstests für H-1, H-4, M-2, M-3 und M-5 (Zeitschranke) fehlen.

**Warum es wichtig ist:** Genau diese Bereiche verursachen im Fehlerfall Datenverlust oder einen
blockierten Start.

**Beleg:** Testliste (198 Tests, alle grün) enthält keine Tests für die genannten Fälle.

**Empfohlene Änderung:**
- Test „Migrationen = Modelle": leere DB per `command.upgrade(head)`, dann
  `alembic.autogenerate.compare_metadata(MigrationContext.configure(conn), Base.metadata)` → leer.
- Migrationstest mit Daten (siehe H-3).
- `_run_startup_backup` mit `tmp_path`-Ordnern und gemonkeypatchtem `has_pending_migrations` testen.
- Wenige gezielte Dialogtests für Dirty-Check und Speichern (Muster der vorhandenen Dialogtests).
- Im Sinne der Projektvorgaben: keine breite Testoffensive, sondern genau diese wenigen, wirksamen Tests.

**Erwarteter Nutzen:** Die gefährlichsten Fehlerklassen werden vor der Auslieferung erkannt.

**Risiken / Hinweise:** Keine.

---

### [MEDIUM] M-12: ORM-Entitäten überqueren die Service-Grenze bis in die Oberfläche

**Ort:** Services geben ORM-Objekte zurück (z. B. `ClientService.get_client/create_client/list_clients`,
`TreatmentSessionService.list_sessions_for_client/create_session/get_session`,
`TreatmentTypeService.*`, `MediaService.find_now_unused/delete_unused_media/rename_media`).
`ui/` importiert `klientenverwaltung.models` in `client_detail_dialog.py:19`,
`client_overview_dialog.py:14`, `client_sessions_dialog.py:11`, `client_report_history_dialog.py:14`,
`session_dialog.py:15`, `report_dialog.py:30`, `media_dialog.py:17`, `session_table_model.py:6`,
`treatment_type_management_dialog.py:11`, `treatment_type_table_model.py:5`.

**Art:** Bestätigtes Problem (Abweichung von der Architekturregel) / Empfehlung

**Problem:** CLAUDE.md: „jede [Schicht] spricht nur mit der direkt darunter"; `ui/` soll nur
Services kennen. Tatsächlich arbeitet die UI mit abgelösten SQLAlchemy-Instanzen. Teile des Codes
nutzen bereits DTO-Dataclasses (`ClientListEntry`, `SessionMediaEntry`, `MediaOverviewEntry`, …) –
das Muster ist uneinheitlich.

**Warum es wichtig ist:**
- Lazy-Loading-Falle: Die UI liest `session.treatment_type.name`; das funktioniert nur, weil die
  benutzten Listenmethoden `joinedload` setzen. `get_session()`/`create_session()` liefern Objekte
  *ohne* geladene Beziehung – ein künftiges `…get_session(id).treatment_type.name` in der UI endet
  in `DetachedInstanceError`.
- Das erklärte Ziel „Services unverändert hinter einer Web-API" setzt serialisierbare
  Rückgabewerte voraus.

**Beleg:** Importe und Rückgabetypen wie oben.

**Empfohlene Änderung:** Schrittweise auf frozen Dataclasses umstellen (wie bei Medien), beginnend
mit `TreatmentSession` (in der UI am meisten genutzt), dann `Client`, `TreatmentType`, `Media`.
Anschließend ein kleiner Architekturtest „`ui/` importiert nicht `klientenverwaltung.models`".

**Erwarteter Nutzen:** Einheitliches Muster, keine Detached-Fallen, echte Vorbereitung auf eine API.

**Risiken / Hinweise:** Mittlerer Aufwand; pro Entität ohne Verhaltensänderung machbar.

---

### [MEDIUM] M-13: Teilweise gestylte Scrollbalken werden mit „Schachbrett"-Rinne gezeichnet

**Ort:** `src/klientenverwaltung/ui/theme.py:461-469`

**Art:** Bestätigtes Problem

**Problem:** Das Stylesheet setzt für `QScrollBar` nur Hintergrund- und Griff-Farbe. Sobald
`QScrollBar` per QSS angefasst wird, ersetzt Qt den nativen Stil; ungestylte Unterelemente
(`::add-page`, `::sub-page`) werden mit einem gerasterten Standardmuster gefüllt, der Griff hat
keine Mindestgröße, die Pfeilflächen keine definierte Größe – genau das in
`docs/ui-regeln.md:81-85` beschriebene Problem.

**Warum es wichtig ist:** Betrifft jede Tabelle und jeden Scrollbereich in beiden Themes; wirkt
unfertig, der Griff ist schwer zu erkennen und zu greifen (Zielgruppe braucht große Klickflächen).

**Beleg:** Render-Probe (`build_stylesheet(LIGHT_PALETTE/DARK_PALETTE)` auf einer `QTableView` mit
60 Zeilen): die vertikale Scrollrinne erscheint in beiden Themes als gepunktetes Schachbrett, der
Griff hebt sich kaum ab.

**Empfohlene Änderung:** Scrollbalken vollständig definieren: `QScrollBar:vertical { width: 14px; }`
bzw. `:horizontal { height: 14px; }`, `::handle { min-height/min-width: 32px; border-radius: 6px;
margin: 2px; }`, `::add-page, ::sub-page { background: none; }`,
`::add-line, ::sub-line { width: 0; height: 0; border: none; }` (oder gestaltete Pfeile),
Hover/Pressed für den Griff.

**Erwarteter Nutzen:** Saubere, gut greifbare Scrollbalken in beiden Themes.

**Risiken / Hinweise:** Danach einmal auf 1366×768 und bei 125 %/150 % Skalierung prüfen.

---

## 🟢 Low Priority Findings

### [LOW] L-1: Einrichtungsassistent kündigt „Standard-Behandlungsarten" an, die seit Auftrag D1 nicht mehr angelegt werden

**Ort:** `src/klientenverwaltung/ui/setup_wizard.py:304-311`
**Art:** Bestätigtes Problem
**Problem:** Zusammenfassung: „… werden jetzt die Kennungsdatei, die verschlüsselte Datenbank und
die Standard-Behandlungsarten angelegt." – seit Commit `820aeff` falsch.
**Warum es wichtig ist:** Der Anwender erwartet vorhandene Arten und wird bei „Neue Sitzung" überrascht.
**Beleg:** `storage.set_up_data_drive` (Docstring `storage.py:229-233`) und
`test_creates_identifier_file_and_database_without_treatment_types`.
**Empfohlene Änderung:** Satz ersetzen durch einen Hinweis, wo Behandlungsarten angelegt werden.
**Erwarteter Nutzen:** Richtige Erwartung. **Risiken / Hinweise:** Keine.

### [LOW] L-2: Deutsche Meldungen mit Ersatzschreibung statt Umlaut/ß

**Ort:** `src/klientenverwaltung/storage.py:151, 157, 215, 222`
**Art:** Bestätigtes Problem
**Problem:** „anschliessen", „geoeffnet" in anwendersichtbaren Meldungen, während der Rest der
Oberfläche korrekte Umlaute nutzt. (Nur am Rand, *Präferenz*: „Product by …" im Über-Dialog,
`ui/dialogs.py:20`, ist englisch – vermutlich bewusstes Branding.)
**Warum es wichtig ist:** Wirkt uneinheitlich; gerade die Meldung „Datenplatte nicht gefunden" sieht
der Anwender häufig.
**Beleg:** Stellen oben.
**Empfohlene Änderung:** „anschließen", „geöffnet".
**Erwarteter Nutzen:** Einheitliche Sprache. **Risiken / Hinweise:** Keine.

### [LOW] L-3: Klientenliste beim ersten Start nach „Anrede" absteigend sortiert; keine deutsche Sortierreihenfolge

**Ort:** `src/klientenverwaltung/ui/client_list_widget.py:67-79`,
`ui/client_table_model.py:43-44, 57-65, 149-157`, `repositories/client_repository.py:39`
**Art:** Bestätigtes Problem
**Problem:** (a) Ohne gespeicherten Tabellenzustand steht Qts Sortierindikator auf Spalte 0,
absteigend → Sortierung nach „Anrede" absteigend (nachgewiesen: `sortIndicatorSection() == 0`,
`DescendingOrder` nach `setSortingEnabled(True)`). (b) `casefold()` bzw. der binäre SQL-Vergleich
ist keine deutsche Kollation: „Özdemir", „Ärmel" landen hinter „Z".
**Warum es wichtig ist:** Erster Eindruck und Auffindbarkeit.
**Beleg:** Offscreen-Probe; Code.
**Empfohlene Änderung:** Beim ersten Start `sortByColumn(1, AscendingOrder)` (wie in
`MediaOverviewDialog`); Sortierschlüssel über `QCollator` (Locale `de_DE`).
**Erwarteter Nutzen:** Erwartbare Reihenfolge. **Risiken / Hinweise:** Keine.

### [LOW] L-4: Formular zeigt nach dem Speichern nicht die normalisierten Werte

**Ort:** `src/klientenverwaltung/ui/client_detail_dialog.py:275-288`
**Art:** Bestätigtes Problem
**Problem:** Der Service normalisiert Groß-/Kleinschreibung („anna" → „Anna"), das Formular zeigt
weiter die Eingabe; `_original_values` enthält die unnormalisierten Werte. Titel und Formular
widersprechen sich bis zum erneuten Öffnen.
**Warum es wichtig ist:** Der Anwender sieht nicht, was tatsächlich gespeichert wurde.
**Beleg:** Code.
**Empfohlene Änderung:** Nach erfolgreichem Speichern `_populate_form(client)` mit dem Rückgabewert
aufrufen und `_original_values` neu erfassen.
**Erwarteter Nutzen:** Anzeige = gespeicherter Zustand. **Risiken / Hinweise:** Keine.

### [LOW] L-5: Tastatur- und Fokusbedienung uneinheitlich; Fokus nicht vom Standard-Button unterscheidbar

**Ort:** `src/klientenverwaltung/ui/theme.py:164-167, 192, 365-377, 426-434`;
`ui/client_detail_dialog.py`; `ui/treatment_type_edit_dialog.py`; `ui/client_sessions_dialog.py:86-116`;
`ui/client_list_widget.py:115`
**Art:** Bestätigtes Problem
**Problem:**
- Fokus und Standard-Button sehen identisch aus (`focus` == `accent` in beiden Paletten, jeweils 1 px).
- `QAbstractItemView { outline: none; }` entfernt den Fokusrahmen in Tabellen.
- Strg+S/Strg+Enter (UI-Regel für mehrzeilige Editoren) gibt es nur im Berichtsfenster, nicht in
  `ClientDetailDialog` (Anliegen/Notizen) und `TreatmentTypeEditDialog` (Beschreibung).
- Doppelklick auf eine Sitzung oder Behandlungsart tut nichts (in Klientenliste und Medien schon);
  Enter auf einer markierten Tabellenzeile öffnet nichts.
**Warum es wichtig ist:** Die Tastaturbedienung ist laut `docs/ui-regeln.md:11` ausdrücklich gewünscht.
**Beleg:** Code/Stylesheet.
**Empfohlene Änderung:** Eigene, kräftigere Fokusdarstellung (2 px, eigene Farbe); Kürzel ergänzen;
`doubleClicked`/`activated` einheitlich mit „Bearbeiten"/„Öffnen" verbinden.
**Erwarteter Nutzen:** Konsistente, schnellere Bedienung. **Risiken / Hinweise:** Keine.

### [LOW] L-6: „Jetzt sichern" ohne Rückmeldung; Statusleiste und Sicherungsziel widersprüchlich

**Ort:** `src/klientenverwaltung/ui/main_window.py:142-157, 178-185`;
`ui/backup_management_dialog.py:198-209`
**Art:** Bestätigtes Problem
**Problem:** Menü „Sicherung → Jetzt sichern" meldet keinen Erfolg. Ohne Sicherungsordner landet
die Kopie auf der Datenplatte, die Statusleiste zeigt aber weiter „Keine Sicherungen eingerichtet".
Ein Sicherungsordner auf der Datenplatte selbst wird ohne Warnung akzeptiert.
**Warum es wichtig ist:** Der Anwender weiß nicht, ob und wo gesichert wurde.
**Beleg:** Code.
**Empfohlene Änderung:** Erfolgsmeldung mit Ziel; Statusleiste berücksichtigt Datenplatten-Kopien
(„nur auf der Datenplatte"); Warnung bei Ordner auf derselben Platte (vgl. M-10).
**Erwarteter Nutzen:** Klarheit über den Sicherungszustand. **Risiken / Hinweise:** Keine.

### [LOW] L-7: `alembic/env.py` konfiguriert bei jedem Start das Logging der Anwendung um und deaktiviert App-Logger

**Ort:** `alembic/env.py:13-16`; `src/klientenverwaltung/services/media_service.py:25, 504-510`
**Art:** Bestätigtes Problem (dokumentiertes Verhalten von `logging.config.fileConfig`)
**Problem:** `apply_migrations` → `env.py` → `fileConfig(alembic.ini)` mit
`disable_existing_loggers=True`: Alle zu diesem Zeitpunkt existierenden Logger, die nicht in
`alembic.ini` stehen – u. a. `klientenverwaltung.services.media_service` –, werden deaktiviert;
zusätzlich wird ein Root-Handler auf `stderr` installiert. Die Warnung in
`cleanup_orphaned_part_files` wird dadurch nie ausgegeben.
**Warum es wichtig ist:** Ungewollte Nebenwirkung; künftiges Logging würde still verschluckt.
**Beleg:** Aufrufreihenfolge in `main.py` (Import der Services vor `apply_migrations`).
**Empfohlene Änderung:** `fileConfig` nur im CLI-Pfad (keine übergebene Verbindung) oder mit
`disable_existing_loggers=False` aufrufen; bewusst festlegen, ob und wohin die App loggt (ohne
Inhalte, vgl. H-2).
**Erwarteter Nutzen:** Vorhersehbares Logging. **Risiken / Hinweise:** Keine.

### [LOW] L-8: Datenbank einer neueren Programmversion führt zu einem Absturz statt einer Meldung

**Ort:** `src/klientenverwaltung/storage.py:321-331`, `main.py:222-228`
**Art:** Mögliches Problem
**Problem:** Öffnet eine ältere `.exe` eine bereits weiter migrierte Datenbank (oder wird eine
Sicherung einer neueren Version wiederhergestellt), kennt Alembic die Revision nicht und wirft
`alembic.util.CommandError`. Das ist kein `SQLAlchemyError`, wird nicht zu `StorageError` →
Absturzdialog.
**Warum es wichtig ist:** Nach einem Update mit einer alten Verknüpfung/Kopie der `.exe` realistisch.
**Beleg:** Code.
**Empfohlene Änderung:** Aktuelle Revision gegen die bekannten prüfen, klare Meldung („… mit einer
neueren Programmversion bearbeitet …"); `CommandError` in `StorageError` übersetzen.
**Erwarteter Nutzen:** Verständliche Meldung. **Risiken / Hinweise:** Keine.

### [LOW] L-9: Die UUID der Kennungsdatei wird nie verglichen

**Ort:** `src/klientenverwaltung/storage.py:78-87, 140-160`; `config.py`
**Art:** Empfehlung
**Problem:** Die UUID wird nur auf Format geprüft. Eine geklonte Platte (z. B. 1:1-Kopie als
Sicherung) oder eine zweite eingerichtete Platte ist nicht unterscheidbar; über
`last_known_drive_path` wird ohne Mehrfachprüfung die Platte am letzten Laufwerksbuchstaben genommen.
**Warum es wichtig ist:** Versehentliches Arbeiten auf der Kopie statt dem Original.
**Beleg:** Code.
**Empfohlene Änderung:** UUID in `config.json` merken; bei Abweichung nachfragen.
**Erwarteter Nutzen:** Eindeutige Zuordnung. **Risiken / Hinweise:** Beim Wechsel auf eine neue
Platte muss eine Bestätigung möglich sein.

### [LOW] L-10: Mediendateinamen werden ohne Pfadprüfung verwendet

**Ort:** `src/klientenverwaltung/services/media_service.py:310-317, 382-388`
**Art:** Mögliches Problem (Defense in Depth)
**Problem:** `delete_unknown_file(stored_filename)` und `resolve_media_path_for_stored_filename()`
hängen den übergebenen Namen ungeprüft an den Medienordner. Heute stammen die Namen aus
`iterdir()`/DB. Hinter der geplanten Web-API wäre `..\klientenverwaltung.db` ein Pfad-Traversal, das
die Datenbank löschen könnte.
**Warum es wichtig ist:** Services sollen laut Architekturziel unverändert hinter eine API.
**Beleg:** Code.
**Empfohlene Änderung:** `Path(name).name == name` und aufgelöster Pfad innerhalb von
`self._media_dir.resolve()` prüfen, sonst `ValidationError`.
**Erwarteter Nutzen:** Robuste Service-API. **Risiken / Hinweise:** Keine.

### [LOW] L-11: Formatierung nicht erzwungen, minimaler Lint-Regelsatz, keine Typprüfung

**Ort:** `pyproject.toml:31-36`
**Art:** Bestätigtes Problem
**Problem:** `ruff format --check` würde 20 Python-Dateien (u. a. `services/media_service.py`,
`ui/report_dialog.py`, `ui/window_settings.py`, `ui/setup_wizard.py`, mehrere Tests/Skripte) und
4 Plan-Dokumente umformatieren. Aktiv ist nur der Ruff-Standardregelsatz (E4/E7/E9/F);
`ignore = ["DTZ"]` ist wirkungslos, weil DTZ nicht ausgewählt ist. „Typ-Hinweise überall"
(CLAUDE.md) prüft kein Werkzeug, obwohl `# type: ignore[...]`-Kommentare auf eine Typprüfung hindeuten.
**Warum es wichtig ist:** Stilabweichungen und Typfehler werden nicht automatisch gefunden.
**Beleg:** Lokale `ruff`-Läufe (siehe Methodik).
**Empfohlene Änderung:** `ruff format` einmalig in einem eigenen Commit anwenden; `select` um
z. B. `I`, `UP`, `B`, `SIM` erweitern; optional `pyright`/`mypy`; einfacher Pre-Commit-Schritt.
**Erwarteter Nutzen:** Einheitlicher Code, frühere Fehlererkennung. **Risiken / Hinweise:** Der
Formatierungs-Commit berührt viele Dateien – getrennt von inhaltlichen Änderungen halten.

### [LOW] L-12: Projektmetadaten – Platzhalterbeschreibung, Version doppelt gepflegt

**Ort:** `pyproject.toml:3-4`; `src/klientenverwaltung/__init__.py:1`
**Art:** Bestätigtes Problem
**Problem:** `description = "Add your description here"`. Die Version steht in `pyproject.toml` und
in `__version__` – obwohl `__init__.py` als „single source" beschrieben ist.
**Warum es wichtig ist:** Öffentliches Portfolio-Repo; Versionsdrift zwischen Paket und `.exe`.
**Beleg:** Dateien.
**Empfohlene Änderung:** Beschreibung setzen; Version aus einer Quelle (z. B. `importlib.metadata`).
**Erwarteter Nutzen:** Konsistente Metadaten. **Risiken / Hinweise:** Im Frozen-Build Verfügbarkeit
der Metadaten prüfen.

### [LOW] L-13: Skalierungsreserven – volle Tabellen-Scans und Zählungen über komplette Listen

**Ort:** `src/klientenverwaltung/repositories/treatment_session_repository.py:89-103`;
`alembic/versions/9ac5d775d208_create_base_schema.py` (keine Indizes),
`alembic/versions/c66a9fbe6d01_add_media_and_session_media_tables.py:41-55`;
`ui/client_overview_dialog.py:103-114`; `ui/client_detail_dialog.py:251-255`;
`ui/backup_table_model.py:75-79`; `ui/client_report_history_dialog.py:48-51, 98-114`
**Art:** Mögliches Problem (Skalierung; aktuell unkritisch)
**Problem:** `find_overlapping` lädt bei jedem Speichern *alle* vergangenen Sitzungen samt Klient.
Keine Indizes auf `session.client_id`, `session.date`, `session_media.media_id`. „Sitzungen (n)"
und „Berichte (n)" laden komplette Listen inkl. Bericht-HTML nur zum Zählen. `BackupTableModel`
ruft `stat()` bei jedem Neuzeichnen. Der Berichtsverlauf erzeugt pro Sitzung zwei `QTextEdit`.
**Warum es wichtig ist:** Nach einigen Jahren (Tausende Sitzungen) auf einer USB-Platte spürbar.
**Beleg:** Code.
**Empfohlene Änderung:** Untergrenze für die Überlappungsabfrage (`date > start - max_dauer`; die
480-Minuten-Grenze aus `ui/session_dialog.py:26` in den Service übernehmen); Indizes per Migration
(**nach H-3**); Count-Abfragen im Repository; Dateigröße beim Aufbau der `BackupEntry` ermitteln.
**Erwarteter Nutzen:** Gleichbleibend flüssige Bedienung. **Risiken / Hinweise:** Keine.

### [LOW] L-14: Meldungen mit ungekürzten Dateilisten bzw. ohne Angabe, was gelöscht wird

**Ort:** `src/klientenverwaltung/ui/dialogs.py:210-233`; `ui/media_cleanup.py:36-42`;
`ui/media_overview_dialog.py:248-252`
**Art:** Bestätigtes Problem
**Problem:** „Nicht mehr verwendete Mediendateien" listet alle Namen in einer Zeile – beim Löschen
eines Klienten mit vielen Dateien wird die Meldung riesig (auf 1366×768 ggf. nicht bedienbar).
Umgekehrt nennt die Löschbestätigung der Medienübersicht weder Anzahl noch Namen.
**Warum es wichtig ist:** Endgültiges Löschen braucht eine klare, lesbare Bestätigung.
**Beleg:** Code.
**Empfohlene Änderung:** Liste kürzen („… und 12 weitere", Details per `setDetailedText`); in der
Medienübersicht Anzahl und Gesamtgröße nennen.
**Erwarteter Nutzen:** Sichere Entscheidungen. **Risiken / Hinweise:** Keine.

### [LOW] L-15: Auswahl geht nach jedem Neuladen verloren; neuer Klient wird nicht markiert

**Ort:** `src/klientenverwaltung/ui/client_list_widget.py:158-177`
**Art:** Bestätigtes Problem
**Problem:** Nach Bearbeiten, Archivieren oder „Neu" setzt das Modell zurück; die Auswahl ist weg,
ein neu angelegter Klient muss gesucht werden.
**Warum es wichtig ist:** Unnötige Suche nach jeder Aktion.
**Beleg:** `set_entries` mit `beginResetModel`.
**Empfohlene Änderung:** ID vor dem Reload merken, danach wieder auswählen (`scrollTo`); nach „Neu"
den neuen Klienten auswählen.
**Erwarteter Nutzen:** Flüssigerer Ablauf. **Risiken / Hinweise:** Keine.

### [LOW] L-16: Datumseingabe umständlich, keine Plausibilitätsprüfung

**Ort:** `src/klientenverwaltung/ui/optional_date_edit.py:13-20`; `services/client_service.py:87-128`
**Art:** Empfehlung
**Problem:** Datum erst über das Häkchen „angegeben" freischalten; Startwert „heute" (für ein
Geburtsdatum viel Kalenderblättern). Keine Plausibilitätsprüfung (Geburtsdatum in der Zukunft →
negatives Alter in der Übersicht; Einwilligung in der Zukunft).
**Warum es wichtig ist:** Häufige Eingabe, nicht-technischer Anwender.
**Beleg:** Code.
**Empfohlene Änderung:** Häkchen automatisch setzen, sobald ein Datum eingegeben wird; für das
Geburtsdatum direkte Tastatureingabe betonen; Plausibilitätsprüfungen im Service (`ValidationError`).
**Erwarteter Nutzen:** Schnellere, fehlerärmere Eingabe. **Risiken / Hinweise:** Keine.

### [LOW] L-17: Mehrfachstart wird nicht verhindert

**Ort:** `src/klientenverwaltung/main.py:289-315`; eingeräumt in `services/media_service.py:485-492`
**Art:** Mögliches Problem
**Problem:** Die Anwendung kann mehrfach gleichzeitig gegen dieselbe Datenbank laufen (z. B.
Doppelklick auf die `.exe` während des Splash). Folgen: zwei Passwortabfragen, veraltete Listen,
„letzter Speichernder gewinnt" bei `update_client` (alle Felder werden überschrieben), „database is
locked"-Fehler (vgl. H-2/M-4), Wiederherstellung scheitert an gesperrter Datei.
**Warum es wichtig ist:** Verwirrende Zustände bei einem nicht-technischen Anwender.
**Beleg:** Kein Einzelinstanz-Mechanismus im Code.
**Empfohlene Änderung:** Einzelinstanz-Sperre (z. B. `QLockFile` in `%APPDATA%`) mit Hinweis
„Das Programm läuft bereits".
**Erwarteter Nutzen:** Eindeutiger Zustand. **Risiken / Hinweise:** Veraltete Sperrdatei nach
Absturz behandeln (`QLockFile` erkennt das).

### [LOW] L-18: Auslieferung – UPX und fehlende Signatur

**Ort:** `klientenverwaltung.spec:50`, `klientenverwaltung-debug.spec:50`; `docs/build.md`
**Art:** Empfehlung
**Problem:** Nicht signierte Onefile-`.exe` mit `upx=True`: erhöhtes Risiko von
Virenscanner-Fehlalarmen; SmartScreen warnt; die Windows-11-„Intelligente App-Steuerung" (Smart App
Control) kann nicht signierte Programme vollständig blockieren.
**Warum es wichtig ist:** Ein nicht-technischer Anwender scheitert eventuell schon am Start.
**Beleg:** Spec-Dateien.
**Empfohlene Änderung:** `upx=False`; Zustand der App-Steuerung auf dem Ziel-Laptop prüfen;
mittelfristig Code-Signatur; in `docs/build.md` dokumentieren.
**Erwarteter Nutzen:** Reibungslose Auslieferung. **Risiken / Hinweise:** Etwas größere `.exe`.

### [LOW] L-19: `config.json` wird nicht atomar geschrieben; Beschädigung deaktiviert Sicherungen still

**Ort:** `src/klientenverwaltung/config.py:25-59`
**Art:** Mögliches Problem
**Problem:** Die Datei wird direkt überschrieben; eine beschädigte Datei wird still als `{}`
gelesen → der Sicherungsordner ist „vergessen", automatische Sicherungen sind aus (nur
Statusleiste). JSON, das kein Objekt ist, führt zu `AttributeError`.
**Warum es wichtig ist:** Stiller Verlust der Sicherungskonfiguration.
**Beleg:** Code.
**Empfohlene Änderung:** Schreiben über Temp-Datei + `replace()`; bei unlesbarer Datei einmal
warnen; Typ prüfen.
**Erwarteter Nutzen:** Robuste Konfiguration. **Risiken / Hinweise:** Keine.

### [LOW] L-20: Gemischte Zeitstempel-Konventionen (UTC vs. lokal)

**Ort:** `src/klientenverwaltung/models/client.py:33-36`, `models/session.py:25-28`,
`models/media.py:20-29, 41-43`, `services/client_service.py:257-268`
**Art:** Empfehlung
**Problem:** `client.created_at/updated_at` und `session.created_at/updated_at` sind UTC
(`CURRENT_TIMESTAMP`), `media.created_at`, `session_media.added_at` und `session.date` lokal. Gut
kommentiert, aber fehleranfällig; unter PostgreSQL ändert sich zudem die Semantik von `func.now()`.
**Warum es wichtig ist:** Jede neue Anzeige muss die jeweilige Konvention kennen.
**Beleg:** Modelle.
**Empfohlene Änderung:** Einheitliche Konvention festlegen und in CLAUDE.md dokumentieren.
**Erwarteter Nutzen:** Weniger Zeitzonen-Fehler. **Risiken / Hinweise:** Umstellung braucht Datenmigration.

### [LOW] L-21: Sicherungen mit Kollisions-Suffix `_2` werden als „unbekannt" angezeigt

**Ort:** `src/klientenverwaltung/backup.py:31-39, 97-110`; `ui/main_window.py:151-153`;
`ui/backup_table_model.py:71-72`
**Art:** Bestätigtes Problem
**Problem:** Zwei Sicherungen in derselben Sekunde (z. B. Doppelklick auf „Jetzt sichern") → die
zweite heißt `…_HHMMSS_2.db`; `parse_backup_timestamp` scheitert („unconverted data remains") →
Tabelle „unbekannt", Statusleiste „Letzte Sicherung: unbekannt".
**Warum es wichtig ist:** Verunsichernde Anzeige.
**Beleg:** Code.
**Empfohlene Änderung:** Suffix `_<n>` vor dem Parsen abtrennen; Test ergänzen.
**Erwarteter Nutzen:** Korrekte Anzeige. **Risiken / Hinweise:** Keine.

### [LOW] L-22: Dokumentation teilweise veraltet oder unvollständig

**Ort:** `docs/projekt-kontext.md:3-8, 40-47, 91, 120-122`; `TODO.md:37-39`; `README.md:17-20, 22-37`
**Art:** Bestätigtes Problem
**Problem:** `projekt-kontext.md` nennt „drei Tabellen", „Phase C … nächste offene Phase",
„152 Tests"; `TODO.md` führt Phase C als „Umfang noch nicht festgelegt", obwohl C1/C2 umgesetzt
sind. Das README erwähnt die Medienverwaltung nicht; die Aussage, die Daten lägen verschlüsselt auf
der Platte, gilt für Mediendateien nicht. Screenshots sind Platzhalter.
**Warum es wichtig ist:** Übergabedokumente und öffentliches README sollen den Ist-Stand zeigen.
**Beleg:** Dateien.
**Empfohlene Änderung:** Kontext/TODO aktualisieren; README-Abschnitt „Medien" inkl. Hinweis auf
fehlende Verschlüsselung/Sicherung. *Präferenz:* die rund 6.000 Zeilen `docs/superpowers/plans/`
als historisch kennzeichnen.
**Erwarteter Nutzen:** Verlässliche Dokumentation. **Risiken / Hinweise:** Keine.

### [LOW] L-23: Startdialoge außer der Passwortabfrage werden nicht vor den Splash geholt

**Ort:** `src/klientenverwaltung/main.py:62-87, 204-228`; `ui/dialogs.py`; vgl.
`ui/password_dialog.py:50-65`
**Art:** Mögliches Problem (manuell zu prüfen)
**Problem:** Laut Kommentar in `ask_for_password` kann der Splash Dialoge verdecken bzw. ihnen den
Tastaturfokus nehmen; deshalb wird dort explizit `show()/raise_()/activateWindow()` aufgerufen. Die
übrigen Startdialoge („Datenplatte nicht gefunden", „Falsches Passwort", Sicherungs-/
Migrationsfehler, Einrichtungsassistent) bekommen diese Behandlung nicht.
**Warum es wichtig ist:** „Datenplatte nicht gefunden" ist der häufigste Startdialog.
**Beleg:** Code und Kommentar.
**Empfohlene Änderung:** In der gebauten `.exe` prüfen; ggf. gemeinsamen Helfer für alle
Startdialoge oder Splash vor modalen Dialogen ausblenden.
**Erwarteter Nutzen:** Kein „hängender" Splash. **Risiken / Hinweise:** Keine.

### [LOW] L-24: Vier Services werden durch alle Dialogebenen gereicht

**Ort:** `src/klientenverwaltung/ui/client_list_widget.py:38-50`, `ui/client_overview_dialog.py:39-53`,
`ui/client_detail_dialog.py:48-62`, `ui/main_window.py:37-46`, `main.py:230-244`
**Art:** Empfehlung
**Problem:** Dieselben vier Services wandern durch jeden Konstruktor (5–7 Parameter); jeder neue
Service (z. B. für Termine) ändert alle Konstruktoren.
**Warum es wichtig ist:** Wartungsaufwand wächst mit jeder Funktion.
**Beleg:** Konstruktoren.
**Empfohlene Änderung:** Ein `AppServices`-Dataclass (frozen) bündeln und übergeben.
**Erwarteter Nutzen:** Schlankere Signaturen. **Risiken / Hinweise:** Rein mechanische Änderung.

### [LOW] L-25: Behandlungsarten – Namensduplikate per Groß-/Kleinschreibung möglich, „Löschen" auch bei verwendeten Arten aktiv

**Ort:** `src/klientenverwaltung/services/treatment_type_service.py:22-37, 95-117`;
`repositories/treatment_type_repository.py:24-26`; `ui/treatment_type_management_dialog.py:118-123`
**Art:** Bestätigtes Problem
**Problem:** Die Eindeutigkeit ist case-sensitiv („Meditation" und „meditation" möglich).
„Löschen" ist auch für verwendete Arten aktiv und scheitert erst mit Fehlermeldung; die
Medienübersicht löst denselben Fall vorbildlich per deaktiviertem Button + Tooltip.
**Warum es wichtig ist:** Doppelte Einträge in Auswahllisten; unnötige Fehlermeldung.
**Beleg:** Code.
**Empfohlene Änderung:** Namensvergleich per `casefold()` im Service; Löschen-Button bei Verwendung
deaktivieren, Tooltip „Wird in n Sitzungen verwendet – bitte deaktivieren".
**Erwarteter Nutzen:** Saubere Stammdaten, klarere Bedienung. **Risiken / Hinweise:** Keine.

---

## Code Quality

**Gesamteindruck: hoch.** Konsistente Benennung, durchgängige Typ-Hinweise, überwiegend kleine
Funktionen, benannte Konstanten statt magischer Zahlen, und Docstrings, die Entscheidungen samt
Begründung festhalten (z. B. `window_settings.finalize_column_widths`, `report_dialog.strip_disallowed_formatting`,
`media_service._process_file`). Toter Code wurde nicht gefunden.

Beobachtungen:
- **Duplizierte Fehlerbehandlung:** rund 20 gleichartige `try/except ServiceError → show_error`-Blöcke
  in `ui/`; ein zentraler Helfer (M-4) reduziert das.
- **Tabellenmodelle:** sechs Modelle wiederholen `rowCount`/`columnCount`/`headerData` fast
  identisch – eine kleine gemeinsame Basisklasse wäre möglich (*Präferenz*).
- **`with transaction(session, …): pass`** als reines Commit liest sich ungewohnt; ein
  `commit(session, meldung)`-Helfer wäre sprechender (*Präferenz*).
- **Zwei Größenformatierer** mit unterschiedlicher Konvention (`ui/backup_table_model.py:17-22`
  „1.4 MB" mit Punkt vs. `ui/media_table_model.py:14-23` „1,4 MB" mit Komma) – in einer deutschen
  Oberfläche einheitlich mit Komma formatieren.
- **Legacy-Schlüssel** `client_detail/session_table_header_state` in
  `ui/client_sessions_dialog.py:45` stammt aus der Zeit vor der Auslagerung; bewusst behalten wäre
  einen Kommentar wert.
- **Formatierung/Werkzeuge:** siehe L-11.

## Architecture

**Stärken:** Die vier Schichten sind klar getrennt; Services importieren kein Qt, Repositories
enthalten alle Abfragen und keine SQLite-spezifischen Konstrukte; Lösch- und Nutzungsregeln sind
doppelt abgesichert (Datenbank: `CASCADE`/`RESTRICT`; Service: Vorabprüfung mit deutscher Meldung).
DTOs für Liste und Medien zeigen bereits das Zielbild.

**Abweichungen / Risiken:**
- UI arbeitet mit ORM-Entitäten (M-12).
- UI spricht direkt mit Infrastrukturmodulen `storage`, `backup`, `config`
  (`ui/main_window.py`, `ui/backup_management_dialog.py`, `ui/setup_wizard.py`); für das Web-API-Ziel
  bräuchte es z. B. einen `BackupService` (*Empfehlung*, für den Desktop pragmatisch vertretbar).
- Dienste über mehrere Services hinweg sind bewusst nicht atomar (z. B. Klient löschen, danach
  Medien aufräumen) – vertretbar, weil die Medienübersicht beide Abweichungen erkennt.

**Wo Wachstum zuerst wehtut:**
1. Schemaänderungen (H-3) – bevor sie sicher sind, ist jede geplante Erweiterung riskant.
2. ORM-Objekte in der UI (M-12) – blockiert eine API und erzeugt Lazy-Loading-Fallen.
3. Suche und Sortierung mit SQLite-Semantik (M-3, L-3).
4. Uneinheitliche Zeitstempel (L-20) beim Umzug auf PostgreSQL.
5. Konstruktor-Parameterketten (L-24) bei jedem neuen Service (z. B. Terminübersicht).

## Bugs & Edge Cases

Bestätigte Fehler: H-1, H-4, M-1, M-2, M-3, M-5, M-6, L-1, L-3, L-4, L-21, L-25.
Randfälle mit möglichem Fehlverhalten: L-8, L-17, L-19, L-23.

Weitere Beobachtungen ohne eigenen Befund:
- **Medienimport:** Die Datei wird vor dem Datenbank-Commit endgültig umbenannt
  (`media_service.py:269` vs. `:241`); scheitert der Commit, bleibt eine „Unbekannte Datei". Beim
  Löschen wird die Datei vor dem Commit entfernt (`:371-378`); scheitert der Commit, zeigt die
  Übersicht „Datei fehlt". Beides wird von der Medienübersicht erkannt – akzeptabel, sollte aber in
  CLAUDE.md als bewusste Reihenfolge stehen.
- **Grenzfall „genau jetzt":** Das Repository zählt `date >= now` als kommend, `SessionTableModel`
  hebt nur `date > now` fett hervor – praktisch bedeutungslos.
- **Zeitverhalten beim Start:** Startsicherung und „Jetzt sichern" laufen synchron auf dem
  GUI-Thread; bei der aktuellen DB-Größe unkritisch, bei einem hängenden Netzwerk-Sicherungsordner
  aber blockierend (gleiche Ursache wie M-5).

## Security

**Stärken:** SQLCipher-Verschlüsselung mit sofortiger Schlüsselprüfung; Mindestlänge 12 und
ausdrückliche Bestätigung „Passwort verloren = Daten verloren"; Passwort wird nicht gespeichert;
`config.json` enthält nur Pfade; Mediendateien mit UUID-Namen (kein Klientenname in „Zuletzt
verwendet"-Listen); nach dem Import ausdrücklicher Hinweis, das Original zu löschen;
`VACUUM INTO` erzeugt verschlüsselte Sicherungen; Temp-Dateien nur für Icons (keine Inhalte).

**Befunde:** H-1 (Passwort/URL, Passwortfragment im Log), H-2 (Klientendaten im Log), M-7
(kein Passwortwechsel), M-8 (Bildverweise auf Laptop-Dateien), L-10 (Pfadprüfung), L-17 (Mehrfachstart).

**Bekannte, dokumentierte Restrisiken** (`TODO.md`, „Vor der Übergabe"): Mediendateien liegen
unverschlüsselt auf der Datenplatte und werden nicht gesichert. **Empfehlung:** vor dem Speichern
echter Aufnahmen verbindlich lösen (BitLocker To Go setzt zum *Einrichten* Windows Pro voraus;
alternativ VeraCrypt oder eigene Verschlüsselung).

**Weitere Hinweise (ohne eigenen Befund):**
- Externe Programme, mit denen Medien geöffnet werden, können Spuren auf dem Laptop hinterlassen
  (Miniaturansichten, Caches, „Zuletzt verwendet"); die UUID-Namen mildern das.
- Kopierter Berichtstext kann im Windows-Zwischenablageverlauf (Win+V) bzw. in der
  Cloud-Zwischenablage landen – Anwender darauf hinweisen oder die Synchronisation deaktivieren lassen.
- Keine automatische Sperre bei Inaktivität; bei Klienten im Raum ist eine optionale Sperre
  (erneute Passworteingabe) überlegenswert.
- DSGVO Art. 15/20 (Auskunft, Datenübertragbarkeit): Ein Export je Klient (z. B. PDF) fehlt; er steht
  unter „Später" in `TODO.md` und wäre als ausdrückliche Nutzeraktion mit CLAUDE.md vereinbar.
- Sicherungsordner in Cloud-synchronisierten Ordnern (z. B. OneDrive) übertragen verschlüsselte
  Gesundheitsdaten an Dritte – beim Auswählen warnen.

## Performance

- **Aktuell:** Keine Performanceprobleme bei der Zielgröße (ein Anwender, einige hundert Klienten).
  Die Klientensuche ist entprellt (250 ms), der Medienimport läuft im Hintergrund, blockweise und in
  einem einzigen Lesedurchgang.
- **Aktuelles Problem:** blockierende Laufwerkssuche (M-5).
- **Skalierungsreserven:** L-13 (Überlappungsabfrage, fehlende Indizes, Zählungen über komplette
  Listen, `stat()` beim Zeichnen, viele `QTextEdit` im Berichtsverlauf).

## UX / Usability

**Stärken:** Durchgängig Deutsch mit „Klient"; sichere Standardwahl bei Lösch-/Wiederherstellungsdialogen
(„Abbrechen"); Rückfrage bei ungespeicherten Änderungen in allen Formularen; Klientenübersicht ohne leere
Felder; „–" statt leerer Flächen; reservierter Platz für Fehlermeldungen; Hinweisdialog mit direktem Weg zur
Anlage einer Behandlungsart; Fenster merken Größe, Position und Spalten.

**Befunde:** H-4, M-2, M-3, M-6, M-10, L-1, L-3, L-4, L-6, L-14, L-15, L-16, L-23, L-25.

**Weitere Hinweise:**
- Im Klientenformular liegt „Speichern" im scrollbaren Bereich zwischen Stammdaten und Notizen,
  „Schließen" dagegen fest unten (`ui/client_detail_dialog.py:109-114, 151-178`). Auf kleinen
  Bildschirmen kann „Speichern" aus dem Blick scrollen; üblicher wäre „Speichern" neben
  „Schließen" (*Empfehlung*).
- „Einstellungen" enthält auch Nicht-Einstellungen (Behandlungsarten, Medienübersicht) – laut
  CLAUDE.md bewusst so; für die Auffindbarkeit wäre ein Menü „Verwaltung" denkbar (*Präferenz*).

## UI / Design

**Stärken:** Zentrale Palette mit vollständigen Rollen, vollständig definierte Zustände für Buttons,
Eingabefelder, Spinboxen (inkl. korrigierter Klickflächen) und Comboboxen, eigene Pfeil-Icons,
Theme-Wechsel zur Laufzeit ohne Neustart, warme, ruhige Farbwelt.

**Befunde:** M-9 (Farbe archivierter Zeilen), M-13 (Scrollbalken), L-5 (Fokus = Standard-Button).
Dazu uneinheitliche Größenformate (siehe Code Quality).

## Accessibility

**Stärken:** Schrift global +2 pt (`main.py:306-308`), Buttons mit `min-height: 30px`, breiter
Splitter-Griff, archivierte Einträge zusätzlich kursiv (nicht nur farblich), kommende Sitzungen fett,
`QFormLayout`-Beschriftungen als Buddies (für Screenreader nutzbar).

**Befunde:** M-9 (Kontrast ≈ 2,9 : 1 im Dunkelmodus), L-5 (Fokusdarstellung, Tastaturkürzel),
M-13 (schwer greifbarer Scrollgriff).

**Weitere Hinweise:** Die Checkbox im Einrichtungsassistenten hat keinen eigenen Text
(`ui/setup_wizard.py:169-178`, Text im separaten `_CheckboxLabel`) – für Screenreader
`setAccessibleName` setzen; ebenso für die reinen Icon-Buttons F/K/U im Berichtseditor.

## Testing

**Stärken:** 198 Tests, alle grün, Laufzeit ≈ 11 s; `%APPDATA%` und `QSettings` in den
betroffenen Tests isoliert; Regressionstests zu konkreten früheren Fehlern (Thread-Verdrahtung,
`LoadingDialog.finish()`, Sortier-Desync, Header-Zustand); gründliche Service-Tests inklusive
Grenzfällen (Überlappung, leere Berichte, Duplikate, Abbruch).

**Befunde:** M-11 sowie die bei den einzelnen Befunden genannten Regressionstests.

**Weitere Hinweise:**
- `tests/conftest.py` setzt `QT_QPA_PLATFORM` nicht; in einer künftigen CI ohne Display müsste
  `offscreen` gesetzt werden.
- Dialogtests, die `QSettings()` ohne Isolation nutzen, schreiben in die Registry des
  Entwicklers (Organisation „Unknown Organization") – harmlos, aber für saubere Testläufe
  überall die `isolated_settings`-Fixture aus `tests/test_window_settings.py` nutzen.
- Keine CI – zumindest `pytest` + `ruff check` + `ruff format --check` vor jedem Commit.

## Dependencies

- **Schlank und passend:** vier Laufzeitabhängigkeiten (`alembic`, `pyside6`, `sqlalchemy`,
  `sqlcipher3-wheels`), drei Dev-Abhängigkeiten; Versionen per `uv.lock` fixiert; keine
  ungenutzten oder doppelten Bibliotheken gefunden.
- `sqlcipher3-wheels` ist ein Community-Paket, das SQLCipher als Wheel mitbringt – die Wahl ist
  nachvollziehbar (Windows-Build von SQLCipher ist aufwendig). *Empfehlung:* SQLCipher-Sicherheitsmeldungen
  im Blick behalten und die enthaltene Version dokumentieren (`PRAGMA cipher_version`).
- *Optional:* `pyside6-essentials` statt des Meta-Pakets `pyside6` verkleinert die Entwicklungsumgebung
  (QtWidgets/QtGui/QtSvg/QtTest sind enthalten); die `.exe` bündelt ohnehin nur genutzte Module.
- UPX/Signatur: L-18.

## Documentation

**Stärken:** `CLAUDE.md`, `docs/ui-regeln.md` und `docs/build.md` halten Regeln *und* die Lehren
aus konkreten Fehlern fest (z. B. Qt-Stylesheets, Thread-Signale, Hidden Imports). Die Docstrings
sind außergewöhnlich aussagekräftig. Das README erklärt Architektur- und Technologieentscheidungen
samt Begründung.

**Befunde:** L-22 (veraltete Stellen, fehlender Medienabschnitt), L-12 (Platzhalterbeschreibung).

**Fehlt:**
- Warnung zu Batch-Migrationen und Fremdschlüsseln (H-3) in den Build-/Migrationsregeln.
- Ein kurzes Notfallblatt für den Anwender (Platte nicht gefunden, Wiederherstellung, Passwort
  vergessen = Daten verloren, Medien nicht gesichert).

## Positive Aspects

- **Datensicherheit durchdacht:** Pflichtsicherung vor Migrationen; `VACUUM INTO` statt Dateikopie
  bei offener Datenbank; atomare Wiederherstellung über Temp-Datei + `replace()`; eigene Rotation für
  Sicherungen vor einer Wiederherstellung; Sekundenkollision bei Dateinamen abgefangen.
- **Löschregeln konsequent:** Klient löschen kaskadiert (keine verwaisten Gesundheitsdaten),
  verwendete Behandlungsarten nur deaktivierbar, Mediendateien nie automatisch gelöscht,
  Nachfrage „jetzt endgültig löschen?" mit „Behalten" als Standard.
- **Medienimport vorbildlich:** Größenvorfilter + SHA-256 für Duplikate, ein Lesedurchgang für
  Hash und Kopie, `fsync`, `.part`-Dateien mit Aufräumen beim Start, Abbruch per `threading.Event`
  mit bewusst gewählter `DirectConnection`, Duplikatfrage per `BlockingQueuedConnection`,
  Fangnetz für Nicht-`ServiceError` im Worker.
- **Klare Schichten:** Services ohne Qt, Repositories als einziger Ort für Abfragen,
  `transaction()`-Helfer, deutsche `ServiceError`-Hierarchie.
- **Robuste Fensterlogik:** Geometrie auf den sichtbaren Bildschirmbereich begrenzt,
  Tabellenlayouts anhand der Spaltenüberschriften versioniert, Spalten füllen stets die Breite.
- **Datenschutzbewusste UX:** Hinweis zum Löschen des Originals nach dem Import, UUID-Dateinamen,
  keine Klientendaten in `QSettings`/`config.json`.
- **Letztes Fangnetz:** globaler `excepthook` mit deutscher Meldung statt stillem Beenden des
  Fensterbuilds.
- **Build durchdacht:** gemeinsame Spec-Konfiguration, Versionsressource aus einer Quelle,
  dokumentierte Hidden Imports, Release- und Debug-Variante, kein SVG zur Laufzeit.
- **Tests schnell und aussagekräftig**, mit Regressionstests für reale Fehler.

---

# Recommended Implementation Roadmap

Reihenfolge nach Risiko und Abhängigkeiten. Wichtige Abhängigkeiten:
**H-1 vor M-7** (Rekey braucht einheitliche Schlüsselbehandlung) und **H-3 vor jeder Migration**
(auch den Migrationen aus H-4 und L-13).

## Phase 1 — Critical / Security

- [ ] **H-1 – Passwort sicher an SQLCipher übergeben:** In `storage.create_encrypted_engine`
  `URL.create("sqlite+pysqlcipher", password=…, database=…)` statt f-String-URL verwenden.
  Test: Einrichtung + Login mit `@`, `%41`, `"`, `:`, `/`, `?`, `#`, Umlauten.
- [ ] **H-2 – Keine Parameter in Ausnahmen/Logs:** `hide_parameters=True` in
  `create_encrypted_engine`; `_log_and_show_crash` loggt keine Meldungstexte von
  `sqlalchemy.exc.*` (auch verkettet). Test mit einer `StatementError` und Parameterwert.
- [ ] **H-3 – Migrationen ohne Fremdschlüssel-Kaskade:** In `alembic/env.py` vor den Migrationen
  `PRAGMA foreign_keys=OFF`, danach `PRAGMA foreign_key_check` (leer, sonst `StorageError`) und
  `PRAGMA foreign_keys=ON`. Test: befüllte DB, Test-Migration mit `recreate="always"` für `client`
  und `session`, Zeilenzahlen unverändert. Warnung in `docs/build.md`.
- [ ] **M-1 – Einrichtung atomar machen:** In `set_up_data_drive` zuerst DB anlegen/migrieren,
  zuletzt Kennungsdatei schreiben; Aufräumen bei jeder Ausnahme; `SetupWizard` fängt `Exception`
  mit verständlicher Meldung; beim Start „Kennungsdatei ohne DB" erkennen und Einrichtung anbieten.

## Phase 2 — High Priority

- [ ] **H-4 – Termine auf Minuten normalisieren:** `date.replace(second=0, microsecond=0)` in
  `create_session`/`update_session`; Startwert im `SessionDialog` auf volle (Viertel-)Stunde;
  Datenmigration für Bestandsdaten (nach H-3). Test mit „krummen" Sekunden.
- [ ] **M-2 – Historische Behandlungsart beim Bearbeiten zulassen:** Aktiv-Prüfung in
  `update_session` nur bei geänderter `treatment_type_id`. Zwei Tests.
- [ ] **M-3 – Suche reparieren:** Begriffe an Leerzeichen trennen (UND über Begriffe, ODER über
  Spalten), Unicode-sicherer Vergleich (`casefold` im Service o. Ä.), Platzhalter escapen; gleiches
  Muster für `list_unlinked_for_session`. Tests mit Umlauten und Vor-/Nachname.
- [ ] **M-4 – Fehlergrenze schließen:** Lese-Wrapper in `services/` (`SQLAlchemyError` →
  `ServiceError`); `DataUnavailableError` für getrennte Platte; zentraler UI-Helfer
  `call_service(...)` und Einsatz an allen Lese-Aufrufstellen (Liste in M-4).
- [ ] **M-5 – Laufwerkssuche wirklich begrenzen:** Daemon-Threads mit Deadline statt
  `with ThreadPoolExecutor`; Netz-/CD-Laufwerke überspringen; Test mit Zeitschranke; Assistent
  (`describe_drive`, `drive_already_set_up`) ebenso absichern.
- [ ] **M-6 – Wiederherstellung sicher und umkehrbar:** Sicherungen aus `vor-wiederherstellung`
  im Dialog anzeigen und wiederherstellbar machen; Sicherung vor dem Überschreiben lesend prüfen
  (Schlüssel, `quick_check`, Alembic-Revision); Meldungstext korrigieren.
- [ ] **M-7 – „Passwort ändern" (nach H-1):** Dialog + `storage.change_password` mit
  Pflichtsicherung und `PRAGMA rekey`; Hinweis zu alten Sicherungen; Wiederherstellung fragt ggf.
  das alte Passwort ab.
- [ ] **M-8 – Einfügen im Berichtseditor bereinigen:** Bilder, Links und Tabellen beim Einfügen
  und vor dem Speichern entfernen/umwandeln; Test mit Word-typischem HTML.
- [ ] **M-10 – Sicherungsstrategie:** Sicherung beim Beenden (nur bei Änderungen); Unverändert-Prüfung
  nur gegen den konfigurierten Ordner; wiederkehrender Hinweis ohne Sicherungsordner; Warnung bei
  Ordner auf der Datenplatte.

## Phase 3 — Architecture / Maintainability

- [ ] **M-12 – DTOs statt ORM-Objekten in der UI:** Beginnend mit `TreatmentSession`, dann
  `Client`, `TreatmentType`, `Media`; danach Architekturtest „`ui/` importiert keine Modelle".
- [ ] **L-24 – `AppServices`-Dataclass** statt vier einzelner Service-Parameter.
- [ ] **L-7 – Logging-Konfiguration aus `env.py` entschärfen** (`fileConfig` nur im CLI-Pfad oder
  `disable_existing_loggers=False`).
- [ ] **L-8 – DB neuer als Programm** erkennen und verständlich melden; `CommandError` →
  `StorageError`.
- [ ] **L-9 – UUID der Datenplatte merken** und bei Abweichung nachfragen.
- [ ] **L-10 – Pfadprüfung** in `delete_unknown_file`/`resolve_media_path_for_stored_filename`.
- [ ] **L-19 – `config.json` atomar schreiben**, beschädigte Datei melden.
- [ ] **L-20 – Zeitstempel-Konvention** festlegen und dokumentieren.
- [ ] **L-11 – Werkzeuge:** `ruff format` in eigenem Commit, erweiterter Regelsatz, optional Typprüfer.
- [ ] **L-12 – Projektmetadaten:** Beschreibung, Version aus einer Quelle.

## Phase 4 — UX / UI

- [ ] **M-9 – Theme-Farben in Tabellenmodellen:** `current_palette()` in `theme.py`, genutzt von
  `ClientTableModel` und `TreatmentTypeTableModel`.
- [ ] **M-13 – Scrollbalken vollständig stylen** (Breite, Griff-Mindestgröße, `add-page`/`sub-page`,
  `add-line`/`sub-line`, Hover/Pressed); auf 1366×768 und bei 125 %/150 % prüfen.
- [ ] **L-1 – Text im Einrichtungsassistenten** korrigieren.
- [ ] **L-2 – Umlaute/ß** in den Meldungen aus `storage.py`.
- [ ] **L-3 – Standard-Sortierung** Nachname aufsteigend, deutsche Kollation (`QCollator`).
- [ ] **L-4 – Formular nach dem Speichern** mit normalisierten Werten neu befüllen.
- [ ] **L-5 – Tastatur/Fokus:** eigene Fokusdarstellung, Strg+S/Strg+Enter in allen
  Formularen mit mehrzeiligen Feldern, Doppelklick/Enter einheitlich.
- [ ] **L-6 – „Jetzt sichern"** mit Rückmeldung, korrekte Statusleiste.
- [ ] **L-14 – Lange Dateilisten** in Meldungen kürzen; Löschbestätigung mit Anzahl/Größe.
- [ ] **L-15 – Auswahl nach Neuladen** erhalten; neuen Klienten markieren.
- [ ] **L-16 – Datumseingabe** vereinfachen, Plausibilitätsprüfungen im Service.
- [ ] **L-23 – Startdialoge vor den Splash holen** (erst in der `.exe` prüfen).
- [ ] **L-25 – Behandlungsarten:** Namensvergleich per `casefold`, Löschen-Button bei Verwendung deaktivieren.

## Phase 5 — Testing

- [ ] **M-11 – Test „Migrationen = Modelle"** per `alembic.autogenerate.compare_metadata`.
- [ ] **M-11 – Migrationstest mit Daten** (deckt H-3 dauerhaft ab).
- [ ] **M-11 – `_run_startup_backup`-Entscheidungsmatrix** testen.
- [ ] **M-11 – Dirty-Check/Speichern** für `ClientDetailDialog` und `SessionDialog`.
- [ ] **Regressionstests zu den Befunden** H-1, H-2, H-4, M-2, M-3, M-5 (Zeitschranke), M-8, L-21.
- [ ] Optional: `QT_QPA_PLATFORM=offscreen` in `conftest.py`, `QSettings` in allen Dialogtests isolieren.

## Phase 6 — Cleanup / Nice-to-have

- [ ] **L-13 – Skalierung:** Untergrenze für `find_overlapping`, Indizes per Migration (nach H-3),
  Count-Abfragen, Dateigröße im `BackupEntry` zwischenspeichern.
- [ ] **L-17 – Einzelinstanz-Sperre** (`QLockFile`).
- [ ] **L-18 – Auslieferung:** `upx=False`, App-Steuerung auf dem Ziel-Laptop prüfen, Signatur erwägen.
- [ ] **L-21 – Suffix `_2`** beim Parsen des Sicherungszeitstempels berücksichtigen.
- [ ] **L-22 – Dokumentation aktualisieren** (Projektkontext, TODO, README-Abschnitt „Medien",
  Notfallblatt für den Anwender).

---

## Offene Fragen (zusätzlicher Kontext wäre hilfreich)

1. **Gibt es bereits echte Daten?** Entscheidet, ob H-1 eine Übergangslösung für `%XX`-Passwörter
   und H-4 eine Datenmigration braucht.
2. **Welche Windows-Edition hat der Ziel-Laptop, ist die Intelligente App-Steuerung aktiv?**
   Bestimmt die Lösung für verschlüsselte Medien (BitLocker To Go vs. VeraCrypt) und L-18.
3. **Wohin soll gesichert werden** (zweite USB-Platte, NAS, Cloud)? Beeinflusst M-10 und die
   Warnungen bei der Ordnerwahl.
4. **Kommen mehrere Behandlungsarten pro Sitzung bzw. eine Klientennummer?** Dann ist H-3 sofort
   dringlich.
5. **Fügt der Anwender Berichte aus Word ein?** Bestimmt die Dringlichkeit von M-8.
6. **Wie realistisch ist die Web-API?** Bestimmt die Priorität von M-12 und L-10.
