"""Zuordnung von Terminen auf das Wochenraster (Mo–Fr, 9–20 Uhr)."""
from datetime import date, datetime

from schedule import Event, place_events, query_range, week_start_for

WEEK = date(2026, 11, 16)  # Montag
DAYS = [0, 1, 2, 3, 4]


def place(*events):
    return place_events(list(events), WEEK, DAYS, 9, 20)


def ev(subject, start, end, **kw):
    return Event(subject, start, end, **kw)


def test_simple_event_position_minute_exact():
    timed, _ = place(ev("A", datetime(2026, 11, 17, 10, 15), datetime(2026, 11, 17, 12, 45)))
    (p,) = timed
    assert (p.day, p.top, p.bottom) == (1, 75, 225)
    assert not p.cut_top and not p.cut_bottom


def test_grid_is_exactly_9_to_20():
    timed, _ = place(ev("Ganzer Tag", datetime(2026, 11, 16, 9), datetime(2026, 11, 16, 20)))
    assert (timed[0].top, timed[0].bottom) == (0, 660)


def test_0830_to_0930_is_cut_at_top():
    timed, _ = place(ev("Früh", datetime(2026, 11, 16, 8, 30), datetime(2026, 11, 16, 9, 30)))
    (p,) = timed
    assert (p.top, p.bottom, p.cut_top, p.cut_bottom) == (0, 30, True, False)


def test_event_completely_outside_is_marked():
    timed, _ = place(
        ev("Sehr früh", datetime(2026, 11, 16, 7), datetime(2026, 11, 16, 8)),
        ev("Abends", datetime(2026, 11, 16, 20), datetime(2026, 11, 16, 21)),
    )
    assert sorted(p.outside for p in timed) == ["after", "before"]


def test_event_over_midnight_is_split():
    timed, _ = place(ev("Nacht", datetime(2026, 11, 18, 18), datetime(2026, 11, 19, 10)))
    wed, thu = timed
    assert (wed.day, wed.top, wed.bottom, wed.cut_bottom) == (2, 540, 660, True)
    assert (thu.day, thu.top, thu.bottom, thu.cut_top) == (3, 0, 60, True)


def test_recurring_occurrences_each_land_on_their_day():
    occ = [ev("Jour fixe", datetime(2026, 11, d, 11), datetime(2026, 11, d, 12),
              entry_id="SERIE", is_recurring=True) for d in (16, 18, 20)]
    timed, _ = place(*occ)
    assert [(p.day, p.top) for p in timed] == [(0, 120), (2, 120), (4, 120)]


def test_moved_occurrence_exception_uses_its_own_time():
    # Outlook liefert bei IncludeRecurrences die Ausnahme mit der verschobenen Zeit.
    timed, _ = place(ev("Jour fixe", datetime(2026, 11, 18, 14), datetime(2026, 11, 18, 15), is_recurring=True))
    assert (timed[0].day, timed[0].top) == (2, 300)


def test_all_day_event_goes_to_strip():
    timed, all_day = place(ev("Konferenz", datetime(2026, 11, 17), datetime(2026, 11, 19), all_day=True))
    assert timed == []
    (a,) = all_day
    assert (a.first, a.last) == (1, 2)


def test_all_day_events_stack_in_rows():
    _, all_day = place(
        ev("A", datetime(2026, 11, 16), datetime(2026, 11, 18), all_day=True),
        ev("B", datetime(2026, 11, 17), datetime(2026, 11, 18), all_day=True),
        ev("C", datetime(2026, 11, 19), datetime(2026, 11, 20), all_day=True),
    )
    rows = {a.event.subject: a.row for a in all_day}
    assert rows == {"A": 0, "B": 1, "C": 0}


def test_overlapping_events_side_by_side():
    timed, _ = place(
        ev("A", datetime(2026, 11, 16, 10), datetime(2026, 11, 16, 12)),
        ev("B", datetime(2026, 11, 16, 11), datetime(2026, 11, 16, 13)),
        ev("C", datetime(2026, 11, 16, 14), datetime(2026, 11, 16, 15)),
    )
    by = {p.event.subject: p for p in timed}
    assert (by["A"].lane, by["A"].lanes) == (0, 2)
    assert (by["B"].lane, by["B"].lanes) == (1, 2)
    assert (by["C"].lane, by["C"].lanes) == (0, 1)


def test_dst_week_wall_clock_positions():
    # Woche mit Zeitumstellung (So 25.10.2026): Montag danach, 10–11 Uhr steht auf 60–120.
    week = week_start_for(date(2026, 10, 26))
    assert week == date(2026, 10, 26)
    timed, _ = place_events([ev("A", datetime(2026, 10, 26, 10), datetime(2026, 10, 26, 11))], week, DAYS, 9, 20)
    assert (timed[0].top, timed[0].bottom) == (60, 120)


def test_dst_sunday_belongs_to_previous_week_or_next():
    assert week_start_for(date(2026, 3, 29), weekend_shows_next_week=False) == date(2026, 3, 23)
    assert week_start_for(date(2026, 3, 29)) == date(2026, 3, 30)


def test_query_range_covers_monday_to_friday_night():
    start, end = query_range(WEEK, DAYS)
    assert start == datetime(2026, 11, 16)
    assert end == datetime(2026, 11, 21)


def test_weekend_events_ignored_for_mo_fr():
    timed, _ = place(ev("Samstag", datetime(2026, 11, 21, 10), datetime(2026, 11, 21, 11)))
    assert timed == []
