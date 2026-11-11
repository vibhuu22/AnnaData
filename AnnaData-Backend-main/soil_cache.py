"""
Soil readings, kept once fetched: in this process, then in Postgres.

Soil is read from a fixed global map (OpenLandMap, 250 m), so a point returns
the same three numbers every time it is asked. Fetching them anyway made Earth
Engine the slowest call a disease question waited on: measured at about 1.4 s
against 0.8 s for the weather, it added some 0.7 s to every answer once disease
questions began reading the soil.

Two layers, because Cloud Run runs several instances and restarts them:

- in memory, per process: free, gone on restart
- in Postgres, shared by every instance and kept across restarts: one indexed
  read, about the cost of the dose lookup that already runs alongside

Nothing expires, because the map does not change. What could change is the
map itself, so the dataset ids are part of the key: moving to a new version
simply misses, and old rows are never served for it.

Points are rounded to SOIL_CACHE_PRECISION decimal places (default 3, about
110 m) for the key. That is well inside the 500 m neighbourhood each reading
already averages over, so a farmer whose phone reports a slightly different
position each time still hits their own reading. Failures are never stored.
Every database problem is logged and treated as a miss: the cache can make an
answer faster, never stop one.
"""
import json
import threading

import db
from config import SOIL_CACHE_PRECISION

SCHEMA = """
CREATE TABLE IF NOT EXISTS soil_cache (
    lat_key    TEXT NOT NULL,
    lon_key    TEXT NOT NULL,
    source     TEXT NOT NULL,     -- the dataset ids the readings came from
    readings   JSONB NOT NULL,    -- raw layer values, as Earth Engine stores them
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (lat_key, lon_key, source)
);
"""

_memory: dict[tuple, dict] = {}
_lock = threading.Lock()
_MAX = 4096
_schema_ready = False


def key(lat, lon, source: str) -> tuple[str, str, str]:
    """Text, not float, so the same point is the same key in Python and SQL."""
    p = SOIL_CACHE_PRECISION
    return (f"{round(float(lat), p):.{p}f}", f"{round(float(lon), p):.{p}f}", source)


def _remember(k, readings: dict):
    with _lock:
        if len(_memory) >= _MAX:
            _memory.clear()
        _memory[k] = dict(readings)


def _ensure_schema(conn):
    global _schema_ready
    if not _schema_ready:
        conn.execute(SCHEMA)
        _schema_ready = True


def get(lat, lon, source: str) -> dict | None:
    """The raw readings for this point, or None if they have to be fetched."""
    k = key(lat, lon, source)
    with _lock:
        hit = _memory.get(k)
    if hit is not None:
        return dict(hit)

    if not db.is_available():
        return None
    try:
        with db.connection() as conn:
            _ensure_schema(conn)
            row = conn.execute(
                "SELECT readings FROM soil_cache"
                " WHERE lat_key = %s AND lon_key = %s AND source = %s",
                k,
            ).fetchone()
    except Exception as e:
        print(f"Soil cache read failed: {e}")
        return None
    if not row:
        return None
    readings = row[0] if isinstance(row[0], dict) else json.loads(row[0])
    _remember(k, readings)
    return dict(readings)


def put(lat, lon, source: str, readings: dict) -> None:
    """Keep a complete reading. Callers never pass a failed one."""
    k = key(lat, lon, source)
    _remember(k, readings)
    if not db.is_available():
        return
    try:
        with db.connection() as conn:
            _ensure_schema(conn)
            conn.execute(
                "INSERT INTO soil_cache (lat_key, lon_key, source, readings)"
                " VALUES (%s, %s, %s, %s)"
                " ON CONFLICT (lat_key, lon_key, source) DO NOTHING",
                (*k, json.dumps(readings)),
            )
    except Exception as e:
        print(f"Soil cache write failed: {e}")


def clear_memory() -> None:
    """For tests and benchmarks: forget what this process holds."""
    with _lock:
        _memory.clear()
