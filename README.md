# Klientenverwaltung

Desktop-Anwendung zur Klientenverwaltung für einen 1-Mann-Betrieb im Bereich energetischer
Heilarbeit (Heilsitzungen, Meditation, Chakrenausgleich u. Ä.). Verwaltet Klienten und
dokumentiert Sitzungen – lokal, ohne Internetanbindung, mit besonderem Augenmerk auf den
Schutz von Gesundheitsdaten.

> Ursprünglich als Auftragsarbeit für einen echten Praxisbetrieb entstanden. Dieses Repository
> zeigt den Quellcode als Arbeitsprobe; enthaltene Namen, Adressen und sonstige Beispieldaten
> sind ausnahmslos erfunden (siehe Abschnitt [Lizenz](#lizenz)).

## Für wen

- **Zielgruppe:** eine einzelne selbstständige Person mit eigener Praxis, kein technischer
  Hintergrund, ein Windows-11-Laptop.
- **Zweck:** Klientenstammdaten, Anliegen und Sitzungsverlauf an einem Ort verwalten, ohne
  Papierkartei und ohne Cloud-Dienst.
- **Datenschutz zuerst:** Sitzungsnotizen enthalten Angaben zu Gesundheit und Befinden –
  besondere Kategorien personenbezogener Daten nach Art. 9 DSGVO. Die Datenbank liegt deshalb
  SQLCipher-verschlüsselt auf einer externen USB-Festplatte, nie auf dem Laptop. Zu Sitzungen
  abgelegte Mediendateien liegen unverschlüsselt auf derselben Platte; ihr Schutz hängt von
  der Verschlüsselung der ganzen Platte ab (siehe `TODO.md`).

## Funktionen

- Klientenliste mit Suche (Groß-/Kleinschreibung und Umlaute egal, auch „Vorname Nachname“),
  Archiv, letzter Sitzung und nächstem Termin; Klientenübersicht und Stammdatenformular
- Sitzungen je Klient mit Überschneidungsprüfung (direkt anschließende Termine erlaubt),
  Bericht und Impulse mit einfacher Formatierung, Berichtsverlauf
- Medien (Bilder, Audio, Video) je Sitzung: Kopie auf die Datenplatte unter neutralem
  Dateinamen, Duplikaterkennung per SHA-256, Medienübersicht mit Abgleich Ordner ↔ Datenbank
- Behandlungsarten frei pflegbar, deaktivieren statt löschen
- Sicherungen beim Start und beim Beenden, geprüfte und umkehrbare Wiederherstellung,
  „Passwort ändern“ (SQLCipher-Rekey) ohne Neustart
- Hell- und Dunkel-Theme, vollständig per Tastatur bedienbar

## Screenshots

*(Platzhalter – Bilder folgen)*

Für eine aussagekräftige Übersicht wären folgende Screenshots hilfreich:

1. **Klientenliste** (Hauptfenster) – Suche, Filter „Archivierte anzeigen", Spalten „letzte
   Sitzung"/„nächster Termin", Light-Theme
2. **Klientendetail** – Stammdaten-Formular eines (erfundenen) Klienten
3. **Sitzungsfenster** eines Klienten – Liste vergangener/künftiger Sitzungen
4. **Einrichtungsassistent** – z. B. der Schritt zur Passwortvergabe
5. **Backup-Verwaltung** – Dialog mit Sicherungsübersicht und Wiederherstellung
6. **Dark-Theme** – dieselbe Ansicht wie (1), zum Vergleich Light/Dark

Am besten mit erfundenen Testdaten aufnehmen (z. B. „Anna Muster", wie in den Tests) und unter
`docs/screenshots/` ablegen.

## Architektur

Strikte Schichtentrennung, jede Schicht spricht nur mit der direkt darunter:

```
ui/  →  services/  →  repositories/  →  models/
```

- **`ui/`** – PySide6-Fenster und Dialoge. Keine Geschäftslogik, kein Datenbankzugriff.
- **`services/`** – Geschäftslogik und Validierung. Kennt keine Qt-Klassen.
- **`repositories/`** – einziger Ort mit SQLAlchemy-Sessions und Abfragen.
- **`models/`** – SQLAlchemy-Modelle.

**Warum diese Trennung:** `services/` und `repositories/` sollen unverändert hinter einer
späteren Web-API (z. B. FastAPI) weiterlaufen können, falls die Datenbank einmal auf einen
Server (PostgreSQL) umzieht. Deshalb bleiben SQLite-spezifische Eigenheiten auf `storage.py`
beschränkt, und die Oberfläche darf niemals direkt auf die Datenbank zugreifen.

**Warum SQLCipher:** Sitzungsnotizen sind Gesundheitsdaten. Statt eine eigene
Verschlüsselungslogik zu bauen, übernimmt SQLCipher transparent auf Datenbankebene, was sonst
leicht vergessen wird – jede neue Tabelle und jede neue Abfrage ist automatisch mitverschlüsselt,
ganz ohne Sonderfall im Anwendungscode.

**Warum Alembic:** Das Schema wird sich über die Nutzungsdauer weiterentwickeln (siehe
„Bewusste Entscheidungen" unten). Migrationen laufen beim Programmstart automatisch, mit
zwingender Sicherung davor – der Anwender verwaltet nie manuell ein Datenbankschema, es „passiert
einfach" beim nächsten Start.

**Warum eine Kennungsdatei statt Laufwerksbuchstabe:** Windows vergibt Laufwerksbuchstaben für
USB-Platten nicht zuverlässig gleich – je nachdem, was sonst noch angeschlossen ist, kann aus
`E:` beim nächsten Anstecken `F:` werden. Eine Datei `klientenverwaltung.id` mit fester UUID auf
der Platte macht die Erkennung unabhängig vom zugewiesenen Buchstaben: Alle Laufwerke werden
durchsucht, das mit passender Kennung ist „die" Datenplatte.

## Tech-Stack

Python 3.12+ (`uv`), PySide6 (Qt), SQLAlchemy 2.x (typisiert), Alembic, SQLite + SQLCipher,
pytest, ruff, PyInstaller.

## Lokaler Start

```bash
uv sync              # Abhängigkeiten inkl. Dev-Tools installieren
uv run klientenverwaltung
```

Beim ersten Start ohne bereits eingerichtete Datenplatte startet automatisch der
Einrichtungsassistent (Laufwerk wählen, Passwort doppelt vergeben, Mindestlänge 12 Zeichen).
Für einen lokalen Test genügt ein beliebiges Laufwerk – im echten Einsatz ist das die
verschlüsselte externe USB-Platte.

Nützliche Flags:

```bash
uv run klientenverwaltung --reset-settings   # Fenstergeometrie/QSettings zurücksetzen
```

**Tests und Linting:**

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

**Migrationen manuell ausführen** (die Anwendung selbst macht das automatisch beim Start; nur
für gezielte `alembic`-Aufrufe während der Entwicklung nötig):

```bash
export KLIENTENVERWALTUNG_DB_PATH=/pfad/zur/klientenverwaltung.db
export KLIENTENVERWALTUNG_DB_PASSWORD=...
uv run alembic revision --autogenerate -m "..."
```

## Build (Windows .exe)

```bash
uv run python scripts/build_exe.py            # Release-Build (ohne Konsole)
uv run python scripts/build_exe.py --debug    # Debug-Build (mit Konsole, für Fehlersuche)
```

Erzeugt `dist/klientenverwaltung.exe` bzw. `dist/klientenverwaltung-debug.exe` als jeweils
eigenständige Single-File-Executables. Ein eingebauter Selbsttest prüft den Build ohne
Anwenderdaten gegen eine Wegwerf-Datenplatte (Migrationen, Services, Sicherung,
Passwortwechsel, Hauptfenster):

```bash
dist/klientenverwaltung-debug.exe --self-test   # Rückgabewert 0 = bestanden
```

Details zu Hidden Imports, Icon-Erzeugung und
PyInstaller-Fallstricken stehen in [`docs/build.md`](docs/build.md) – vor Änderungen an den
`.spec`-Dateien oder einer neuen Alembic-Migration lesen.

## Bewusste Entscheidungen und Trade-offs

- **Kein automatischer Neustart nach einer Wiederherstellung.** Ein aus der `.exe` heraus
  gestarteter Neuprozess findet die von PyInstaller in einen temporären, beim Beenden
  gelöschten Ordner entpackten Qt-Plugins nicht zuverlässig. Nach mehreren Anläufen bewusst
  verworfen zugunsten von: Hinweistext anzeigen, Anwendung beenden, Anwender startet manuell neu.
- **Kein SVG zur Laufzeit.** `PySide6.QtSvg` lässt sich mit PyInstaller nicht zuverlässig
  bündeln. SVG bleibt reines Quellformat für Icons/Splash und wird beim Build
  (`scripts/generate_icons.py`) einmalig in PNG umgewandelt.
- **Keine Terminverwaltung im MVP.** Zukünftige Sitzungen erscheinen als „nächster Termin" in
  der Klientenliste, mehr nicht – eine echte Terminübersicht/Kalender ist ein offener Punkt.
- **Keine Abrechnung im MVP.** Läuft beim Anwender aktuell außerhalb der Anwendung. Das Schema
  ist bewusst so geschnitten, dass sich Standardpreise (`treatment_type`) und eine
  `payment`-Tabelle später per Alembic-Migration nachrüsten lassen, ohne Bestehendes umzubauen.
- **Feste Spaltenauswahl statt konfigurierbarer Tabellen**, Spaltenbreiten werden aber pro
  Fenster gespeichert. Konfigurierbarkeit hätte für eine Ein-Personen-Anwendung ohne wirklichen
  Nutzen nur Komplexität hinzugefügt.
- **Fenster-Titelleisten werden nicht angepasst** – bewusst natives Windows-Systemelement, um
  Betriebssystem-Konsistenz nicht für reine Optik zu opfern.
- **Services liefern Werte, keine ORM-Objekte.** Die Oberfläche bekommt frozen dataclasses
  (`ClientDetails`, `SessionEntry` …) und importiert keine Modelle – ein Architekturtest
  sichert das ab. So hängt nichts an „zufällig“ geladenen Beziehungen, und die Services
  könnten unverändert hinter einer API laufen.
- **Suche in Python statt per SQL `LIKE`.** SQLite faltet nur ASCII – „über“ fand
  „Überlingen“ nicht. Bei der Datenmenge einer Einzelpraxis ist das Filtern im Service
  sofort fertig und bleibt datenbankunabhängig.
- **Migrationen ohne Fremdschlüsselprüfung.** SQLites Batch-Modus baut Tabellen per
  `DROP TABLE` neu auf; mit aktiven Fremdschlüsseln hätte das alle abhängigen Zeilen
  gelöscht. Migrationen laufen deshalb mit `PRAGMA foreign_keys=OFF` und werden danach per
  `foreign_key_check` geprüft.
- **Löschen vs. Archivieren:** Ein Klient löschen entfernt zwingend auch alle zugehörigen
  Sitzungen (keine verwaisten Gesundheitsdaten), deshalb immer mit Sicherheitsabfrage. Für den
  Alltag ist Archivieren vorgesehen, endgültiges Löschen die bewusste Ausnahme.

## Lizenz

Alle Rechte vorbehalten (siehe [`LICENSE`](LICENSE)). Dieses Repository dient als Arbeitsprobe;
Ansehen und Lesen des Codes ist ausdrücklich erwünscht, eine Weiterverwendung ohne Rücksprache
jedoch nicht gestattet – das Projekt entstand ursprünglich als Auftragsarbeit für einen echten
Praxisbetrieb.
