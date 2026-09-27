# TODO

## Screenshots für README

Mit erfundenen Testdaten aufnehmen (z. B. "Anna Muster"), unter `docs/screenshots/` ablegen
und im README verlinken:

- Klientenliste (Hauptfenster, Light-Theme) – Suche, Filter, Spalten "letzte Sitzung"/"nächster Termin"
- Klientenübersicht (reine Ansicht, per Doppelklick/Kontextmenü "Ansicht")
- Berichtsverlauf eines Klienten (zwei Spalten Bericht/Impulse, formatiert)
- Klientendetail-Formular
- Sitzungsfenster eines Klienten
- Bericht-Formularfenster mit Formatierungs-Werkzeugleiste
- Einrichtungsassistent (z. B. Passwortvergabe-Schritt)
- Backup-Verwaltung
- Dieselbe Hauptansicht im Dark-Theme, zum Vergleich mit Light

## Vor der Übergabe

- Testdaten vollständig entfernen, bevor echte Klientendaten eingetragen werden
- Datenplatte verschlüsseln (BitLocker To Go, falls Windows-Edition das erlaubt)
- Anrede als editierbare QComboBox mit Autovervollständigung, Vorschläge aus den bereits vergebenen Werten.

## Fragen an den Anwender

- Welche Spalten sollen in der Klientenliste stehen? Feste Auswahl oder konfigurierbar? Anrede ggf. mit dem Namen zusammenziehen statt eigener Spalte
- Soll eine Klientennummer sichtbar sein? Falls ja: eigenes Feld client_number statt der Datenbank-ID
- Soll das Programm Termine verwalten, oder läuft das über einen Kalender? Aktuell nur zukünftige Sitzungen als 'nächster Termin'
- Welche Anreden werden gebraucht? Wird das Feld überhaupt genutzt?

## Später

- Phase C (Medien) – nächste geplante Phase nach A (Bericht-Formatierung, erledigt)
  und B (Klientenübersicht/Berichtsverlauf, erledigt). Umfang noch nicht im Detail
  festgelegt.
- Export (CSV/PDF), Statistiken wie Sitzungen pro Monat
- Terminübersicht/Kalender (Ausbaustufe nach dem MVP)
  - Schlanke Variante zuerst: Liste aller zukünftigen Sitzungen aller Klienten, nach Datum sortiert, mit Klient, Uhrzeit und Behandlungsart; Klick springt zum Klienten; Umschaltung kommende Termine / Vergangenheit. Nutzt die bestehende session-Tabelle, im Wesentlichen nur Oberfläche.
  - Dabei Statusfeld für Sitzungen einführen (vereinbart, wahrgenommen, abgesagt, nicht erschienen). Ohne Status gilt jeder vergangene Termin automatisch als stattgefunden. Kleine Alembic-Migration mit Standardwert.
  - Monatsansicht (QCalendarWidget) erst danach entscheiden, ggf. reicht die Liste. Bei einem Einzelbetrieb mit wenigen Terminen pro Woche ist eine Liste oft praktischer.

## Ursprünglicher MVP-Umfang (historischer Planungsstand aus CLAUDE.md, inzwischen erreicht/überholt)

- Klientenliste mit Suche (Name, Ort), Filter "Archivierte anzeigen"
- Klient anlegen, bearbeiten, archivieren, endgültig löschen
- Detailansicht eines Klienten mit Sitzungsliste (neueste zuerst)
- Sitzung anlegen, bearbeiten, löschen
- Behandlungsarten pflegen (anlegen, umbenennen, deaktivieren)
- Start-Ablauf: Platte suchen → Passwort → Migrationen anwenden → Hauptfenster

Nicht im MVP: Abrechnung, Termine/Erinnerungen, Export, Statistiken.
