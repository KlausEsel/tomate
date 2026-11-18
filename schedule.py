"""Reine Planungslogik ohne Qt und ohne Outlook.

- Event: ein Termin (naive Datetimes = lokale Wandzeit, so wie Outlook sie liefert)
- week_start_for / query_range: welche Woche wird angezeigt und abgefragt
- place_events: bildet Termine minutengenau auf das Wochenraster ab,
  schneidet an den Rastergrenzen ab und ordnet Überschneidungen nebeneinander an.

Alles hier ist ohne Windows testbar (siehe tests/test_schedule.py).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

# Mindesthöhe eines Blocks in Minuten. Wird auch für die Überschneidungs-
# Erkennung benutzt, damit sehr kurze Termine optisch nicht übereinanderliegen.
MIN_VISUAL_MINUTES = 20


@dataclass(frozen=True)
class Event:
    subject: str
    start: datetime
    end: datetime
    location: str = ""
    all_day: bool = False
    private: bool = False
    entry_id: str = ""
    is_recurring: bool = False


@dataclass
class Placement:
    """Ein Termin-Abschnitt an einem Tag im Raster (Minuten ab Rasterbeginn)."""
    event: Event
    day: int                # Spaltenindex (0 = erste sichtbare Spalte)
    top: float
    bottom: float
    cut_top: bool = False   # beginnt vor dem Raster (oder am Vortag)
    cut_bottom: bool = False  # endet nach dem Raster (oder am Folgetag)
    outside: str = ""       # "" | "before" | "after": liegt ganz außerhalb
    lane: int = 0
    lanes: int = 1


@dataclass
class AllDayPlacement:
    event: Event
    first: int  # erste Spalte
    last: int   # letzte Spalte
    row: int = 0


def week_start_for(today: date, weekend_shows_next_week: bool = True) -> date:
    """Montag der anzuzeigenden Woche. Am Wochenende optional schon die nächste Woche."""
    monday = today - timedelta(days=today.weekday())
    if weekend_shows_next_week and today.weekday() >= 5:
        monday += timedelta(days=7)
    return monday


def query_range(week_start: date, days: list[int]) -> tuple[datetime, datetime]:
    """Abfragezeitraum: erster sichtbarer Tag 00:00 bis Tag nach dem letzten sichtbaren Tag 00:00."""
    start = datetime.combine(week_start + timedelta(days=min(days)), time.min)
    end = datetime.combine(week_start + timedelta(days=max(days) + 1), time.min)
    return start, end


def _minutes(delta: timedelta) -> float:
    return delta.total_seconds() / 60.0


def place_events(
    events: list[Event],
    week_start: date,
    days: list[int],
    start_hour: int,
    end_hour: int,
) -> tuple[list[Placement], list[AllDayPlacement]]:
    """Ordnet Termine dem Raster zu.

    Mehrtägige Termine (z. B. über Mitternacht) werden pro Tag in Abschnitte geteilt.
    Gerechnet wird in Wandzeit; an Tagen mit Zeitumstellung stimmt die Position
    daher mit der Uhr überein.
    """
    span = (end_hour - start_hour) * 60
    timed: list[Placement] = []
    all_day: list[AllDayPlacement] = []

    for ev in events:
        if ev.end < ev.start:
            continue  # defekter Datensatz
        covered: list[int] = []
        for col, weekday in enumerate(days):
            day_start = datetime.combine(week_start + timedelta(days=weekday), time.min)
            day_end = day_start + timedelta(days=1)
            if ev.all_day:
                if ev.start < day_end and ev.end > day_start:
                    covered.append(col)
                continue

            seg_s, seg_e = max(ev.start, day_start), min(ev.end, day_end)
            zero_length_today = ev.start == ev.end and day_start <= ev.start < day_end
            if seg_s >= seg_e and not zero_length_today:
                continue

            win_s = day_start + timedelta(hours=start_hour)
            win_e = day_start + timedelta(hours=end_hour)
            if seg_e < win_s or (seg_e == win_s and seg_s < win_s):
                timed.append(Placement(ev, col, 0, 0, outside="before"))
            elif seg_s > win_e or (seg_s == win_e and seg_e > win_e):
                timed.append(Placement(ev, col, span, span, outside="after"))
            else:
                timed.append(Placement(
                    ev, col,
                    top=_minutes(max(seg_s, win_s) - win_s),
                    bottom=_minutes(min(seg_e, win_e) - win_s),
                    cut_top=seg_s < win_s,
                    cut_bottom=seg_e > win_e,
                ))
        if covered:
            all_day.append(AllDayPlacement(ev, covered[0], covered[-1]))

    for col in range(len(days)):
        _assign_lanes([p for p in timed if p.day == col and not p.outside])
    _assign_rows(all_day)
    timed.sort(key=lambda p: (p.day, p.top, p.lane))
    return timed, all_day


def _assign_lanes(items: list[Placement]) -> None:
    """Überschneidende Termine bekommen Spuren nebeneinander.

    Eine Gruppe (Cluster) sind alle Termine, die sich direkt oder über andere
    überschneiden; alle in der Gruppe teilen sich dieselbe Spaltenzahl.
    """
    items.sort(key=lambda p: (p.top, -p.bottom))
    cluster: list[Placement] = []
    lane_ends: list[float] = []
    cluster_end = float("-inf")

    def close() -> None:
        for q in cluster:
            q.lanes = len(lane_ends)

    for p in items:
        bottom = max(p.bottom, p.top + MIN_VISUAL_MINUTES)
        if cluster and p.top >= cluster_end:
            close()
            cluster, lane_ends = [], []
            cluster_end = float("-inf")
        for i, end in enumerate(lane_ends):
            if end <= p.top:
                p.lane, lane_ends[i] = i, bottom
                break
        else:
            p.lane = len(lane_ends)
            lane_ends.append(bottom)
        cluster.append(p)
        cluster_end = max(cluster_end, bottom)
    if cluster:
        close()


def _assign_rows(items: list[AllDayPlacement]) -> None:
    items.sort(key=lambda a: (a.first, -(a.last - a.first)))
    row_ends: list[int] = []
    for a in items:
        for i, last in enumerate(row_ends):
            if last < a.first:
                a.row, row_ends[i] = i, a.last
                break
        else:
            a.row = len(row_ends)
            row_ends.append(a.last)
