"""
Mandi (market) prices from data.gov.in.

The previous version paged through every record for a state with no cap and no
commodity filter, then fed the whole dump into the LLM prompt - thousands of
rows for a large state. It now filters by commodity where known and stops at
MANDI_MAX_RECORDS.
"""
import requests

from config import GOV_API_KEY, MANDI_MAX_RECORDS, HTTP_TIMEOUT

RESOURCE_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
PAGE_SIZE = 100


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

        response = requests.get(RESOURCE_URL, params=params, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        page = response.json().get("records", [])

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

    try:
        records = _fetch(state, commodity)

        # A crop filter that matches nothing is worse than a broader answer.
        if not records and commodity:
            records = _fetch(state, None)

        return format_state_data(records)

    except Exception as e:
        print(f"Mandi price lookup failed for state={state!r}: {e}")
        return "Mandi price data unavailable (lookup failed)."
