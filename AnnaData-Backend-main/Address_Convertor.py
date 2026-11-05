"""
Place name to coordinates.

Two providers, tried in order:

  Google Maps  - used only when LOCATION_API_KEY is set. Better at messy input
                 and Indian village names, but needs a billing account.
  Nominatim    - OpenStreetMap's free geocoder, and the default. No key.

Nominatim's usage policy asks for at most one request per second, a User-Agent
that identifies the application, and that results are cached rather than
re-requested. All three are honoured here: calls are throttled, the agent
identifies itself, and results are memoised in-process on top of the permanent
per-farmer cache in the profile store - a given farmer is geocoded once, ever.

Returns (None, None) on any failure rather than raising, so a geocoding outage
degrades the answer instead of failing the request.
"""
import threading
import time
from typing import NamedTuple

import requests

from config import (
    LOCATION_API_KEY,
    HTTP_TIMEOUT,
    NOMINATIM_URL,
    NOMINATIM_USER_AGENT,
    GEOCODE_COUNTRY,
)

# Nominatim asks for no more than one request per second.
_MIN_INTERVAL = 1.1
_last_call = 0.0
_throttle = threading.Lock()

# Districts repeat heavily across farmers, so an in-process cache saves most
# calls even before the per-farmer coordinates are stored.
_cache: dict[str, "Place"] = {}
_CACHE_MAX = 512


class Place(NamedTuple):
    """A geocoded place, and how specific it turned out to be.

    Coordinates alone were not enough. A farmer in Kharagpur asked about "rice
    varieties in west bengal", the state geocoded fine, and the state's centroid
    - 83 km away, near Bankura - was written over their farm. Nothing in
    (lat, lon) said one was a city and the other a whole state, so nothing could
    refuse the overwrite. The provider knew; we were discarding it.
    """
    latitude: float | None
    longitude: float | None
    kind: str | None = None          # 'state', 'city', 'village', ...
    district: str | None = None
    state: str | None = None
    name: str | None = None          # set by reverse(): what to call the place


# How specific a place is, higher being finer. Used only to refuse a downgrade,
# never to reject an update outright, so an unfamiliar type still gets stored.
PRECISION = {
    "country": 1,
    "state": 2, "region": 2, "administrative_area_level_1": 2,
    "state_district": 3, "district": 3, "county": 3,
    "administrative_area_level_2": 3,
    "city": 4, "town": 4, "municipality": 4, "locality": 4,
    "village": 5, "suburb": 5, "hamlet": 5, "neighbourhood": 5,
    "sublocality": 5, "postcode": 5, "postal_code": 5,
}


def precision(kind: str | None) -> int | None:
    """Rank for a place type, or None when the type is not one we know."""
    if not kind:
        return None
    return PRECISION.get(kind.strip().lower())


def _throttled_get(url: str, params: dict, headers: dict, timeout=None):
    global _last_call
    with _throttle:
        wait = _MIN_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
    return requests.get(url, params=params, headers=headers, timeout=timeout or HTTP_TIMEOUT)


def _google(address: str):
    response = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"address": address, "key": LOCATION_API_KEY,
                "components": f"country:{GEOCODE_COUNTRY}"},
        timeout=HTTP_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()

    if data.get("status") == "OK" and data.get("results"):
        top = data["results"][0]
        loc = top["geometry"]["location"]
        # Google reports the match as a list of types, most specific first, and
        # names the district as administrative_area_level_2.
        kind = next((t for t in top.get("types", []) if t in PRECISION), None)
        district = state = None
        for part in top.get("address_components", []):
            types = part.get("types", [])
            if "administrative_area_level_2" in types:
                district = part.get("long_name")
            elif "administrative_area_level_1" in types:
                state = part.get("long_name")
        return Place(loc["lat"], loc["lng"], kind=kind, district=district, state=state)

    print(f"Google geocoding returned {data.get('status')} for {address!r}")
    return Place(None, None)


def _nominatim(address: str):
    response = _throttled_get(
        NOMINATIM_URL,
        {
            "q": address,
            "format": "jsonv2",
            "limit": 1,
            # The breakdown costs nothing extra on a call we already make, and
            # carries both the district and how specific the match was.
            "addressdetails": 1,
            # Farmer queries are Indian; the bias stops "Nagpur" resolving abroad.
            "countrycodes": GEOCODE_COUNTRY,
        },
        # Nominatim rejects requests without an identifying User-Agent.
        {"User-Agent": NOMINATIM_USER_AGENT, "Accept": "application/json"},
    )
    response.raise_for_status()
    results = response.json()

    if results:
        top = results[0]
        parts = top.get("address") or {}
        return Place(
            float(top["lat"]), float(top["lon"]),
            kind=top.get("addresstype") or top.get("type"),
            district=(parts.get("state_district") or parts.get("county")
                      or parts.get("district")),
            state=parts.get("state"),
        )

    print(f"Nominatim found nothing for {address!r}")
    return Place(None, None)


def locate(address: str) -> Place:
    """Geocode a place, keeping what kind of place it turned out to be."""
    if not address:
        return Place(None, None)

    address = address.strip()
    if not address or address.lower() == "unknown":
        return Place(None, None)

    key = address.lower()
    if key in _cache:
        return _cache[key]

    provider = "google" if LOCATION_API_KEY else "nominatim"
    try:
        place = _google(address) if LOCATION_API_KEY else _nominatim(address)
    except Exception as e:
        print(f"Geocoding failed ({provider}) for {address!r}: {e}")
        return Place(None, None)

    if place.latitude is not None and place.longitude is not None:
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[key] = place
        print(f"Geocoded {address!r} -> ({place.latitude}, {place.longitude}) "
              f"via {provider} [{place.kind or 'unknown kind'}"
              + (f", {place.district}" if place.district else "") + "]")

    return place


def get_location(address: str):
    """Get (latitude, longitude) for a place, or (None, None)."""
    place = locate(address)
    return place.latitude, place.longitude


# --- Coordinates to a place --------------------------------------------------
#
# A browser that has been allowed its location sends coordinates with every
# question. Weather and soil need only those, but a mandi price needs the
# state, the dose table the district, and a farmer is told "for Kharagpur", not
# "for 22.34, 87.30". Rounded to two decimals - about a kilometre - so a phone
# asking twenty questions from the same field is looked up once, and so a
# Nominatim outage costs one slow request rather than one per question.

_REVERSE_TIMEOUT = 4
_reverse_cache: dict[tuple, tuple] = {}
_REVERSE_FAIL_SECONDS = 600
# Most specific first: what a farmer would call where they are.
_PLACE_FIELDS = ("village", "hamlet", "town", "city", "suburb", "municipality",
                 "city_district", "county", "state_district")


def _reverse_key(latitude, longitude):
    return (round(float(latitude), 2), round(float(longitude), 2))


def _nominatim_reverse(latitude, longitude) -> Place:
    url = NOMINATIM_URL.rsplit("/", 1)[0] + "/reverse"
    response = _throttled_get(
        url,
        {"lat": latitude, "lon": longitude, "format": "jsonv2", "zoom": 12,
         "addressdetails": 1, "accept-language": "en"},
        {"User-Agent": NOMINATIM_USER_AGENT, "Accept": "application/json"},
        timeout=_REVERSE_TIMEOUT,
    )
    response.raise_for_status()
    top = response.json() or {}
    parts = top.get("address") or {}
    if not parts:
        return Place(latitude, longitude)
    kind = top.get("addresstype") or top.get("type")
    name = top.get("name") if kind in PRECISION else None
    name = name or next((parts[f] for f in _PLACE_FIELDS if parts.get(f)), None)
    return Place(latitude, longitude, kind=kind,
                 district=parts.get("state_district") or parts.get("county") or parts.get("district"),
                 state=parts.get("state"), name=name)


def _google_reverse(latitude, longitude) -> Place:
    response = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={"latlng": f"{latitude},{longitude}", "key": LOCATION_API_KEY, "language": "en"},
        timeout=_REVERSE_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "OK" or not data.get("results"):
        return Place(latitude, longitude)
    name = district = state = kind = None
    for part in data["results"][0].get("address_components", []):
        types = part.get("types", [])
        if not name and ({"locality", "sublocality"} & set(types)):
            name, kind = part.get("long_name"), "locality"
        if "administrative_area_level_2" in types:
            district = part.get("long_name")
        elif "administrative_area_level_1" in types:
            state = part.get("long_name")
    return Place(latitude, longitude, kind=kind, district=district, state=state,
                 name=name or district)


def reverse(latitude, longitude) -> Place:
    """The place at these coordinates: name, district and state where known.

    Never raises. On any failure the coordinates come back alone, so the
    answer still gets weather and soil for where the farmer is.
    """
    if latitude is None or longitude is None:
        return Place(None, None)
    key = _reverse_key(latitude, longitude)
    hit = _reverse_cache.get(key)
    if hit:
        place, failed_at = hit
        if failed_at is None or time.monotonic() - failed_at < _REVERSE_FAIL_SECONDS:
            return Place(latitude, longitude, *place[2:])
    provider = "google" if LOCATION_API_KEY else "nominatim"
    try:
        place = (_google_reverse if LOCATION_API_KEY else _nominatim_reverse)(latitude, longitude)
    except Exception as e:
        print(f"Reverse geocoding failed ({provider}) for {key}: {e}")
        _reverse_cache[key] = (Place(latitude, longitude), time.monotonic())
        return Place(latitude, longitude)
    if len(_reverse_cache) >= _CACHE_MAX:
        _reverse_cache.clear()
    _reverse_cache[key] = (place, None if place.name or place.state else time.monotonic())
    print(f"Reverse geocoded {key} -> {place.name}, {place.district}, {place.state} via {provider}")
    return place
