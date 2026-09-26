# UI-Regeln

Regeln für Fenster, Dialoge, Tabellen und Theming in der PySide6-Oberfläche. Lesen,
bevor ein neues Fenster oder ein neuer Dialog entsteht, ein Stylesheet angefasst wird
oder eine Tabelle mit Spalten hinzukommt.

- Nicht gespeicherte Änderungen abfangen. Wer ein Formular mit Änderungen schließt, bekommt "Möchten Sie die Änderungen speichern?". Sitzungsnotizen, die beim versehentlichen Schließen verschwinden, sind der sicherste Weg, das Vertrauen in das Programm zu verlieren.
- Service-Fehler abfangen und die deutsche Meldung in einer QMessageBox zeigen. Niemals ein Traceback.
- Ausreichend große Schrift und Klickflächen. Der Anwender ist kein Techniker und sitzt eventuell nicht optimal vor dem Bildschirm.
- Keine Geschäftslogik in der Oberfläche. Wenn Claude Code anfängt, im Fenstercode zu validieren, gehört das in die Services.
- Tastatur nicht vergessen: Enter speichert, Escape schließt, Tab läuft in sinnvoller Reihenfolge durch die Felder. Bei Dateneingabe spart das spürbar Zeit.

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
- Gespeicherte Tabellen-Layouts (Spaltenbreiten, Reihenfolge, Sortierung) werden
  verworfen, wenn sich die Spalten seit dem Speichern geändert haben (Anzahl oder
  Überschriften) - sonst adressiert die wiederhergestellte Kopfzeile Spalten, die das
  Modell nicht mehr hat, und headerData() stürzt ab. restore_header_state() vergleicht
  dafür die aktuellen Spaltenüberschriften gegen die mitgespeicherten; bei einer
  Abweichung wird der gespeicherte Zustand aus QSettings gelöscht und False
  zurückgegeben, genau wie beim allerersten Start. headerData() bleibt trotzdem in
  jedem Tabellenmodell defensiv (Index außerhalb des Bereichs -> None), als zweite,
  unabhängige Absicherung.
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
- Stylesheets, die QMenu oder QSplitter anfassen, setzen deren native Darstellung
  außer Kraft: Menüeinträge verlieren ihren Innenabstand, Splitter-Griffe ihre Breite
  und werden dadurch unbedienbar. Für QMenu::item immer padding setzen, für
  QSplitter::handle immer eine Breite/Höhe (ca. 6 px), eine sichtbare Farbe und
  einen Hover-Zustand.
- Bei gestylten QComboBox immer auch ::drop-down und ::down-arrow gestalten, sonst
  fehlt der Aufklapp-Pfeil. Gleiches gilt für QWizard: der Button-Bereich wird separat
  eingefärbt und bleibt sonst im nativen Hell.
- Ein- und ausblendbare Fehler- oder Hinweistexte bekommen dauerhaft reservierten
  Platz im Layout, damit beim Erscheinen nichts springt.
- Jedes Fenster und jeder Dialog hat einen gesetzten deutschen Fenstertitel.
- Fenstergrößen immer gegen QScreen.availableGeometry() prüfen, nicht gegen die volle
  Bildschirmgröße, und beim Öffnen hineinschieben, falls das Fenster herausragt. Das
  gilt auch für gespeicherte Werte aus QSettings. Alle Fenster müssen auf 1366x768
  vollständig nutzbar sein; bei zu wenig Platz den Inhalt in eine QScrollArea legen.
- Sitzungen liegen in einem eigenen Fenster, nicht im Klientenfenster. Das Klientenfenster
  zeigt nur Stammdaten, Anliegen und Notizen; der Zugang zu den Sitzungen erfolgt über
  einen Button unten mit Anzahl und Datum der letzten Sitzung.
- Bei gestylten QSpinBox, QDoubleSpinBox und QDateTimeEdit immer up-button UND
  down-button vollständig definieren (Breite, Höhe, subcontrol-origin/-position),
  sonst wird eine der beiden Klickflächen winzig, obwohl der Pfeil normal aussieht.
