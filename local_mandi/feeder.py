"""PC publisher: official API -> complete, current state snapshots in Neon.

No HTTP listener, SMS sending, model calls, or application schema migrations.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import psycopg
import requests
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
IST = timezone(timedelta(hours=5, minutes=30))
PAGE_SIZE = 1000
MAX_OFFSET = 10000
ALIASES = {"keralam": "kerala", "orissa": "odisha", "pondicherry": "puducherry",
           "uttaranchal": "uttarakhand", "nct of delhi": "delhi",
           "jammu and kashmir": "jammu & kashmir"}


class FeedError(Exception):
    """Only deliberately safe, credential-free descriptions reach the UI."""


class Cancelled(FeedError):
    pass


def state_key(value):
    name = value.strip().lower()
    return ALIASES.get(name, name)


def today():
    return datetime.now(IST).date()


def check_stop(stop):
    if stop.is_set():
        raise Cancelled("Stopped. Previous cached prices remain available.")


def fetch_state(state, api_key, stop, log, client=None):
    """Never publish a truncated page, another state's prices, or stale rows."""
    client = client or requests.Session()
    records, offset, expected, fingerprints = [], 0, None, set()
    while True:
        check_stop(stop)
        if offset >= MAX_OFFSET:
            raise FeedError(f"{state}: API pagination limit reached; snapshot not published.")
        try:
            response = client.get(API, params={"api-key": api_key, "format": "json",
                "filters[state]": state, "limit": PAGE_SIZE, "offset": offset},
                headers={"User-Agent": "AnnaData/1.0 (PC mandi publisher)"}, timeout=(8, 25))
            if response.status_code != 200:
                raise FeedError(f"{state}: government API returned HTTP {response.status_code}.")
            payload = response.json()
        except (requests.RequestException, ValueError):
            raise FeedError(f"{state}: government API connection or response failed.") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
            raise FeedError(f"{state}: invalid government API response.")
        try:
            total = int(payload["total"])
        except (KeyError, TypeError, ValueError):
            raise FeedError(f"{state}: source did not report a usable total.") from None
        if total < 0 or (expected is not None and total != expected):
            raise FeedError(f"{state}: publication changed during paging; retry later.")
        expected = total
        page = payload["records"]
        if not page:
            if offset < total:
                raise FeedError(f"{state}: incomplete publication; old cache retained.")
            break
        fingerprint = json.dumps(page, sort_keys=True)
        if fingerprint in fingerprints:
            raise FeedError(f"{state}: repeated API page; old cache retained.")
        fingerprints.add(fingerprint)
        records.extend(page)
        offset += len(page)
        log(f"{state}: downloaded {offset} / {total} source rows")
        if offset >= total:
            break
    check_stop(stop)
    current, seen = [], set()
    for row in records:
        if not isinstance(row, dict):
            raise FeedError(f"{state}: malformed price row.")
        if state_key(str(row.get("state", ""))) != state_key(state):
            continue  # Upstream state filters also return other 'Pradesh' states.
        try:
            date = datetime.strptime(row["arrival_date"], "%d/%m/%Y").date()
            prices = [Decimal(str(row[k])) for k in ("min_price", "modal_price", "max_price")]
            if not all(p.is_finite() and p >= 0 for p in prices) or not prices[0] <= prices[1] <= prices[2]:
                raise ValueError()
            if not all(row.get(k) for k in ("market", "district", "commodity")):
                raise ValueError()
        except (KeyError, ValueError, InvalidOperation, TypeError):
            raise FeedError(f"{state}: invalid dates or prices; snapshot not published.") from None
        if date != today():
            continue
        signature = json.dumps(row, sort_keys=True)
        if signature not in seen:
            current.append(row)
            seen.add(signature)
    if not current:
        raise FeedError(f"{state}: no prices dated today ({today()}); old cache retained.")
    return current


def summary(rows):
    return "\n".join(
        f"Market: {r['market']} | Commodity: {r['commodity']} ({r.get('variety', 'N/A')}) | "
        f"Grade: {r.get('grade', 'N/A')} | Arrival Date: {r['arrival_date']} | "
        f"Min Price: Rs{r['min_price']} | Max Price: Rs{r['max_price']} | Modal Price: Rs{r['modal_price']}"
        for r in rows)


def publish(state, rows, database_url, stop):
    check_stop(stop)
    # Recheck after downloading in case the job crosses midnight in India.
    if any(r.get("arrival_date") != today().strftime("%d/%m/%Y") for r in rows):
        raise FeedError(f"{state}: date changed during refresh; retry required.")
    try:
        with psycopg.connect(database_url, connect_timeout=15) as conn:
            conn.execute("SET LOCAL statement_timeout = 20000")
            conn.execute("SET LOCAL lock_timeout = 5000")
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("pc-mandi:" + state_key(state),))
            check_stop(stop)
            conn.execute("""INSERT INTO mandi_cache (state, commodity, summary, records, fetched_at)
                VALUES (%s, '', %s, %s::jsonb, now())
                ON CONFLICT (state, commodity) DO UPDATE SET
                  summary = EXCLUDED.summary, records = EXCLUDED.records, fetched_at = now()""",
                (state_key(state), summary(rows), json.dumps(rows)))
            # Crop-specific rows are deliberately left alone. They used to be
            # deleted here because the reader ordered by exact crop before
            # recency, so a months-old (state, potato) row outranked a snapshot
            # published this morning. The reader now ranks by date first and
            # narrows the state snapshot to the crop it was asked about, which
            # is tested, so nothing needs removing for fresh prices to win.
            #
            # Not deleting them is the safer property for a job that runs
            # unattended: this publisher only ever inserts, so a bad run cannot
            # destroy the only prices on file. Those older rows stay as a
            # fallback and lose on age the moment a snapshot lands.
            count = conn.execute("SELECT jsonb_array_length(records) FROM mandi_cache WHERE state=%s AND commodity=''",
                                 (state_key(state),)).fetchone()[0]
            if count != len(rows):
                raise FeedError(f"{state}: database verification failed; transaction rolled back.")
            check_stop(stop)
    except FeedError:
        raise
    except psycopg.Error:
        raise FeedError(f"{state}: Neon connection/write failed; transaction rolled back.") from None


def sync(states, stop=None, log=print, dry_run=False):
    stop = stop or threading.Event()
    credentials = dotenv_values(ROOT / "AnnaData-Backend-main" / ".env")
    if not credentials.get("GOV_API_KEY") or (not dry_run and not credentials.get("DATABASE_URL")):
        raise FeedError("GOV_API_KEY and DATABASE_URL must be configured in the backend .env.")
    results, errors = [], []
    with requests.Session() as client:
        for state in dict.fromkeys(s.strip() for s in states if s.strip()):
            check_stop(stop)
            try:
                rows = fetch_state(state, credentials["GOV_API_KEY"], stop, log, client)
                if not dry_run:
                    publish(state, rows, credentials["DATABASE_URL"], stop)
                result = {"state": state, "rows": len(rows), "price_date": str(today()),
                          "published": not dry_run, "time": datetime.now(IST).isoformat()}
                results.append(result)
                log(f"{state}: {'validated' if dry_run else 'published and verified'} {len(rows)} prices dated {today()}")
            except Cancelled:
                raise
            except FeedError as exc:
                errors.append(str(exc))
                log(str(exc))
    return {"results": results, "errors": errors}
