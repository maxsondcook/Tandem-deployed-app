"""Tandem dock suggestions, driven by the group model v1 regression.

The model (model/dock_regression.py, trained on the tandem-data recordings)
predicts how many docks a station will have free 30 minutes from now, from:
docks free now, the change over the last 15 minutes, capacity, and minutes
after 4 PM New York time. Its fitted numbers live in app/model_v1.json, so the
app applies them directly without pandas or statsmodels.

If the destination is predicted to have fewer than `min_docks` free docks when
the rider arrives, suggest the nearest stations predicted to have room.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from zoneinfo import ZoneInfo

COEFFICIENTS = json.loads((Path(__file__).resolve().parent / "model_v1.json").read_text())
MINUTES_AHEAD: int = COEFFICIENTS["minutes_ahead"]
LOW_DOCKS: int = COEFFICIENTS["low_docks"]
RUSH_START, RUSH_END = COEFFICIENTS["rush_hours_new_york"]
NEW_YORK = ZoneInfo("America/New_York")


@dataclass
class StationSnapshot:
    station_id: str
    name: str
    lat: float
    lon: float
    capacity: int
    docks_available: int
    bikes_available: int
    docks_15_ago: int | None = None


def walking_meters(a: StationSnapshot, b: StationSnapshot) -> float:
    """Straight-line (haversine) distance; stands in for real walking distance."""
    lat1, lon1, lat2, lon2 = map(radians, (a.lat, a.lon, b.lat, b.lon))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * asin(sqrt(h))


def minutes_after_4pm(at: datetime) -> int:
    """Minutes after 4 PM New York time, clamped to the 4-7 PM window the model was trained on."""
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    local = at.astimezone(NEW_YORK)
    minutes = (local.hour - RUSH_START) * 60 + local.minute
    return max(0, min(minutes, (RUSH_END - RUSH_START) * 60))


def predict_docks(docks_now: int, docks_change_15: int, capacity: int, minutes: int) -> float:
    """Model v1: free docks MINUTES_AHEAD minutes from now, kept between 0 and capacity."""
    c = COEFFICIENTS["coefficients"]
    raw = (
        COEFFICIENTS["intercept"]
        + c["docks_now"] * docks_now
        + c["docks_change_15"] * docks_change_15
        + c["capacity"] * capacity
        + c["minutes_after_4pm"] * minutes
    )
    return max(0.0, min(raw, float(capacity)))


def predict_station(s: StationSnapshot, at: datetime) -> float:
    change = 0 if s.docks_15_ago is None else s.docks_available - s.docks_15_ago
    return predict_docks(s.docks_available, change, s.capacity, minutes_after_4pm(at))


def suggest_docks(
    destination: StationSnapshot,
    others: list[StationSnapshot],
    at: datetime,
    min_docks: int = LOW_DOCKS,
    limit: int = 3,
) -> dict:
    predicted = predict_station(destination, at)
    shown = round(predicted, 1)
    if predicted >= min_docks:
        return {
            "reroute": False,
            "predicted_docks": shown,
            "reason": (f"{destination.name} has {destination.docks_available} open docks now; "
                       f"Tandem predicts {shown} when you arrive in {MINUTES_AHEAD} minutes."),
            "suggestions": [],
        }

    scored = [(s, predict_station(s, at)) for s in others if s.station_id != destination.station_id]
    candidates = [(s, p) for s, p in scored if p >= min_docks]
    ranked = sorted(candidates, key=lambda sp: walking_meters(destination, sp[0]))[:limit]
    return {
        "reroute": True,
        "predicted_docks": shown,
        "reason": (f"{destination.name} has {destination.docks_available} open docks now, but Tandem "
                   f"predicts only {shown} when you arrive in {MINUTES_AHEAD} minutes."),
        "suggestions": [
            {
                "station_id": s.station_id,
                "name": s.name,
                "docks_available": s.docks_available,
                "predicted_docks": round(p, 1),
                "distance_m": round(walking_meters(destination, s)),
            }
            for s, p in ranked
        ],
    }
