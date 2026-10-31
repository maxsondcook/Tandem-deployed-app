"""Create the schema and load the rush-hour sample CSV into Postgres.

Usage:
    DATABASE_URL=postgresql://... python scripts/load_sample.py           # load only if empty
    DATABASE_URL=postgresql://... python scripts/load_sample.py --reset   # drop and recreate everything

Without --reset the schema is left alone if `stations` already exists, so this is
safe to run against the Railway database the team has already populated.
"""

import csv
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = ROOT / "db" / "schema.sql"
CSV_PATH = ROOT / "data" / "citibike_rush_hour_sample.csv"


def main() -> None:
    reset = "--reset" in sys.argv
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        exists = conn.execute("SELECT to_regclass('public.stations') IS NOT NULL").fetchone()[0]
        if reset or not exists:
            conn.execute(SCHEMA.read_text())
            print("Schema created.")
        elif conn.execute("SELECT count(*) FROM station_status").fetchone()[0] > 0:
            print("station_status already has rows; nothing to do (use --reset to reload).")
            return

        with CSV_PATH.open(newline="") as f:
            rows = list(csv.DictReader(f))

        stations = {r["station_id"]: r for r in rows}
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO stations (station_id, short_name, name, lat, lon, capacity, region_id)
                VALUES (%(station_id)s, %(short_name)s, %(name)s, %(lat)s, %(lon)s, %(capacity)s, %(region_id)s)
                ON CONFLICT (station_id) DO NOTHING
                """,
                list(stations.values()),
            )
            cur.executemany(
                """
                INSERT INTO station_status (station_id, fetched_at, reported_at, bikes_available,
                    ebikes_available, bikes_disabled, docks_available, docks_disabled,
                    is_installed, is_renting, is_returning)
                VALUES (%(station_id)s, %(fetched_at)s, %(reported_at)s, %(bikes_available)s,
                    %(ebikes_available)s, %(bikes_disabled)s, %(docks_available)s, %(docks_disabled)s,
                    %(is_installed)s::int::boolean, %(is_renting)s::int::boolean, %(is_returning)s::int::boolean)
                """,
                rows,
            )
        print(f"Loaded {len(stations)} stations and {len(rows)} status rows.")


if __name__ == "__main__":
    main()
