# Tomatenplan

Wochenstundenplan aus Microsoft Outlook als ruhiges Raster auf dem Windows-Desktop.
Jeder Termin ist eine Tomate: grün, solange er bevorsteht, gelb-orange zur Hälfte, rot und reif am Ende.

> **Nur klassisches Outlook.** Das neue Outlook für Windows („New Outlook“) hat keine COM-Schnittstelle.
> Tomatenplan funktioniert nur mit dem klassischen Outlook. Für das neue Outlook wäre ein Zugriff über
> Microsoft Graph oder einen ICS-Link nötig.

## Architektur

| Modul | Aufgabe |
|---|---|
| `outlook_reader.py` | eigener Thread mit `CoInitialize`; liest die Woche per COM (`Sort`, `IncludeRecurrences`, `Restrict`) |
| `schedule.py` | reine Logik: Woche bestimmen, Termine minutengenau aufs Raster legen, Überschneidungen anordnen |
| `tomato.py` | reine Logik: Fortschritt p, Reifefarbe, Größe, Restzeit-Text |
| `ui.py` | Raster und Tomaten in einem `paintEvent` (kein Flackern), Tooltips, Einstellungsdialog |
| `desktop_win.py` | HWND_BOTTOM / WS_EX_TOOLWINDOW / WorkerW, Autostart über die Registry |
| `config.py`, `config.json` | Einstellungen laden, prüfen, speichern |
| `main.py` | startet alles, Tray-Menü, verbindet Worker und Oberfläche über Qt-Signale |
| `demo.py` | Beispieldaten ohne Outlook (`--demo`) |

Datenfluss: Worker-Thread → Outlook (COM) → Liste von `Event` → Qt-Signal → `ScheduleWidget.set_events`
→ `schedule.place_events` → Zeichnen. Ein Timer zeichnet alle 15 s neu, damit Tomaten reifen und die Zeitlinie wandert.

## Installation

Voraussetzung: Windows 10/11, klassisches Outlook, Python 3.11 oder neuer (python.org, Haken bei „Add to PATH“).

```
cd C:\Pfad\zu\tomatenplan
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Start

```
pythonw main.py          # ohne Konsolenfenster, liest Outlook
python main.py --demo    # Beispieldaten, ohne Outlook
```

Das Fenster erscheint rechts oben auf dem Hauptbildschirm, hinter allen anderen Fenstern.
Bedienung über das Tomaten-Symbol im Infobereich der Taskleiste:

- **Anzeigen/Verbergen**, **Jetzt aktualisieren**
- **Position und Größe anpassen**: Fenster ziehen, unten rechts an der Ecke die Größe ändern, danach den Haken wieder entfernen. Wird in `config.json` gespeichert.
- **Einstellungen …**: Stunden, Wochentage, Intervall, Kalender, Hell/Dunkel, Privattermine, Sprache, Deckkraft, Desktop-Modus
- **Autostart**: trägt Tomatenplan unter `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` ein bzw. aus
- **Beenden**

Ein Klick auf einen Termin öffnet ihn in Outlook. Der Tooltip zeigt den Fortschritt in Prozent.

## Autostart ohne Tray-Menü

Alternativ eine Verknüpfung zu `pythonw.exe "C:\Pfad\zu\tomatenplan\main.py"` (bzw. zur `Tomatenplan.exe`)
in den Ordner `shell:startup` legen (Win+R → `shell:startup`).

## Als .exe verpacken (PyInstaller)

```
pyinstaller --noconsole --onefile --name Tomatenplan main.py
```

Die Datei liegt danach in `dist\Tomatenplan.exe`. Die .exe speichert ihre Einstellungen unter
`%APPDATA%\Tomatenplan\config.json`; beim ersten Start werden Standardwerte benutzt.

## Tests

```
python -m pytest tests
```

Geprüft werden Fortschritt und Farbe (inkl. Abnahmekriterium 10:00–11:00), Restzeit-Texte,
Rasterzuordnung (Termin über Mitternacht, 8:30–9:30, Serientermin und verschobene Ausnahme,
Ganztagstermin, Überschneidungen, Zeitumstellung) sowie Konfiguration und Outlook-Filter.
Die Tests laufen ohne Outlook und ohne Windows.

## Konfiguration (`config.json`)

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `start_hour`, `end_hour` | 9, 20 | sichtbare Stunden |
| `days` | [0,1,2,3,4] | Wochentage, 0 = Montag |
| `refresh_seconds` | 60 | Abfrage-Intervall |
| `retry_seconds` | 30 | neuer Versuch, wenn Outlook nicht erreichbar ist |
| `calendar` | "" | leer = Hauptkalender, sonst Name eines Unterordners des Kalenders |
| `theme` | "system" | "system", "light", "dark" |
| `hide_private` | true | private Termine nur als „Belegt“ |
| `language` | "de" | "de", "en" |
| `opacity` | 92 | Deckkraft in Prozent |
| `geometry` | null | [x, y, Breite, Höhe] |
| `desktop_mode` | "bottom" | "bottom" (hinter allen Fenstern) oder "workerw" (Desktop-Ebene, experimentell) |
| `start_outlook_if_closed` | false | true = Outlook bei Bedarf selbst starten |
| `weekend_shows_next_week` | true | Sa/So schon die kommende Woche zeigen |
| `click_opens_in_outlook` | true | Klick öffnet den Termin |
| `outlook_date_format` | "" | nur bei Problemen setzen, z. B. "%d.%m.%Y %H:%M" |

## Datenschutz

Termindaten bleiben auf dem Rechner und nur im Arbeitsspeicher. Es wird nichts gespeichert oder übertragen.
Die Protokolldatei `tomatenplan.log` enthält nur technische Fehler, keine Termininhalte.
Private Termine erscheinen standardmäßig nur als „Belegt“; Betreff und Ort werden dann gar nicht erst übernommen.

## Bekannte Grenzen

- **Win+D / „Desktop anzeigen“** blendet Fenster im Modus "bottom" aus. Der Modus "workerw" vermeidet das,
  ist aber von Windows-Versionen abhängig (ab Windows 11 24H2 geänderte Desktop-Struktur). Bei Problemen zurück auf "bottom".
- **Datumsformat für Restrict()**: Outlook erwartet das Format der Windows-Ländereinstellung. Tomatenplan
  ermittelt es automatisch; falls Termine fehlen, `outlook_date_format` setzen.
- **Termin öffnen bei verschobenen Serien-Ausnahmen** öffnet ggf. die ganze Serie statt des Einzeltermins.
