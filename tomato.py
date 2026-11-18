"""Tomaten-Prinzip: Fortschritt, Reifefarbe, Größe und Texte eines Termins.

Reine Rechenlogik ohne Qt, damit sie mit Unit-Tests geprüft werden kann.
Das Zeichnen der Tomate übernimmt ui.paint_tomato().
"""
from __future__ import annotations

import math
from datetime import datetime

# Farbstufen (RGB). Zwischen den Stufen wird stufenlos linear interpoliert.
GREEN = (67, 160, 71)    # unreif, p = 0
ORANGE = (245, 166, 35)  # halb reif, p = 0,5
RED = (211, 47, 47)      # reif, p = 1

MIN_SCALE = 0.70  # Größe bei p = 0
MAX_SCALE = 1.00  # Größe bei p = 1


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _ts(dt: datetime) -> float:
    # Naive Datetimes werden als lokale Zeit gelesen. So stimmt die echte Dauer
    # auch dann, wenn ein Termin über eine Zeitumstellung läuft.
    return dt.timestamp()


def progress(now: datetime, start: datetime, end: datetime) -> float:
    """p = (jetzt − Start) / (Ende − Start), begrenzt auf 0 bis 1."""
    total = _ts(end) - _ts(start)
    if total <= 0:
        return 1.0 if now >= start else 0.0
    return _clamp((_ts(now) - _ts(start)) / total)


def state(now: datetime, start: datetime, end: datetime) -> str:
    """'future', 'running' oder 'past'. Ab dem Endzeitpunkt gilt ein Termin als vorbei."""
    if now < start:
        return "future"
    if now >= end:
        return "past"
    return "running"


def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))  # type: ignore[return-value]


def ripeness_color(p: float) -> tuple[int, int, int]:
    """Grün (0) → Gelb-Orange (0,5) → Rot (1), stufenlos."""
    p = _clamp(p)
    if p <= 0.5:
        return _lerp(GREEN, ORANGE, p / 0.5)
    return _lerp(ORANGE, RED, (p - 0.5) / 0.5)


def tomato_scale(p: float) -> float:
    """Die Tomate wächst mit dem Fortschritt von 70 % auf 100 %."""
    return MIN_SCALE + (MAX_SCALE - MIN_SCALE) * _clamp(p)


def percent_text(p: float) -> str:
    return f"{round(_clamp(p) * 100)} %"


def remaining_text(now: datetime, end: datetime, lang: str = "de") -> str:
    """Restzeit, aufgerundet auf volle Minuten: 'noch 23 Min.' / 'noch 1 Std. 5 Min.'."""
    minutes = max(0, math.ceil((_ts(end) - _ts(now)) / 60))
    h, m = divmod(minutes, 60)
    if lang == "en":
        parts = ([f"{h} h"] if h else []) + ([f"{m} min"] if m or not h else [])
        return " ".join(parts) + " left"
    parts = ([f"{h} Std."] if h else []) + ([f"{m} Min."] if m or not h else [])
    return "noch " + " ".join(parts)
