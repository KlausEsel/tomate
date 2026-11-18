"""Laden, Prüfen und Speichern von config.json."""
from __future__ import annotations

import json
import logging
import os
import sys
from copy import deepcopy
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULTS: dict = {
    "start_hour": 9,
    "end_hour": 20,
    "days": [0, 1, 2, 3, 4],          # 0 = Montag … 6 = Sonntag
    "refresh_seconds": 60,
    "retry_seconds": 30,
    "calendar": "",                    # leer = Hauptkalender, sonst Name eines Unterkalenders
    "theme": "system",                 # "system" | "light" | "dark"
    "hide_private": True,
    "language": "de",                  # "de" | "en"
    "opacity": 92,                     # 0–100 %
    "geometry": None,                  # [x, y, Breite, Höhe]; None = automatisch
    "desktop_mode": "bottom",          # "bottom" (HWND_BOTTOM) | "workerw" (experimentell)
    "start_outlook_if_closed": False,
    "weekend_shows_next_week": True,
    "click_opens_in_outlook": True,
    "outlook_date_format": "",         # leer = Format der Windows-Ländereinstellung
}


def app_dir() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller-.exe
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def config_path() -> Path:
    """Im Entwicklungsordner liegt config.json neben main.py.
    Als .exe wird sie unter %APPDATA%\\Tomatenplan gespeichert (Programmordner ist oft schreibgeschützt)."""
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("APPDATA", Path.home())) / "Tomatenplan"
        base.mkdir(parents=True, exist_ok=True)
        return base / "config.json"
    return app_dir() / "config.json"


def validate(cfg: dict) -> dict:
    """Ergänzt fehlende Werte und korrigiert ungültige auf die Standardwerte."""
    out = deepcopy(DEFAULTS)
    out.update({k: v for k, v in cfg.items() if k in DEFAULTS})

    def as_int(key: str, lo: int, hi: int) -> None:
        try:
            out[key] = max(lo, min(hi, int(out[key])))
        except (TypeError, ValueError):
            out[key] = DEFAULTS[key]

    as_int("start_hour", 0, 23)
    as_int("end_hour", 1, 24)
    if out["end_hour"] <= out["start_hour"]:
        out["start_hour"], out["end_hour"] = DEFAULTS["start_hour"], DEFAULTS["end_hour"]
    as_int("refresh_seconds", 15, 3600)
    as_int("retry_seconds", 5, 600)
    as_int("opacity", 10, 100)  # unter 10 % wäre das Fenster praktisch unsichtbar

    try:
        days = sorted({int(d) for d in out["days"] if 0 <= int(d) <= 6})
    except (TypeError, ValueError):
        days = []
    out["days"] = days or list(DEFAULTS["days"])

    if out["theme"] not in ("system", "light", "dark"):
        out["theme"] = "system"
    if out["language"] not in ("de", "en"):
        out["language"] = "de"
    if out["desktop_mode"] not in ("bottom", "workerw"):
        out["desktop_mode"] = "bottom"
    geo = out["geometry"]
    if not (isinstance(geo, list) and len(geo) == 4 and all(isinstance(v, int) for v in geo)):
        out["geometry"] = None
    for key in ("hide_private", "start_outlook_if_closed", "weekend_shows_next_week", "click_opens_in_outlook"):
        out[key] = bool(out[key])
    out["calendar"] = str(out["calendar"] or "")
    out["outlook_date_format"] = str(out["outlook_date_format"] or "")
    return out


def load(path: Path | None = None) -> dict:
    path = path or config_path()
    data: dict = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("config.json nicht lesbar, Standardwerte werden benutzt: %s", exc)
    return validate(data)


def save(cfg: dict, path: Path | None = None) -> None:
    path = path or config_path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(validate(cfg), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
