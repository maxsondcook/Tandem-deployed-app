"""Placeholder dock-suggestion logic.

This is the "model" slot in the skeleton. Today it is a simple rule:
if the rider's destination will have fewer than `min_docks` open docks,
suggest the nearest stations that do. Swap `suggest_docks` for the real
analysis (forecasting, incentives, etc.) without touching the API or UI.
"""

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt


@dataclass
class StationSnapshot:
    station_id: str
    name: str
    lat: float
    lon: float
    capacity: int
    docks_available: int
    bikes_available: int


def walking_meters(a: StationSnapshot, b: StationSnapshot) -> float:
    """Straight-line (haversine) distance; stands in for real walking distance."""
    lat1, lon1, lat2, lon2 = map(radians, (a.lat, a.lon, b.lat, b.lon))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000 * asin(sqrt(h))


def suggest_docks(
    destination: StationSnapshot,
    others: list[StationSnapshot],
    min_docks: int = 5,
    limit: int = 3,
) -> dict:
    if destination.docks_available >= min_docks:
        return {
            "reroute": False,
            "reason": f"{destination.name} has {destination.docks_available} open docks.",
            "suggestions": [],
        }

    candidates = [s for s in others if s.station_id != destination.station_id and s.docks_available >= min_docks]
    ranked = sorted(candidates, key=lambda s: walking_meters(destination, s))[:limit]
    return {
        "reroute": True,
        "reason": f"{destination.name} has only {destination.docks_available} open docks.",
        "suggestions": [
            {
                "station_id": s.station_id,
                "name": s.name,
                "docks_available": s.docks_available,
                "distance_m": round(walking_meters(destination, s)),
            }
            for s in ranked
        ],
    }
