# TODO

## Vor der Übergabe

- Backup-Konzept umsetzen (Punkt 8 aus der Planung), muss vor dem Produktivstart stehen
- Testdaten vollständig entfernen, bevor echte Klientendaten eingetragen werden
- Datenplatte verschlüsseln (BitLocker To Go, falls Windows-Edition das erlaubt)
- Anrede als editierbare QComboBox mit Autovervollständigung, Vorschläge aus den bereits vergebenen Werten.

## Fragen an den Anwender

- Welche Spalten sollen in der Klientenliste stehen? Feste Auswahl oder konfigurierbar? Anrede ggf. mit dem Namen zusammenziehen statt eigener Spalte
- Soll eine Klientennummer sichtbar sein? Falls ja: eigenes Feld client_number statt der Datenbank-ID
- Soll das Programm Termine verwalten, oder läuft das über einen Kalender? Aktuell nur zukünftige Sitzungen als 'nächster Termin'
- Kommen mehrere Behandlungsarten in einer Sitzung vor?
- Wird die Abrechnung künftig im Programm gebraucht?
- Welche Anreden werden gebraucht? Wird das Feld überhaupt genutzt?

## Später

- Mindestbreite pro Spalte in der Klientenliste, damit Spalten nicht auf null gezogen werden können
- Spaltenbreiten und Sortierung beim Beenden speichern
- Export (CSV/PDF), Statistiken wie Sitzungen pro Monat
- Terminübersicht/Kalender (Ausbaustufe nach dem MVP)
  - Schlanke Variante zuerst: Liste aller zukünftigen Sitzungen aller Klienten, nach Datum sortiert, mit Klient, Uhrzeit und Behandlungsart; Klick springt zum Klienten; Umschaltung kommende Termine / Vergangenheit. Nutzt die bestehende session-Tabelle, im Wesentlichen nur Oberfläche.
  - Dabei Statusfeld für Sitzungen einführen (vereinbart, wahrgenommen, abgesagt, nicht erschienen). Ohne Status gilt jeder vergangene Termin automatisch als stattgefunden. Kleine Alembic-Migration mit Standardwert.
  - Monatsansicht (QCalendarWidget) erst danach entscheiden, ggf. reicht die Liste. Bei einem Einzelbetrieb mit wenigen Terminen pro Woche ist eine Liste oft praktischer.
