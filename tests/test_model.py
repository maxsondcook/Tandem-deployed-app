from datetime import datetime, timezone

import pytest

from app.model import COEFFICIENTS, StationSnapshot, minutes_after_4pm, predict_docks, suggest_docks


def station(sid, docks, docks_15_ago=None, capacity=30, lat=40.75, lon=-73.99, name=None):
    return StationSnapshot(
        station_id=sid, name=name or sid, lat=lat, lon=lon, capacity=capacity,
        docks_available=docks, bikes_available=capacity - docks, docks_15_ago=docks_15_ago,
    )


def test_prediction_matches_the_trained_regression():
    c = COEFFICIENTS["coefficients"]
    expected = (COEFFICIENTS["intercept"] + c["docks_now"] * 3 + c["docks_change_15"] * -3
                + c["capacity"] * 31 + c["minutes_after_4pm"] * 75)
    assert predict_docks(3, -3, 31, 75) == pytest.approx(expected)
    # The team's script prints 2.4 for this exact example.
    assert round(predict_docks(3, -3, 31, 75), 1) == 2.4


def test_prediction_stays_between_zero_and_capacity():
    assert predict_docks(0, -10, 20, 170) == 0
    assert predict_docks(20, 15, 20, 0) == 20


@pytest.mark.parametrize(("utc", "expected"), [
    ("2026-10-14T20:00:00+00:00", 0),     # 4:00 PM New York (EDT)
    ("2026-10-14T21:15:00+00:00", 75),    # 5:15 PM
    ("2026-11-19T22:30:00+00:00", 90),    # 5:30 PM (EST, after the clocks changed)
    ("2026-10-14T14:00:00+00:00", 0),     # 10 AM: outside rush, clamped to the window
    ("2026-10-14T23:30:00+00:00", 180),   # 7:30 PM: clamped to the window
])
def test_minutes_after_4pm_uses_new_york_time(utc, expected):
    assert minutes_after_4pm(datetime.fromisoformat(utc)) == expected


def test_minutes_after_4pm_treats_naive_times_as_utc():
    assert minutes_after_4pm(datetime(2026, 10, 14, 21, 15)) == 75


AT = datetime(2026, 10, 14, 21, 15, tzinfo=timezone.utc)  # 5:15 PM New York


def test_no_reroute_when_destination_is_predicted_to_have_room():
    dest = station("dest", docks=15, docks_15_ago=15)
    result = suggest_docks(dest, [dest], AT)
    assert result["reroute"] is False
    assert result["predicted_docks"] >= 3
    assert result["suggestions"] == []


def test_reroute_uses_the_prediction_not_docks_right_now():
    # 4 open docks now (enough for a "right now" rule of 3) but filling fast.
    dest = station("dest", docks=4, docks_15_ago=10)
    near = station("near", docks=12, docks_15_ago=12, lat=40.751)
    far = station("far", docks=12, docks_15_ago=12, lat=40.80)
    filling = station("filling", docks=4, docks_15_ago=10, lat=40.7505)
    result = suggest_docks(dest, [dest, near, far, filling], AT)

    assert result["reroute"] is True
    assert result["predicted_docks"] < 3
    names = [s["name"] for s in result["suggestions"]]
    assert names == ["near", "far"]  # nearest first; "filling" is predicted full too
    assert all(s["predicted_docks"] >= 3 for s in result["suggestions"])


def test_missing_history_counts_as_no_change():
    with_history = station("a", docks=8, docks_15_ago=8)
    without = station("a", docks=8, docks_15_ago=None)
    assert suggest_docks(with_history, [], AT)["predicted_docks"] == suggest_docks(without, [], AT)["predicted_docks"]


def test_min_docks_threshold_is_respected():
    dest = station("dest", docks=8, docks_15_ago=8)
    assert suggest_docks(dest, [dest], AT, min_docks=3)["reroute"] is False
    assert suggest_docks(dest, [dest], AT, min_docks=20)["reroute"] is True
