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

    while len(records) < MANDI_MAX_RECORDS:
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


def get_state_data(state: str, commodity: str | None = None) -> str:
    """Mandi prices for a state, narrowed to a commodity when one is known."""
    if not state or state.lower() == "unknown":
        return "Mandi price data unavailable (no state identified)."

    if not GOV_API_KEY:
        return "Mandi price data unavailable (GOV_API_KEY not set)."

    if commodity and commodity.lower() == "unknown":
        commodity = None

    if _circuit_open():
        return "Mandi price data unavailable (price service is down)."

    try:
        records = _fetch(state, commodity)

        # A crop filter that matches nothing is worse than a broader answer.
        if not records and commodity:
            records = _fetch(state, None)

        _record_success()
        return format_state_data(records)

    except Exception as e:
        _record_failure()
        print(f"Mandi price lookup failed for state={state!r}: {e}")
        return "Mandi price data unavailable (lookup failed)."
