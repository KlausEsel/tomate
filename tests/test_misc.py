"""Konfiguration und Outlook-Filter (ohne Outlook prüfbar)."""
from datetime import datetime

import config
from outlook_reader import restrict_filter


def test_config_defaults_and_validation():
    cfg = config.validate({"start_hour": 20, "end_hour": 9, "days": [9, "x"], "opacity": 300, "theme": "bunt"})
    assert (cfg["start_hour"], cfg["end_hour"]) == (9, 20)
    assert cfg["days"] == [0, 1, 2, 3, 4]
    assert cfg["opacity"] == 100
    assert cfg["theme"] == "system"


def test_config_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    config.save({"start_hour": 8, "end_hour": 18}, path)
    assert config.load(path)["start_hour"] == 8


def test_restrict_filter_german_format():
    f = restrict_filter(datetime(2026, 11, 16), datetime(2026, 11, 21), "%d.%m.%Y %H:%M")
    assert f == "[Start] < '21.11.2026 00:00' AND [End] > '16.11.2026 00:00'"
