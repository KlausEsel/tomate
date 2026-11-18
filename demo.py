"""Demo-Datenquelle ohne Outlook (Start mit: python main.py --demo).

Erzeugt Beispieltermine rund um die aktuelle Uhrzeit, damit man Raster und Tomaten
auch ohne Outlook oder auf einem anderen Rechner ansehen kann.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Callable

from schedule import Event, week_start_for


def demo_events(now: datetime, week: date) -> list[Event]:
    def at(day: int, h: int, m: int = 0) -> datetime:
        return datetime.combine(week + timedelta(days=day), time(h, m))

    today = min(now.weekday(), 4)
    run_start = now.replace(second=0, microsecond=0) - timedelta(minutes=37)
    return [
        Event("Teamrunde", at(0, 9, 30), at(0, 10, 30), "Besprechungsraum"),
        Event("Frühtermin", at(0, 8, 30), at(0, 9, 30), "Telefon"),
        Event("Lesung vorbereiten", at(1, 14), at(1, 16, 30), "Büro"),
        Event("Telefonat", at(1, 15), at(1, 15, 30)),
        Event("Jour fixe", at(2, 11), at(2, 12), entry_id="x", is_recurring=True),
        Event("Jour fixe", at(3, 11), at(3, 12), entry_id="x", is_recurring=True),
        Event("Nachtfahrt", at(3, 22), at(4, 9, 45), "Bahn"),
        Event("Vortrag", at(4, 18), at(4, 21), "Essen"),
        Event("Konferenz", at(1, 0), at(3, 0), all_day=True),
        Event("Belegt", at(2, 16), at(2, 17), private=True),
        Event("Laufender Termin", run_start, run_start + timedelta(minutes=60), "Kita"),
        Event("Später heute", at(today, 17), at(today, 18)),
    ]


class DemoSource:
    """Gleiche Schnittstelle wie OutlookWorker."""

    def __init__(self, on_events: Callable, on_status: Callable, now_fn: Callable[[], datetime] = datetime.now):
        self._on_events, self._on_status, self._now = on_events, on_status, now_fn

    def start(self) -> None:
        self.request_refresh()

    def request_refresh(self) -> None:
        now = self._now()
        week = week_start_for(now.date())
        self._on_events(week, demo_events(now, week))
        self._on_status("ok", True)

    def request_open(self, ev) -> None:
        print("Demo: würde in Outlook öffnen:", ev.subject)

    def stop(self) -> None:
        pass

    def join(self, timeout=None) -> None:
        pass
