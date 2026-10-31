"""Tandem API: FastAPI backend that also serves the static frontend."""

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import db
from app.model import StationSnapshot, suggest_docks

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# Latest status row per station at or before a given time (defaults to the newest poll).
SNAPSHOT_SQL = """
    SELECT DISTINCT ON (s.station_id)
        s.station_id, s.short_name, s.name, s.lat::float AS lat, s.lon::float AS lon, s.capacity,
        st.fetched_at, st.bikes_available, st.ebikes_available, st.docks_available
    FROM stations s
    JOIN station_status st ON st.station_id = s.station_id
    WHERE st.fetched_at <= COALESCE(%(at)s, (SELECT max(fetched_at) FROM station_status))
    ORDER BY s.station_id, st.fetched_at DESC
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    db.close()


app = FastAPI(title="Tandem", lifespan=lifespan)


class TripRequest(BaseModel):
    rider_name: str = Field(min_length=1, max_length=80)
    rider_age: int = Field(ge=0, le=120)
    destination_station_id: str
    at: datetime | None = None
    min_docks: int = Field(default=5, ge=1, le=50)


@app.get("/api/health")
def health():
    row = db.fetch_one("SELECT count(*) AS stations FROM stations")
    return {"ok": True, "stations": row["stations"]}


@app.get("/api/times")
def times():
    rows = db.fetch_all("SELECT DISTINCT fetched_at FROM station_status ORDER BY fetched_at")
    return [r["fetched_at"] for r in rows]


@app.get("/api/stations")
def stations(at: datetime | None = None):
    return db.fetch_all(SNAPSHOT_SQL, {"at": at})


@app.get("/api/stations/{station_id}/status")
def station_history(station_id: str):
    rows = db.fetch_all(
        """
        SELECT fetched_at, bikes_available, ebikes_available, docks_available
        FROM station_status WHERE station_id = %s ORDER BY fetched_at
        """,
        (station_id,),
    )
    if not rows:
        raise HTTPException(404, "No status rows for that station")
    return rows


@app.post("/api/trips")
def create_trip(req: TripRequest):
    snapshot = [StationSnapshot(**{k: r[k] for k in StationSnapshot.__dataclass_fields__})
                for r in db.fetch_all(SNAPSHOT_SQL, {"at": req.at})]
    destination = next((s for s in snapshot if s.station_id == req.destination_station_id), None)
    if destination is None:
        raise HTTPException(404, "Unknown destination station")

    result = suggest_docks(destination, snapshot, min_docks=req.min_docks)

    with db.pool().connection() as conn, conn.transaction():
        user = conn.execute("SELECT id FROM users WHERE name = %s AND age = %s LIMIT 1",
                            (req.rider_name, req.rider_age)).fetchone()
        if user is None:
            user = conn.execute("INSERT INTO users (name, age) VALUES (%s, %s) RETURNING id",
                                (req.rider_name, req.rider_age)).fetchone()
        trip = conn.execute("INSERT INTO trips (user_id, started_at) VALUES (%s, COALESCE(%s, now())) RETURNING id",
                            (user["id"], req.at)).fetchone()
        for s in result["suggestions"]:
            conn.execute(
                "INSERT INTO suggested_docks (trip_id, station_id, suggested_at) VALUES (%s, %s, now())",
                (trip["id"], s["station_id"]),
            )

    return {"trip_id": trip["id"], "user_id": user["id"], "destination": destination.name, **result}


@app.get("/api/trips")
def recent_trips(limit: int = 10):
    return db.fetch_all(
        """
        SELECT t.id, u.name AS rider, t.started_at,
               COALESCE(array_agg(s.name ORDER BY sd.id) FILTER (WHERE s.name IS NOT NULL), '{}') AS suggested
        FROM trips t
        JOIN users u ON u.id = t.user_id
        LEFT JOIN suggested_docks sd ON sd.trip_id = t.id
        LEFT JOIN stations s ON s.station_id = sd.station_id
        GROUP BY t.id, u.name
        ORDER BY t.id DESC
        LIMIT %s
        """,
        (min(limit, 50),),
    )


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
