"""
Fill the mandi price cache from a network the price service will talk to.

data.gov.in refuses the egress addresses Cloud Run uses in asia-south1, where
the backend runs: the connection is closed in under a second, with no status
line, whatever User-Agent is sent. It is not a geography or an ASN rule - the
same request from Cloud Build, and from Cloud Run in us-central1, europe-west1
and asia-southeast1, is answered normally:

    asia-south1      34.96.40.124    connection closed, 0.62s
    asia-southeast1  34.96.48.8      HTTP 400 in 1.43s
    europe-west1     34.96.41.0      HTTP 400 in 5.05s
    us-central1      136.124.34.212  HTTP 400 in 1.47s

(400 because the probe carried no API key - the point is that it was answered.)

So this runs as a scheduled job in a region that is not blocked, and writes what
it finds into the same table the backend already reads when the live call fails.
The backend keeps serving from asia-south1, near the farmers, and never has to
reach the upstream itself.

Prices carry an arrival_date, not a timestamp: the source publishes once a day,
so a daily refresh loses nothing that a live call would have caught.

The whole national daily snapshot is a few hundred rows, so it is fetched in one
request and split by state, rather than asking per state. That also sidesteps the
upstream's filters[state] being a token match - see Mandi_Price_Tool._in_state.

Usage:  python -m tools.warm_mandi_cache
"""
import collections
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import Mandi_Price_Tool as mandi  # noqa: E402
from config import GOV_API_KEY  # noqa: E402

# One page big enough for the entire daily publication.
FETCH_LIMIT = 10000
TIMEOUT = 60


def fetch_all() -> list:
    params = {"api-key": GOV_API_KEY, "format": "json", "limit": FETCH_LIMIT}
    response = requests.get(mandi.RESOURCE_URL, params=params,
                            headers=mandi.HEADERS, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json().get("records", [])


def run() -> int:
    if not GOV_API_KEY:
        print("GOV_API_KEY not set; nothing to do")
        return 1

    # Without this the pool is never built, _cache_store returns early, and the
    # job reports success having written nothing - which is how a warm cache
    # would silently become an empty one.
    if not db.init():
        print("Database unavailable; refusing to report a warm cache")
        return 1

    try:
        records = fetch_all()
    except Exception as e:
        # Record the failure so the service keeps its capability withdrawn
        # rather than advertising prices it cannot produce.
        mandi._record_outcome(False)
        print(f"Mandi warm failed: {e}")
        return 1

    if not records:
        mandi._record_outcome(False)
        print("Mandi warm returned no records")
        return 1

    by_state = collections.defaultdict(list)
    for record in records:
        state = (record.get("state") or "").strip()
        if state:
            by_state[state].append(record)

    for state, rows in sorted(by_state.items()):
        mandi._cache_store(state, None, mandi.format_state_data(rows), records=rows)

    # Read back rather than trust the writes: _cache_store swallows its errors so
    # that a caching problem never breaks a farmer's answer, which means the only
    # way to know the cache is warm is to look.
    stored = _stored_states()
    missing = sorted({s.strip().lower() for s in by_state} - stored)
    if missing:
        mandi._record_outcome(False)
        print(f"Cache write incomplete; {len(missing)} state(s) missing: "
              + ", ".join(missing))
        return 1

    mandi._record_outcome(True)
    print(f"Cached {len(records)} record(s) across {len(by_state)} state(s): "
          + ", ".join(f"{s} {len(r)}" for s, r in sorted(by_state.items())))
    return 0


def _stored_states() -> set:
    """States with a snapshot written in the last hour."""
    try:
        with db.connection() as conn:
            rows = conn.execute(
                """SELECT state FROM mandi_cache
                    WHERE commodity = '' AND records IS NOT NULL
                      AND fetched_at > now() - interval '1 hour'"""
            ).fetchall()
    except Exception as e:
        print(f"Could not verify cache writes: {e}")
        return set()
    # _cache_store lowercases the key; compare on the same footing.
    return {r[0] for r in rows}


if __name__ == "__main__":
    try:
        code = run()
    finally:
        db.close()
    raise SystemExit(code)
