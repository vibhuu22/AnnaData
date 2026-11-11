"""
Weather from Open-Meteo (no API key required).

Days are now located by matching the actual date strings the API returns rather
than by fixed negative offsets, which silently reported the wrong day whenever
the response range differed from the request.
"""
import threading
import time

import requests
from datetime import date, timedelta

import weather_fallback
from config import (
    WEATHER_TIMEOUT,
    WEATHER_ATTEMPTS,
    WEATHER_CACHE_TTL,
    WEATHER_CACHE_PRECISION,
)

PAST_DAYS = 30
FORECAST_DAYS = 7

# Keyed by coarse coordinate, so every farmer in a district shares one reading.
_cache: dict[tuple, tuple] = {}
_cache_lock = threading.Lock()
_CACHE_MAX = 256

# Last upstream failure, surfaced on /health. Weather can fail in the deployed
# environment while working locally, and reading it back from the running
# service beats trying to catch the line in a log.
_last_error: str | None = None


def last_error() -> str | None:
    return _last_error


def _cache_key(lat, lon) -> tuple:
    p = WEATHER_CACHE_PRECISION
    return (round(float(lat), p), round(float(lon), p))


def weather_openmeteo(lat, lon) -> str:
    """The weather report as text, for the advisory prompt."""
    return weather_reading(lat, lon)[0]


def weather_series(lat, lon) -> dict | None:
    """The same reading as numbers, or None when only the fallback answered."""
    return weather_reading(lat, lon)[1]


def weather_reading(lat, lon) -> tuple[str, dict | None]:
    """The report text and the daily series it was written from.

    Both come from one request and share one cache entry. The text is what the
    prompt has always received; the series is what disease risk is computed
    from, because thresholds on humidity and temperature cannot be checked
    against a sentence. MET Norway's fallback has no daily humidity, so when it
    answers the series is None and risk is reported as unknown rather than low.
    """
    key = _cache_key(lat, lon)
    now = time.monotonic()

    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < WEATHER_CACHE_TTL:
            return hit[1], hit[2]

    series = _fetch_series(lat, lon)
    if isinstance(series, dict):
        report = format_weather(series)
    else:
        report, series = series, None

    # Open-Meteo's limit is per IP and shared with everyone else on this host,
    # so being refused says nothing about our own usage and retrying will not
    # help. Fall back to a provider with its own quota.
    if report.startswith("Weather data unavailable"):
        fallback = weather_fallback.fetch(lat, lon)
        if fallback:
            print(f"Weather served by fallback provider for ({lat}, {lon})")
            report = fallback

    # Never cache a failure - the next farmer deserves a fresh attempt.
    if not report.startswith("Weather data unavailable"):
        with _cache_lock:
            if len(_cache) >= _CACHE_MAX:
                _cache.clear()
            _cache[key] = (now, report, series)

    return report, series


def _fetch_weather(lat, lon) -> str:
    """The report for a coordinate, uncached. Kept for existing callers."""
    series = _fetch_series(lat, lon)
    return format_weather(series) if isinstance(series, dict) else series


def _fetch_series(lat, lon) -> dict | str:
    """Open-Meteo's daily series around today, or the unavailable notice."""
    global _last_error
    today = date.today()
    start = today - timedelta(days=PAST_DAYS)
    end = today + timedelta(days=FORECAST_DAYS)

    params = {
        "latitude": lat,
        "longitude": lon,
        # Live conditions. Farmers ask "what is it like right now" directly,
        # and daily aggregates cannot answer that - humidity especially, which
        # has no daily equivalent and drives disease pressure advice.
        "current": "temperature_2m,relative_humidity_2m,precipitation,"
                   "wind_speed_10m,weather_code",
        # Daily humidity is what the disease risk rules count days against.
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                 "weathercode,windspeed_10m_max,"
                 "relative_humidity_2m_mean,relative_humidity_2m_max",
        # Hourly, because the published disease forecasting models count
        # hours - JHULSACAST asks for so many hours at >= 90% humidity in a
        # moving window, which no daily figure can answer.
        "hourly": "temperature_2m,relative_humidity_2m",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": "auto",
    }

    data = None
    last_error = None
    for attempt in range(1, WEATHER_ATTEMPTS + 1):
        try:
            r = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params=params,
                timeout=WEATHER_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            break
        except Exception as e:
            last_error = e
            # Record the status so a rate limit is distinguishable from a
            # block or a timeout without guessing.
            status = getattr(getattr(e, "response", None), "status_code", "-")
            body = ""
            resp = getattr(e, "response", None)
            if resp is not None:
                try:
                    body = f" body={resp.text[:160]!r}"
                except Exception:
                    pass
            _last_error = f"[http {status}] {type(e).__name__}: {e}{body}"
            print(f"Weather attempt {attempt}/{WEATHER_ATTEMPTS} failed "
                  f"for ({lat}, {lon}) {_last_error}")
            if attempt < WEATHER_ATTEMPTS:
                time.sleep(attempt)

    if data is None:
        print(f"Weather lookup failed for ({lat}, {lon}): {last_error}")
        return "Weather data unavailable (lookup failed)."

    _last_error = None
    return series_from_response(data, lat, lon, today)


def series_from_response(data: dict, lat, lon, today: date) -> dict | str:
    """Open-Meteo's response as plain lists, with today located by date."""
    daily = data.get("daily")
    if not daily or not daily.get("time"):
        return f"Weather data unavailable (unexpected response: {data})."

    times = daily["time"]

    def series(key):
        return daily.get(key) or [None] * len(times)

    # Locate today by date string; fall back to the last past day available.
    today_str = today.isoformat()
    idx = times.index(today_str) if today_str in times else len(times) - FORECAST_DAYS - 1
    idx = max(0, min(idx, len(times) - 1))

    hourly = data.get("hourly") or {}
    hours = hourly.get("time") or []

    return {
        "lat": lat,
        "lon": lon,
        "dates": list(times),
        "tmin": series("temperature_2m_min"),
        "tmax": series("temperature_2m_max"),
        "precip": series("precipitation_sum"),
        "wind": series("windspeed_10m_max"),
        "rh_mean": series("relative_humidity_2m_mean"),
        "rh_max": series("relative_humidity_2m_max"),
        # Local times as "YYYY-MM-DDTHH:MM", aligned with the two lists below.
        "hours": list(hours),
        "temp_hourly": hourly.get("temperature_2m") or [None] * len(hours),
        "rh_hourly": hourly.get("relative_humidity_2m") or [None] * len(hours),
        "current": data.get("current") or {},
        "today_index": idx,
    }


def format_weather(s: dict) -> str:
    """The report the advisory prompt has always received, from a series."""
    lat, lon, idx = s["lat"], s["lon"], s["today_index"]
    times, tmin, tmax = s["dates"], s["tmin"], s["tmax"]
    precip, wind = s["precip"], s["wind"]

    def num(values, i, default=0.0):
        v = values[i] if 0 <= i < len(values) else None
        return default if v is None else v

    past_rain = [num(precip, i) for i in range(idx)]
    last_30_sum = sum(past_rain)
    last_10 = past_rain[-10:]
    last_10_avg = sum(last_10) / len(last_10) if last_10 else 0.0

    forecast_lines = []
    for i in range(idx + 1, len(times)):
        forecast_lines.append(
            f"{times[i]}: {num(tmin, i)}-{num(tmax, i)}C, "
            f"{num(precip, i)} mm rain, wind {num(wind, i)} km/h"
        )

    # Live conditions. Farmers ask what it is like right now, and a daily
    # aggregate cannot answer that - humidity especially, which has no daily
    # equivalent and is what drives fungal disease pressure.
    current = s.get("current") or {}
    now_parts = []
    for key, unit, label in (
        ("temperature_2m", "C", "temperature"),
        ("relative_humidity_2m", "%", "humidity"),
        ("precipitation", " mm", "precipitation"),
        ("wind_speed_10m", " km/h", "wind"),
    ):
        value = current.get(key)
        if value is not None:
            now_parts.append(f"{label} {value}{unit}")
    now_block = f"- Right now: {', '.join(now_parts)}\n" if now_parts else ""

    return (
        f"Weather Report for ({lat}, {lon}):\n"
        f"{now_block}"
        f"- Today's temp: {num(tmin, idx)}-{num(tmax, idx)}C, "
        f"Rain: {num(precip, idx)} mm, Wind: {num(wind, idx)} km/h\n"
        f"- Last 10 days avg rainfall: {last_10_avg:.2f} mm/day\n"
        f"- Last 1 month total rainfall: {last_30_sum:.2f} mm\n"
        f"- {len(forecast_lines)}-day Forecast:\n" + "\n".join(forecast_lines)
    )
