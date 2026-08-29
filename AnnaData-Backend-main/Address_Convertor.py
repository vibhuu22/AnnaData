"""
Address -> coordinates.

Returns (None, None) on any failure instead of raising. The agent treats that as
"no location known" and falls back to a general answer, so a geocoding outage or
a missing API key degrades the reply rather than erroring the request.
"""
import requests

from config import LOCATION_API_KEY, HTTP_TIMEOUT


def get_location(address: str):
    """Get (latitude, longitude) for an address, or (None, None)."""
    if not address or address.lower() == "unknown":
        return None, None

    if not LOCATION_API_KEY:
        print("Geocoding skipped: LOCATION_API_KEY not set")
        return None, None

    try:
        response = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": address, "key": LOCATION_API_KEY},
            timeout=HTTP_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "OK" and data.get("results"):
            location = data["results"][0]["geometry"]["location"]
            return location["lat"], location["lng"]

        print(
            f"Geocoding failed for {address!r}: "
            f"{data.get('status')} - {data.get('error_message', '')}"
        )
        return None, None

    except Exception as e:
        print(f"Geocoding request failed for {address!r}: {e}")
        return None, None
