"""Fortschritt, Reifefarbe, Größe und Texte der Tomate."""
import os
import time
from datetime import datetime

import pytest

import tomato
from tomato import GREEN, ORANGE, RED


def dt(h, m=0, day=18):
    return datetime(2026, 11, day, h, m)


# Abnahmekriterium: 10:00–11:00 → um 10:30 halb reif (gelb-orange), um 11:00 rot.
def test_acceptance_half_ripe_at_1030():
    p = tomato.progress(dt(10, 30), dt(10), dt(11))
    assert p == pytest.approx(0.5)
    assert tomato.ripeness_color(p) == ORANGE
    assert tomato.state(dt(10, 30), dt(10), dt(11)) == "running"


def test_acceptance_red_at_1100():
    p = tomato.progress(dt(11), dt(10), dt(11))
    assert p == 1.0
    assert tomato.ripeness_color(p) == RED
    assert tomato.state(dt(11), dt(10), dt(11)) == "past"


def test_progress_is_clamped():
    assert tomato.progress(dt(9), dt(10), dt(11)) == 0.0
    assert tomato.progress(dt(12), dt(10), dt(11)) == 1.0


def test_zero_length_event():
    assert tomato.progress(dt(9), dt(10), dt(10)) == 0.0
    assert tomato.progress(dt(10), dt(10), dt(10)) == 1.0


def test_color_endpoints_and_continuity():
    assert tomato.ripeness_color(0) == GREEN
    assert tomato.ripeness_color(1) == RED
    assert tomato.ripeness_color(-3) == GREEN
    assert tomato.ripeness_color(7) == RED
    # stufenlos: kleine Schritte ergeben kleine Farbsprünge
    prev = tomato.ripeness_color(0)
    for i in range(1, 101):
        cur = tomato.ripeness_color(i / 100)
        assert max(abs(a - b) for a, b in zip(prev, cur)) <= 6
        prev = cur


def test_color_quarter_is_between_green_and_orange():
    r, g, b = tomato.ripeness_color(0.25)
    assert GREEN[0] < r < ORANGE[0]


def test_scale_grows_from_70_to_100_percent():
    assert tomato.tomato_scale(0) == pytest.approx(0.7)
    assert tomato.tomato_scale(0.5) == pytest.approx(0.85)
    assert tomato.tomato_scale(1) == pytest.approx(1.0)


def test_remaining_text_german():
    assert tomato.remaining_text(dt(10, 37), dt(11)) == "noch 23 Min."
    assert tomato.remaining_text(dt(9, 55), dt(11)) == "noch 1 Std. 5 Min."
    assert tomato.remaining_text(dt(9), dt(11)) == "noch 2 Std."
    # angebrochene Minuten werden aufgerundet
    assert tomato.remaining_text(datetime(2026, 11, 18, 10, 59, 30), dt(11)) == "noch 1 Min."


def test_remaining_text_english():
    assert tomato.remaining_text(dt(10, 37), dt(11), "en") == "23 min left"


def test_percent_text():
    assert tomato.percent_text(0.5) == "50 %"


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="Zeitzone lässt sich hier nicht umstellen")
def test_progress_across_dst_uses_real_duration():
    """29.03.2026: Uhr springt von 2:00 auf 3:00. Termin 1:00–4:00 dauert real 2 Stunden.
    Um 3:00 Uhr ist real 1 Stunde vergangen → p = 0,5 (Wandzeit allein ergäbe 2/3)."""
    old = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Berlin"
    time.tzset()
    try:
        p = tomato.progress(datetime(2026, 3, 29, 3), datetime(2026, 3, 29, 1), datetime(2026, 3, 29, 4))
        assert p == pytest.approx(0.5)
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()
