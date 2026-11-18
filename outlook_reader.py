"""Termine aus dem klassischen Outlook lesen (COM über pywin32).

WICHTIG: Das neue Outlook für Windows ("New Outlook") hat KEINE COM-Schnittstelle.
Diese Lösung funktioniert nur mit dem klassischen Outlook (Outlook 2016/2019/2021/
Microsoft 365 klassisch). Für das neue Outlook wäre Microsoft Graph oder ein ICS-Link nötig.

Der gesamte COM-Zugriff läuft im Thread OutlookWorker. Die Oberfläche wartet nie auf Outlook.
Termindaten bleiben im Arbeitsspeicher; es wird nichts gespeichert oder übertragen.
"""
from __future__ import annotations

import locale
import logging
import queue
import threading
import time as _time
from datetime import date, datetime
from typing import Callable

from schedule import Event, query_range, week_start_for

log = logging.getLogger(__name__)

OL_FOLDER_CALENDAR = 9
OL_APPOINTMENT_CLASS = 26
OL_PRIVATE = 2
MAX_ITEMS_PER_WEEK = 2000  # Schutz gegen Endlosschleifen bei IncludeRecurrences


class OutlookUnavailable(Exception):
    """Outlook läuft nicht, ist blockiert oder der Kalender fehlt."""


def to_naive(value) -> datetime:
    """pywin32 liefert Outlook-Zeiten mit einer irreführenden UTC-Zeitzone,
    obwohl es lokale Wandzeit ist. Daher nur die Felder übernehmen."""
    return datetime(value.year, value.month, value.day, value.hour, value.minute, value.second)


def outlook_date_format(override: str = "") -> str:
    """Restrict() erwartet Datum/Uhrzeit im Format der Windows-Ländereinstellung."""
    if override:
        return override
    try:
        locale.setlocale(locale.LC_TIME, "")
    except locale.Error:
        pass
    return "%x %H:%M"


def restrict_filter(start: datetime, end: datetime, fmt: str) -> str:
    """Alle Termine, die den Zeitraum [start, end) berühren."""
    return f"[Start] < '{end.strftime(fmt)}' AND [End] > '{start.strftime(fmt)}'"


class OutlookReader:
    """Kapselt die COM-Objekte. Nur im Worker-Thread benutzen."""

    def __init__(self) -> None:
        self._ns = None

    def reset(self) -> None:
        self._ns = None

    def _namespace(self, start_if_closed: bool):
        if self._ns is not None:
            return self._ns
        import pywintypes
        import win32com.client

        try:
            if start_if_closed:
                app = win32com.client.Dispatch("Outlook.Application")
            else:
                app = win32com.client.GetActiveObject("Outlook.Application")
        except pywintypes.com_error as exc:
            raise OutlookUnavailable("not_running") from exc
        self._ns = app.GetNamespace("MAPI")
        return self._ns

    def _calendar(self, ns, name: str):
        folder = ns.GetDefaultFolder(OL_FOLDER_CALENDAR)
        if not name:
            return folder
        for i in range(1, folder.Folders.Count + 1):
            sub = folder.Folders.Item(i)
            if sub.Name == name:
                return sub
        raise OutlookUnavailable("calendar_missing")

    def read_events(self, start: datetime, end: datetime, cfg: dict) -> list[Event]:
        ns = self._namespace(cfg["start_outlook_if_closed"])
        items = self._calendar(ns, cfg["calendar"]).Items
        # Reihenfolge ist wichtig: erst sortieren, dann Serien einschließen, dann filtern.
        items.Sort("[Start]")
        items.IncludeRecurrences = True
        restricted = items.Restrict(restrict_filter(start, end, outlook_date_format(cfg["outlook_date_format"])))

        busy = "Belegt" if cfg["language"] == "de" else "Busy"
        events: list[Event] = []
        item = restricted.GetFirst()
        count = 0
        # Bei IncludeRecurrences ist Count unzuverlässig, daher GetFirst/GetNext.
        while item is not None and count < MAX_ITEMS_PER_WEEK:
            count += 1
            if getattr(item, "Class", None) == OL_APPOINTMENT_CLASS:
                s, e = to_naive(item.Start), to_naive(item.End)
                if s >= end:
                    break  # sortiert: alles Weitere liegt später
                if e > start or (s == e and s >= start):  # zweite Prüfung, falls Restrict ungenau filtert
                    private = item.Sensitivity == OL_PRIVATE
                    hide = private and cfg["hide_private"]
                    events.append(Event(
                        subject=busy if hide else (item.Subject or ""),
                        start=s,
                        end=e,
                        location="" if hide else (item.Location or ""),
                        all_day=bool(item.AllDayEvent),
                        private=private,
                        entry_id=item.EntryID,
                        is_recurring=bool(item.IsRecurring),
                    ))
            item = restricted.GetNext()
        return events

    def open_event(self, ev: Event, cfg: dict) -> None:
        """Öffnet den Termin in Outlook. Bei Serien das einzelne Vorkommen, sonst die Serie."""
        ns = self._namespace(cfg["start_outlook_if_closed"])
        item = ns.GetItemFromID(ev.entry_id)
        if ev.is_recurring:
            try:
                item = item.GetRecurrencePattern().GetOccurrence(ev.start)
            except Exception:  # verschobene Ausnahme: dann die Serie öffnen
                log.info("Einzelvorkommen nicht gefunden, öffne Serie.")
        item.Display()


class OutlookWorker(threading.Thread):
    """Eigener Thread mit eigener COM-Initialisierung.

    Aktualisiert sofort, danach alle refresh_seconds; nach einem Fehler alle retry_seconds.
    Ergebnisse gehen über Callbacks (in main.py an Qt-Signale gebunden) an die Oberfläche.
    """

    def __init__(
        self,
        get_config: Callable[[], dict],
        on_events: Callable[[date, list], None],
        on_status: Callable[[str, bool], None],
    ) -> None:
        super().__init__(name="OutlookWorker", daemon=True)
        self._get_config = get_config
        self._on_events = on_events
        self._on_status = on_status
        self._q: queue.Queue = queue.Queue()

    # --- Aufrufe aus dem UI-Thread -------------------------------------------
    def request_refresh(self) -> None:
        self._q.put(("refresh", None))

    def request_open(self, ev: Event) -> None:
        self._q.put(("open", ev))

    def stop(self) -> None:
        self._q.put(("stop", None))

    # --- Thread ----------------------------------------------------------------
    def run(self) -> None:
        import pythoncom

        pythoncom.CoInitialize()
        reader = OutlookReader()
        try:
            cmd, arg = "refresh", None
            next_refresh = 0.0
            while cmd != "stop":
                if cmd == "refresh":
                    next_refresh = _time.monotonic() + self._refresh(reader)
                elif cmd == "open":
                    self._open(reader, arg)
                try:
                    cmd, arg = self._q.get(timeout=max(0.0, next_refresh - _time.monotonic()))
                except queue.Empty:
                    cmd, arg = "refresh", None
        finally:
            reader.reset()
            pythoncom.CoUninitialize()

    def _refresh(self, reader: OutlookReader) -> float:
        cfg = self._get_config()
        week = week_start_for(date.today(), cfg["weekend_shows_next_week"])
        start, end = query_range(week, cfg["days"])
        try:
            events = reader.read_events(start, end, cfg)
        except OutlookUnavailable as exc:
            reader.reset()
            self._on_status(str(exc), False)
            return cfg["retry_seconds"]
        except Exception:  # COM-Fehler, Outlook beschäftigt, Profil gesperrt …
            log.exception("Outlook-Abfrage fehlgeschlagen")
            reader.reset()
            self._on_status("unreachable", False)
            return cfg["retry_seconds"]
        self._on_events(week, events)
        self._on_status("ok", True)
        return cfg["refresh_seconds"]

    def _open(self, reader: OutlookReader, ev: Event) -> None:
        try:
            reader.open_event(ev, self._get_config())
        except Exception:
            log.exception("Termin konnte nicht geöffnet werden")
            reader.reset()
            self._on_status("open_failed", False)
