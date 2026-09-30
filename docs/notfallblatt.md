# Notfallblatt – Klientenverwaltung

Zum Ausdrucken und Aufbewahren (nicht auf der Datenplatte, nicht nur auf dem Laptop).
Beschreibt, was in den seltenen Fällen zu tun ist, in denen etwas nicht wie gewohnt läuft.

## Das Wichtigste zuerst

1. **Passwort vergessen = Daten verloren.** Niemand kann das Passwort zurücksetzen, auch
   der Entwickler nicht. Das Passwort deshalb aufschreiben und an einem sicheren Ort
   aufbewahren – getrennt von Laptop und Datenplatte.
2. **Frühere Passwörter aufbewahren.** Nach „Passwort ändern“ bleiben ältere Sicherungen
   mit dem damaligen Passwort verschlüsselt. Wer eine solche Sicherung wiederherstellen
   will, braucht das damalige Passwort.
3. **Der Sicherungsordner gehört auf einen anderen Datenträger** (zweite USB-Platte,
   USB-Stick), nicht auf die Datenplatte selbst. Eine Kopie auf der Datenplatte geht
   zusammen mit ihr verloren. Steht unten rechts im Hauptfenster „(nur auf der
   Datenplatte)“ oder „Keine Sicherungen eingerichtet“, bitte unter
   *Sicherung → Sicherungen verwalten…* einen anderen Ordner wählen.
4. **Mediendateien (Bilder, Audio, Video) sind nicht Teil der Sicherungen** und liegen
   unverschlüsselt im Ordner `medien` auf der Datenplatte. Wer sie sichern will, kopiert
   diesen Ordner von Hand.
5. **Datenplatte nie abziehen, solange das Programm läuft.** Erst das Programm beenden
   (dabei wird in den Sicherungsordner gesichert, wenn sich etwas geändert hat), dann die
   Platte über „Hardware sicher entfernen“ auswerfen.

## Meldungen beim Start

| Meldung | Was tun |
|---|---|
| **Datenplatte nicht gefunden** | Datenplatte anschließen, kurz warten, „Erneut versuchen“. „Neue Datenplatte einrichten…“ nur wählen, wenn wirklich eine neue, leere Platte eingerichtet werden soll (siehe „Datenplatte defekt oder verloren“). |
| **Mehrere Datenplatten gefunden** | Nur die richtige Datenplatte angeschlossen lassen, dann „Erneut versuchen“. |
| **Andere Datenplatte gefunden** | Es ist nicht die Platte angeschlossen, mit der dieser Laptop zuletzt gearbeitet hat. Im Zweifel die gewohnte Platte anschließen und „Erneut versuchen“. |
| **Falsches Passwort** | Noch einmal eingeben; auf Feststelltaste und Tastaturbelegung achten. Es gibt keine Sperre nach Fehlversuchen – und keinen anderen Weg an die Daten. |
| **Programm läuft bereits** | Das Programm ist schon geöffnet: das vorhandene Fenster über die Taskleiste nach vorn holen. |
| Windows: **„Der Computer wurde durch Windows geschützt“** | „Weitere Informationen“ → „Trotzdem ausführen“. Das Programm ist nicht signiert, deshalb fragt Windows beim ersten Start nach. |

## Meldungen während der Arbeit

- **„Datenplatte nicht erreichbar“** – die Platte wurde getrennt. Platte wieder anschließen
  und den letzten Schritt wiederholen; ein geöffnetes Formular dabei offen lassen, der
  eingegebene Text steht noch darin. Hilft das nicht: Programm beenden und neu starten.
- **„Unerwarteter Fehler“** – das Programm beendet sich. Neu starten; gespeicherte Daten
  sind nicht betroffen. Tritt der Fehler wieder auf, die in der Meldung genannte Datei
  `error.log` an den Entwickler schicken. Sie enthält nur technische Angaben, keine
  Klientendaten.

## Etwas versehentlich gelöscht oder überschrieben

1. *Sicherung → Sicherungen verwalten…* öffnen.
2. Die Sicherung mit dem passenden Datum auswählen und „Wiederherstellen“ wählen.
3. Das Programm prüft die Sicherung, sichert vorher den jetzigen Stand und beendet sich
   danach. Bitte von Hand neu starten.

**Achtung:** Eine Wiederherstellung ersetzt den gesamten Datenbestand durch den Stand der
Sicherung. Alles, was danach eingetragen wurde, fehlt anschließend.

**Doch die falsche Sicherung erwischt?** Der Stand von unmittelbar vor der
Wiederherstellung steht in derselben Liste mit der Herkunft „Vor Wiederherstellung“ und
lässt sich genauso wiederherstellen.

## Datenplatte defekt oder verloren

Voraussetzung: Es gibt einen Sicherungsordner auf einem anderen Datenträger.

1. Neue Platte anschließen und das Programm starten.
2. Bei „Datenplatte nicht gefunden“ „Neue Datenplatte einrichten…“ wählen und dem
   Assistenten folgen (Platte wählen, Passwort festlegen, denselben Sicherungsordner wie
   bisher wählen).
3. Danach sofort *Sicherung → Sicherungen verwalten…* öffnen, die jüngste Sicherung
   auswählen und „Wiederherstellen“ wählen.
4. Fragt das Programm nach dem „Passwort der Sicherung“, das Passwort eingeben, das galt,
   als diese Sicherung entstand. Die Daten werden dabei auf das neue Passwort umgestellt.
5. Programm neu starten.

Mediendateien kommen auf diesem Weg nicht zurück (siehe oben, Punkt 4). Bei einer
verlorenen Platte außerdem bedenken: Die Datenbank ist verschlüsselt, die Mediendateien
sind es nur, wenn die ganze Platte verschlüsselt wurde.

## Neuer Laptop

1. Die Programmdatei auf den neuen Laptop kopieren und starten.
2. Datenplatte anschließen, Passwort eingeben – die Daten sind sofort da, sie liegen auf
   der Platte, nicht auf dem Laptop.
3. Den Sicherungsordner unter *Sicherung → Sicherungen verwalten…* neu wählen; diese
   Einstellung liegt auf dem Laptop und zieht nicht mit um.

Auf dem alten Laptop liegen keine Klientendaten, nur Einstellungen (Fenstergrößen,
Sicherungsordner).
