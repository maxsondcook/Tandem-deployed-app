-- Tandem station feed, plus empty placeholders for riders, trips, and reroutes.
-- Station attributes are current values only. Each poll is its own status row.

DROP TABLE IF EXISTS suggested_docks;
DROP TABLE IF EXISTS trips;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS station_status;
DROP TABLE IF EXISTS stations;

CREATE TABLE stations (
    station_id text PRIMARY KEY,
    short_name text NOT NULL UNIQUE,
    name text NOT NULL,
    lat numeric(12, 10) NOT NULL CHECK (lat BETWEEN -90 AND 90),
    lon numeric(12, 10) NOT NULL CHECK (lon BETWEEN -180 AND 180),
    capacity integer NOT NULL CHECK (capacity >= 0),
    region_id integer NOT NULL
);

CREATE TABLE station_status (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    station_id text NOT NULL REFERENCES stations (station_id),
    fetched_at timestamptz NOT NULL,
    reported_at timestamptz NOT NULL,
    bikes_available integer NOT NULL CHECK (bikes_available >= 0),
    ebikes_available integer NOT NULL CHECK (ebikes_available >= 0),
    bikes_disabled integer NOT NULL CHECK (bikes_disabled >= 0),
    docks_available integer NOT NULL CHECK (docks_available >= 0),
    docks_disabled integer NOT NULL CHECK (docks_disabled >= 0),
    is_installed boolean NOT NULL,
    is_renting boolean NOT NULL,
    is_returning boolean NOT NULL,
    CHECK (ebikes_available <= bikes_available)
);

CREATE INDEX station_status_station_fetched_at_idx
    ON station_status (station_id, fetched_at);

CREATE TABLE users (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL,
    age integer NOT NULL CHECK (age >= 0)
);

CREATE TABLE trips (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id integer NOT NULL REFERENCES users (id),
    started_at timestamptz
);

CREATE TABLE suggested_docks (
    id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trip_id integer NOT NULL REFERENCES trips (id),
    station_id text NOT NULL REFERENCES stations (station_id),
    suggested_at timestamptz
);
