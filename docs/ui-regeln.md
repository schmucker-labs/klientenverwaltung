# UI-Regeln

Regeln für Fenster, Dialoge, Tabellen und Theming in der PySide6-Oberfläche. Lesen,
bevor ein neues Fenster oder ein neuer Dialog entsteht, ein Stylesheet angefasst wird
oder eine Tabelle mit Spalten hinzukommt.

- Nicht gespeicherte Änderungen abfangen. Wer ein Formular mit Änderungen schließt, bekommt "Möchten Sie die Änderungen speichern?". Sitzungsnotizen, die beim versehentlichen Schließen verschwinden, sind der sicherste Weg, das Vertrauen in das Programm zu verlieren.
- Service-Fehler abfangen und die deutsche Meldung in einer QMessageBox zeigen. Niemals ein Traceback.
- Ausreichend große Schrift und Klickflächen. Der Anwender ist kein Techniker und sitzt eventuell nicht optimal vor dem Bildschirm.
- Keine Geschäftslogik in der Oberfläche. Wenn Claude Code anfängt, im Fenstercode zu validieren, gehört das in die Services.
- Tastatur nicht vergessen: Enter speichert, Escape schließt, Tab läuft in sinnvoller Reihenfolge durch die Felder. Bei Dateneingabe spart das spürbar Zeit. Ausnahme: in mehrzeiligen Texteditoren (QTextEdit) erzeugt Enter immer einen Zeilenumbruch; Speichern läuft dort über Strg+S (ohne zu schließen) bzw. Strg+Enter/Strg+Return (speichert und schließt).

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
- Rich-Text-Felder (QTextEdit mit Formatierung, z. B. das Berichtsfenster): nie eine
  eigene Textfarbe, immer die Textfarbe des aktiven Themes - dafür wird gar keine
  Vordergrundfarbe im Zeichenformat gesetzt, dann folgt die Anzeige automatisch der
  Theme-Stylesheet-Farbe, auch bei einem Theme-Wechsel im laufenden Betrieb. Beim
  Einfügen (insertFromMimeData überschreiben) und zusätzlich vor dem Speichern werden
  Vordergrundfarbe, Hintergrundfarbe, Schriftart und Schriftgröße aus jedem
  Zeichenformat entfernt (zwei unabhängige Stellen, nicht nur eine); erhalten bleiben
  nur fett, kursiv, unterstrichen, die Überschriftsebene und Listen. An denselben zwei
  Stellen werden Bilder entfernt (aus Word eingefügte Bilder sind nur Verweise auf
  Temp-Dateien auf dem Laptop - Gesundheitsdaten außerhalb der verschlüsselten
  Datenbank), Links zu normalem Text und Tabellen zu einem Absatz je Zelle
  (`strip_disallowed_formatting` in `ui/report_dialog.py`). Überschriften bekommen
  ihre Größe über eine relative Größenanpassung der Überschriftsebene, nie über eine
  gespeicherte Punktgröße - sonst würde das Entfernen der Schriftgröße auch die
  Überschrift wieder einebnen. Leerer Inhalt (auch ein rein aus Leerzeichen
  bestehendes Rich-Text-Dokument) wird beim Speichern als NULL/None abgelegt, nie als
  leerer String.
- Werkzeugleisten-Buttons neben einem Textfeld (z. B. Fett/Kursiv/Unterstrichen im
  Berichtsfenster) bekommen `Qt.FocusPolicy.NoFocus`, damit ein Klick den Fokus im
  Textfeld belässt und sofort weitergetippt werden kann - Maus-Klick und Tastenkürzel
  funktionieren trotzdem unverändert. Sie sind so hoch wie das Steuerelement daneben
  (z. B. die Überschriften-Auswahl) und quadratisch - dafür `ToolbarButton` aus
  `ui/buttons.py` verwenden: Die Eigenschaft `toolbarButton` nimmt ihnen im Theme
  Innenabstand, Mindesthöhe und Mindestbreite eines Dialog-Buttons, die Größe kommt
  aus `sizeHint()` (Höhe des Nachbarelements, Größenrichtlinie `Fixed`) statt aus
  `setFixedSize()` - ein festes Minimum setzt diese Theme-Regel bei jedem Anwenden des
  Styles wieder zurück. Eine Auswahlbox in derselben Leiste, die zum
  Aufklappen selbst Fokus braucht (z. B. die Überschriften-Auswahl), gibt den Fokus
  nach einer echten Auswahl (Signal `activated`, nicht `currentIndexChanged` - das
  feuert auch bei einer rein programmatischen Aktualisierung) an das zuletzt aktive
  Textfeld zurück.
- Alle Buttons sind gleich groß: 32 px hoch (wie die Eingabefelder) und mindestens
  96 px breit, damit kurze Beschriftungen wie "OK" keine Stummel ergeben. Die Größe
  kommt ausschließlich aus dem Theme (`QPushButton` in `ui/theme.py`), nie aus
  `setFixedWidth()`/`setFixedHeight()` im Fenstercode - so gilt sie auch für
  QDialogButtonBox und QMessageBox.
- Button-Zeilen werden in jedem Fenster gleich aufgebaut, über `ui/buttons.py` statt
  über ein eigenes QHBoxLayout:
  - `action_row()` - die Zeile unter einer Tabelle. Links (`independent`), was ohne
    ausgewählte Zeile funktioniert, Anlegen zuerst; rechts (`on_selection`), was auf
    die ausgewählte Zeile wirkt, in der Reihenfolge Öffnen/Ansehen, Bearbeiten,
    Archivieren/Deaktivieren, "Löschen" immer zuletzt.
  - `window_row()` - die Buttons des Fensters selbst, rechtsbündig in der letzten
    Zeile: "Schließen" bzw. "Speichern" und "Schließen"/"Abbrechen". In einem Fenster
    ohne "Speichern" ist "Schließen" der Standard-Button (`setDefault(True)`).
  - Beide liefern ein `ButtonRow`-Widget, kein bloßes Layout: Die Mindestbreite aus
    dem Theme gilt für Qt als gesamte Mindestbreite eines Buttons - ein Layout würde
    längere Beschriftungen darauf zusammendrücken und abschneiden, bevor das Fenster
    breiter wird. `ButtonRow` ist deshalb nie schmaler, als alle Buttons brauchen.
- Ein Button, der etwas Neues anlegt, ist ein `CreateButton` (Plus vor dem Text, in
  der Textfarbe des aktiven Themes, färbt sich bei einem Theme-Wechsel selbst um) und
  nennt, was er anlegt: "Neuer Klient", "Neue Sitzung", "Neue Behandlungsart" - nicht
  nur "Neu". In Klientenliste und Sitzungsfenster gibt es dazu Strg+N (steht im
  Tooltip) und denselben Eintrag im Kontextmenü der Tabelle, auch auf der leeren
  Fläche unter den Zeilen.
- Umschalt-Buttons (checkable QPushButton) zeigen ihren aktiven Zustand ausschließlich
  über `:checked` mit der Akzentfarbe des Themes und kontrastreicher Schrift, deutlich
  vom inaktiven Zustand unterscheidbar in Light UND Dark - dazu `:checked:hover`,
  `:checked:pressed` und `:checked:disabled` ebenso definieren wie die unmarkierten
  Zustände (siehe Regel oben zu vollständig ersetztem nativem Stil). Wird der Zustand
  programmatisch aktualisiert (z. B. nach einer Cursor-Bewegung), dabei die Signale
  jedes betroffenen Widgets blockieren, damit das Anzeigen selbst nicht wieder eine
  Formatierung auslöst oder den Fokus verschiebt.
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
- Bei gestylten QScrollBar immer Breite/Höhe, ::handle mit Mindestgröße, ::add-page/
  ::sub-page (sonst gepunktetes Schachbrettmuster in der Rinne) und ::add-line/::sub-line
  definieren. Fokus und Standard-Button müssen unterscheidbar bleiben: Standard-Button
  mit getönter Fläche, Fokus mit 2 px Rahmen (Innenabstand um 1 px verringert, damit
  nichts springt). Farben, die Code direkt setzt (z. B. ForegroundRole eines
  Tabellenmodells), kommen aus `theme.current_palette()`, nie aus einer festen Palette.
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
  einen Button unten mit Anzahl und Datum der letzten Sitzung. Es ist zweispaltig:
  links das Formular (scrollt bei wenig Höhe), darunter der Sitzungen-Button; rechts
  nur Anliegen und Notizen. "Speichern" steht unten neben "Schließen".
- Zwischen Eingabefeldern und dem Scrollbalken einer QScrollArea bleibt derselbe Abstand
  wie der Außenrand des Dialogs (`layout.contentsMargins()`, aus dem Style gelesen, nicht
  als feste Zahl): als rechter Rand des gescrollten Inhalts. Reichen die Felder ohne
  Scrollbalken bis an den Dialogrand (Berichtsfenster), gibt es diesen Rand nur, solange
  der Scrollbalken sichtbar ist (`rangeChanged` des Scrollbalkens) - sonst stünden sie
  gegenüber Überschrift und Buttons eingerückt.
- Abstände in einem Dialog: nur zwei Maße, beide aus dem Style statt als feste Zahl -
  zwischen den Blöcken (Überschrift, Werkzeugleiste, beschriftetes Feld, Button-Zeile) der
  Außenrand des Dialogs, innerhalb eines Blocks (Beschriftung und ihr Feld, die Elemente
  einer Werkzeugleiste) der Standardabstand des Layouts. Eingebettete Layouts (z. B. eine
  Werkzeugleiste als eigenes QWidget) bekommen Rand 0, damit alles an derselben linken
  Kante beginnt.
- Trennlinie zwischen gleichartigen Abschnitten (z. B. den Sitzungen im Berichtsverlauf):
  ein 1 px hoher QFrame mit der Eigenschaft `divider`, den das Theme in der Linienfarbe
  (`lines`, wie die Feldrahmen) einfärbt - keine Karten/Rahmen um die Abschnitte, die
  Textfelder darin sind schon gerahmt. Ober- und unterhalb der doppelte Layout-Rand. Der
  Leerraum am Ende einer solchen Liste bekommt `addStretch(1)`, sonst teilen sich die
  Abschnitte die überschüssige Höhe und rücken in einem hohen Fenster auseinander.
- Überschriften in Anzeige-Fenstern haben zwei Ränge: die Überschrift eines Eintrags
  (Name in der Klientenübersicht, "Sitzung vom …" im Berichtsverlauf) fett und 2 pt
  größer; Beschriftungen darunter ("Bericht", "Impulse") in normaler Schrift und
  Sekundärfarbe über die Eigenschaft `secondary` (Theme: `QLabel[secondary="true"]`).
- Der Berichtsverlauf hat über der Liste eine feste Zeile mit zwei Auswahlboxen:
  "Behandlungsart" (Standard "Alle Behandlungsarten"; nur Arten, zu denen dieser Klient
  Berichte hat) und "Sortieren nach Datum" (Standard absteigend = neueste zuerst). Die
  Sortierung wird in QSettings gemerkt, die Behandlungsart nicht.
- Tabellen werden über einen Klick auf die Spaltenüberschrift sortiert
  (`setSortingEnabled(True)`, `sort()` im Tabellenmodell, nach jedem Neuladen erneut
  anwenden, `sortIndicatorChanged` speichert den Kopfzeilen-Zustand). `sort()` muss die
  persistenten Indizes mitverschieben (`changePersistentIndexList`, siehe
  `SessionTableModel.sort`), damit die Auswahl auf demselben Eintrag bleibt.
  `setSortingEnabled(True)` erst nach `restore_header_state()` aufrufen: ein Zustand,
  der gespeichert wurde, bevor die Tabelle sortierbar war, blendet den Sortierpfeil
  sonst wieder aus.
- Eine Tabelle behält ihre Markierung über jedes Neuladen hinweg: Wer eine Sitzung
  markiert, "Medien" öffnet und wieder schließt, kann direkt "Bearbeiten" klicken, ohne
  die Zeile erneut anzuklicken. Jedes Tabellenmodell lädt mit einem Model-Reset neu, und
  der verwirft die Auswahl der Ansicht - die `_reload…()`-Methode merkt sich deshalb
  vorher den markierten Eintrag und markiert ihn danach wieder
  (`select_rows_where()` in `ui/table_selection.py`). Immer über die ID des Eintrags,
  nie über die Zeilennummer: Nach dem Sortieren steht in derselben Zeile ein anderer
  Eintrag, und "Löschen" darf nie auf einen anderen zeigen als den angeklickten. Ein
  gelöschter Eintrag hinterlässt keine Markierung; ein neu angelegter (Klient, Sitzung,
  Behandlungsart, Mediendatei) wird markiert, damit er zu finden ist.
- Ein Fenster, das hinter einem geöffneten Dialog sichtbar bleibt, zeigt nie veraltete
  Daten: Es aktualisiert sich, sobald im Dialog gespeichert wird, nicht erst, wenn er
  geschlossen wird ("Speichern" im Klientenfenster und Strg+S im Berichtsfenster lassen
  das Fenster offen). Das gilt für jede Ebene dahinter, bis zur Klientenliste im
  Hauptfenster. Dafür sendet der Dialog ein Signal (`saved` in einem Formular wie
  `ReportDialog` oder `TreatmentTypeEditDialog`, `data_changed` in einem Fenster, das
  selbst weitere Dialoge öffnet: `ClientDetailDialog`, `ClientSessionsDialog`,
  `ClientOverviewDialog`, `TreatmentTypeManagementDialog`), das der Aufrufer vor
  `exec()` mit seiner eigenen `_reload()`-Methode verbindet und - wenn hinter ihm
  wieder ein Fenster liegt - an sein eigenes `data_changed` weiterreicht. Kein
  programmweites Signal: Dialoge bleiben nach dem Schließen als Kinder ihres
  Elternfensters bestehen und würden sonst weiter mitladen.
- Bei gestylten QSpinBox, QDoubleSpinBox und QDateTimeEdit immer up-button UND
  down-button vollständig definieren (Breite, Höhe, subcontrol-origin/-position),
  sonst wird eine der beiden Klickflächen winzig, obwohl der Pfeil normal aussieht.
- In reinen Anzeige-Fenstern (keine Eingabefelder, z. B. die Klientenübersicht) werden
  leere Felder komplett weggelassen, samt Beschriftung - ein Abschnitt ohne Inhalt
  verschwindet vollständig, es bleibt keine Lücke stehen. Doppelklick in der
  Klientenliste öffnet diese Ansicht, nicht mehr direkt den Bearbeiten-Dialog.
- Ein Signal eines auf einen QThread verschobenen Worker-Objekts nie mit einer
  Lambda oder freien Funktion verbinden, nur mit einer gebundenen Methode eines
  QObjects (z. B. `self._on_x`) - nur eine gebundene Methode trägt einen Empfänger-
  Kontext, den Qts AutoConnection erkennt und dadurch korrekt in den GUI-Thread
  einreiht. Eine Lambda hat keinen solchen Kontext und wird stattdessen direkt im
  Thread des Signals aufgerufen - dort dürfen dann keine Widgets, GUI-Thread-Timer
  oder QMessageBox angefasst werden (Auftrag C1: genau das führte anfangs dazu,
  dass ein erfolgreicher Medien-Import die Anwendung beim Anzeigen der
  Erfolgsmeldung eingefroren hat). Umgekehrt: Ein Slot, der auf dem Worker-Thread
  laufen soll (z. B. ein reiner `threading.Event.set()`-Aufruf zum Abbrechen),
  braucht ausdrücklich `Qt.ConnectionType.DirectConnection` - AutoConnection würde
  ihn sonst in die Ereignisschleife des Worker-Threads einreihen, die während
  eines laufenden Vorgangs gar nicht läuft und den Slot erst nach dessen Ende
  zustellen würde.
