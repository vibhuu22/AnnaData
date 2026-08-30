"""
Mandi (market) prices from data.gov.in.

The previous version paged through every record for a state with no cap and no
commodity filter, then fed the whole dump into the LLM prompt - thousands of
rows for a large state. It now filters by commodity where known and stops at
MANDI_MAX_RECORDS.
"""
import threading
import time

import requests

from config import (
    GOV_API_KEY,
    MANDI_MAX_RECORDS,
    GOV_API_TIMEOUT,
    GOV_API_DEADLINE,
    GOV_API_ATTEMPTS,
    GOV_FAILURE_THRESHOLD,
    GOV_CIRCUIT_COOLDOWN,
)

RESOURCE_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
PAGE_SIZE = 100

# Circuit breaker. After repeated failures the upstream is presumed down and
# calls are skipped until the cooldown expires, so a farmer gets an immediate
# answer minus prices rather than waiting out two timeouts to be told the same.
_consecutive_failures = 0
_circuit_opened_at = 0.0
_breaker_lock = threading.Lock()


def _circuit_open() -> bool:
    with _breaker_lock:
        if _consecutive_failures < GOV_FAILURE_THRESHOLD:
            return False
        if time.monotonic() - _circuit_opened_at < GOV_CIRCUIT_COOLDOWN:
            return True
        # Cooldown elapsed: allow one probe through to test recovery.
        return False


def _record_success():
    global _consecutive_failures
    with _breaker_lock:
        _consecutive_failures = 0


def _record_failure():
    global _consecutive_failures, _circuit_opened_at
    with _breaker_lock:
        _consecutive_failures += 1
        if _consecutive_failures >= GOV_FAILURE_THRESHOLD:
            _circuit_opened_at = time.monotonic()
            print(f"data.gov.in circuit opened after {_consecutive_failures} "
                  f"failures; pausing calls for {GOV_CIRCUIT_COOLDOWN}s")


def format_state_data(records) -> str:
    """Convert market records into a readable summary."""
    if not records:
        return "No mandi price data available for the selected state."

    lines = []
    for record in records:
        lines.append(
            f"Market: {record.get('market', 'N/A')} | "
            f"Commodity: {record.get('commodity', 'N/A')} "
            f"({record.get('variety', 'N/A')}) | "
            f"Grade: {record.get('grade', 'N/A')} | "
            f"Arrival Date: {record.get('arrival_date', 'N/A')} | "
            f"Min Price: Rs{record.get('min_price', 'N/A')} | "
            f"Max Price: Rs{record.get('max_price', 'N/A')} | "
            f"Modal Price: Rs{record.get('modal_price', 'N/A')}"
        )

    return "\n".join(lines)


def _fetch(state: str, commodity: str | None) -> list:
    records = []
    offset = 0
    deadline = time.monotonic() + GOV_API_DEADLINE

    while len(records) < MANDI_MAX_RECORDS:
        # Paging multiplies the per-request timeout, so the fetch as a whole
        # gets a deadline. Whatever has arrived by then is returned: a partial
        # list of markets is a usable answer, a timeout is not.
        if time.monotonic() > deadline:
            print(f"Mandi fetch deadline reached with {len(records)} record(s)")
            break

        params = {
            "api-key": GOV_API_KEY,
            "format": "json",
            "filters[state]": state,
            "limit": PAGE_SIZE,
            "offset": offset,
        }
        if commodity:
            params["filters[commodity]"] = commodity

        page = None
        for attempt in range(1, GOV_API_ATTEMPTS + 1):
            try:
                response = requests.get(RESOURCE_URL, params=params,
                                        timeout=GOV_API_TIMEOUT)
                response.raise_for_status()
                page = response.json().get("records", [])
                break
            except Exception as e:
                print(f"data.gov.in attempt {attempt} failed: {e}")
                if attempt == GOV_API_ATTEMPTS:
                    raise
        if page is None:
            break

        if not page:
            break

        records.extend(page)
        offset += PAGE_SIZE

    return records[:MANDI_MAX_RECORDS]


# Successful lookups are kept so an outage degrades to a stale price rather
# than to nothing. A farmer deciding when to sell is better served by "cotton
# was Rs 7,200 a quintal in Nagpur on 25 August" than by silence, provided the
# date is stated plainly and they can see how old it is.
CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS mandi_cache (
    state      TEXT NOT NULL,
    commodity  TEXT NOT NULL DEFAULT '',
    summary    TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (state, commodity)
);
"""


def _cache_key(state: str, commodity: str | None) -> tuple:
    return (state.strip().lower(), (commodity or "").strip().lower())


def _cache_store(state: str, commodity: str | None, summary: str) -> None:
    import db

    if not db.is_available() or not summary:
        return
    st, cm = _cache_key(state, commodity)
    try:
        with db.connection() as conn:
            conn.execute(CACHE_SCHEMA)
            conn.execute(
                """
                INSERT INTO mandi_cache (state, commodity, summary, fetched_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (state, commodity)
                DO UPDATE SET summary = EXCLUDED.summary, fetched_at = now()
                """,
                (st, cm, summary),
            )
    except Exception as e:
        print(f"Could not cache mandi prices: {e}")


def _cache_lookup(state: str, commodity: str | None) -> str | None:
    import db
    from datetime import datetime, timezone

    if not db.is_available():
        return None
    st, cm = _cache_key(state, commodity)
    try:
        with db.connection() as conn:
            conn.execute(CACHE_SCHEMA)
            row = conn.execute(
                """
                SELECT summary, fetched_at FROM mandi_cache
                 WHERE state = %s AND (commodity = %s OR commodity = '')
              ORDER BY (commodity = %s) DESC, fetched_at DESC
                 LIMIT 1
                """,
                (st, cm, cm),
            ).fetchone()
    except Exception as e:
        print(f"Mandi cache lookup failed: {e}")
        return None

    if not row:
        return None

    summary, fetched = row
    age_days = (datetime.now(timezone.utc) - fetched).days
    when = fetched.strftime("%d %B %Y")
    return (
        f"Mandi prices are temporarily unavailable from the government service. "
        f"These are the last prices on record, from {when} "
        f"({age_days} day(s) old) - tell the farmer the date and that they "
        f"should confirm today's rate at the mandi:\n{summary}"
    )


def get_state_data(state: str, commodity: str | None = None) -> str:
    """Mandi prices for a state, narrowed to a commodity when one is known."""
    if not state or state.lower() == "unknown":
        return "Mandi price data unavailable (no state identified)."

    if not GOV_API_KEY:
        return "Mandi price data unavailable (GOV_API_KEY not set)."

    if commodity and commodity.lower() == "unknown":
        commodity = None

    if _circuit_open():
        return _cache_lookup(state, commodity) or             "Mandi price data unavailable (the government price service is down)."

    try:
        records = _fetch(state, commodity)

        # A crop filter that matches nothing is worse than a broader answer.
        if not records and commodity:
            records = _fetch(state, None)

        _record_success()
        summary = format_state_data(records)
        if records:
            _cache_store(state, commodity, summary)
        return summary

    except Exception as e:
        _record_failure()
        print(f"Mandi price lookup failed for state={state!r}: {e}")
        return _cache_lookup(state, commodity) or             "Mandi price data unavailable (lookup failed)."
