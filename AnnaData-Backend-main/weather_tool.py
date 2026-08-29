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


def _cache_key(lat, lon) -> tuple:
    p = WEATHER_CACHE_PRECISION
    return (round(float(lat), p), round(float(lon), p))


def weather_openmeteo(lat, lon) -> str:
    key = _cache_key(lat, lon)
    now = time.monotonic()

    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < WEATHER_CACHE_TTL:
            return hit[1]

    report = _fetch_weather(lat, lon)

    # Never cache a failure - the next farmer deserves a fresh attempt.
    if not report.startswith("Weather data unavailable"):
        with _cache_lock:
            if len(_cache) >= _CACHE_MAX:
                _cache.clear()
            _cache[key] = (now, report)

    return report


def _fetch_weather(lat, lon) -> str:
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
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                 "weathercode,windspeed_10m_max",
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
            # Log every attempt with the status, so a rate limit is
            # distinguishable from a timeout in the deployment logs.
            status = getattr(getattr(e, "response", None), "status_code", "-")
            print(f"Weather attempt {attempt}/{WEATHER_ATTEMPTS} failed "
                  f"for ({lat}, {lon}) [http {status}]: {e}")
            if attempt < WEATHER_ATTEMPTS:
                time.sleep(attempt)

    if data is None:
        print(f"Weather lookup failed for ({lat}, {lon}): {last_error}")
        return "Weather data unavailable (lookup failed)."

    daily = data.get("daily")
    if not daily or not daily.get("time"):
        return f"Weather data unavailable (unexpected response: {data})."

    times = daily["time"]

    def series(key):
        return daily.get(key) or [None] * len(times)

    tmax, tmin = series("temperature_2m_max"), series("temperature_2m_min")
    precip, wind = series("precipitation_sum"), series("windspeed_10m_max")

    # Locate today by date string; fall back to the last past day available.
    today_str = today.isoformat()
    idx = times.index(today_str) if today_str in times else len(times) - FORECAST_DAYS - 1
    idx = max(0, min(idx, len(times) - 1))

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
    current = data.get("current") or {}
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
