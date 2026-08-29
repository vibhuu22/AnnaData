"""
Weather from Open-Meteo (no API key required).

Days are now located by matching the actual date strings the API returns rather
than by fixed negative offsets, which silently reported the wrong day whenever
the response range differed from the request.
"""
import requests
from datetime import date, timedelta

from config import HTTP_TIMEOUT

PAST_DAYS = 30
FORECAST_DAYS = 7


def weather_openmeteo(lat, lon) -> str:
    today = date.today()
    start = today - timedelta(days=PAST_DAYS)
    end = today + timedelta(days=FORECAST_DAYS)

    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                 "weathercode,windspeed_10m_max",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "timezone": "auto",
    }

    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
            timeout=HTTP_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Weather lookup failed for ({lat}, {lon}): {e}")
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

    return (
        f"Weather Report for ({lat}, {lon}):\n"
        f"- Today's temp: {num(tmin, idx)}-{num(tmax, idx)}C, "
        f"Rain: {num(precip, idx)} mm, Wind: {num(wind, idx)} km/h\n"
        f"- Last 10 days avg rainfall: {last_10_avg:.2f} mm/day\n"
        f"- Last 1 month total rainfall: {last_30_sum:.2f} mm\n"
        f"- {len(forecast_lines)}-day Forecast:\n" + "\n".join(forecast_lines)
    )
