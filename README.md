# Tandem — deployed app skeleton

One Railway service runs a FastAPI backend that also serves the frontend, connected to the
team's Railway Postgres (the `stations` / `station_status` / `users` / `trips` / `suggested_docks` schema).

The placeholder flow shows every layer working:

1. **User input** — rider name, destination station, arrival time (form in `static/`).
2. **Backend model logic** — `app/model.py` applies the group model v1 regression: it predicts
   each station's free docks 30 minutes ahead from docks now, the change over the last 15 minutes,
   capacity, and minutes after 4 PM. If the destination is predicted to have fewer than 3 (the
   form's "Min. docks on arrival"), it suggests the nearest stations predicted to have room.
3. **Database access** — `app/main.py` reads station snapshots from `station_status`, and writes
   `users`, `trips`, and `suggested_docks` rows. "Recent trips" reads them back.

The chart reproduces the Tableau "Citi Bike Evening Rush (Oct. 14th)" view from the API.

```
app/main.py         API routes + serves static/
app/model.py        dock predictions + suggestions (applies app/model_v1.json)
app/model_v1.json   fitted coefficients, written by model/dock_regression.py
model/              the group regression, copied from alexxu2027/tandem-data
tests/              pytest tests for app/model.py
app/db.py           Postgres pool (reads DATABASE_URL)
static/             index.html, app.js, style.css (no build step)
db/schema.sql       schema
scripts/load_sample.py  creates schema + loads data/citibike_rush_hour_sample.csv if empty
```

## API

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | DB connectivity check (Railway healthcheck) |
| GET | `/api/times` | Distinct poll times in `station_status` |
| GET | `/api/stations?at=<iso time>` | Each station's latest status at or before `at`, with `predicted_docks` |
| GET | `/api/model` | The model's coefficients and what it was trained on |
| GET | `/api/stations/{station_id}/status` | Full time series for one station |
| POST | `/api/trips` | Run the model, save user/trip/suggested docks, return suggestions |
| GET | `/api/trips` | Last 10 trips with their suggested docks |

Interactive docs: `/docs`.

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # paste the Postgres *public* URL from Railway → Postgres → Connect
export $(cat .env) && uvicorn app.main:app --reload
```

Open http://localhost:8000.

## Retrain the model

The app only needs `app/model_v1.json`. To refit it on newer data, clone
[tandem-data](https://github.com/alexxu2027/tandem-data) next to this repo (or set `TANDEM_DATA`)
and run, from this repo's root:

```bash
uv run model/dock_regression.py   # about 2 minutes; rewrites app/model_v1.json and model/output/
```

## Tests

```bash
pip install pytest && python -m pytest
```

## Deploy on Railway

1. Push this folder to the team GitHub repo.
2. In the Railway project that already has the Postgres service: **+ New → GitHub Repo** → pick the repo.
3. On the new service → **Variables** → add `DATABASE_URL` = `${{Postgres.DATABASE_URL}}`
   (a reference variable, so it uses Railway's private network).
4. **Settings → Networking → Generate Domain**. That URL is the submission link.
5. `railway.json` sets the start command (`uvicorn ... --port $PORT`) and the `/api/health` healthcheck.

If `station_status` is empty in Railway, load the sample once from your laptop:

```bash
DATABASE_URL='<public Postgres URL>' python scripts/load_sample.py
```

It leaves an already-populated database alone; `--reset` drops and reloads everything.
