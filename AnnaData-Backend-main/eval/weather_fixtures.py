"""
Synthetic weather series for the disease tests, shaped like weather_tool's.

A day is described by its figures, and its 24 hours are generated from them:
`humid_hours` hours at `rh_high`, the rest at `rh_low`; temperature at tmin
for the six hours before dawn and at tmax for the rest. Coarse, but every
hour is known, so a test can say exactly how many hours meet a threshold.
"""
from datetime import date, timedelta

TODAY = date(2026, 11, 11)


def day(tmin=14.0, tmax=22.0, rh_mean=85, rh_max=96, rain=0.0,
        humid_hours=20, rh_high=95, rh_low=70):
    return {"tmin": tmin, "tmax": tmax, "rh_mean": rh_mean, "rh_max": rh_max,
            "rain": rain, "humid_hours": humid_hours, "rh_high": rh_high, "rh_low": rh_low}


def series(past: list[dict], ahead: list[dict], today: date = TODAY,
           hourly: bool = True, daily_rh: bool = True) -> dict:
    """`past` ends yesterday; `ahead` starts today."""
    days = past + ahead
    start = today - timedelta(days=len(past))
    dates = [(start + timedelta(days=i)).isoformat() for i in range(len(days))]

    hours, temps, rhs = [], [], []
    for d, figures in zip(dates, days):
        for h in range(24):
            hours.append(f"{d}T{h:02d}:00")
            temps.append(figures["tmin"] if h < 6 else figures["tmax"])
            rhs.append(figures["rh_high"] if h < figures["humid_hours"] else figures["rh_low"])

    s = {
        "lat": 22.3, "lon": 87.3, "dates": dates,
        "tmin": [d["tmin"] for d in days], "tmax": [d["tmax"] for d in days],
        "precip": [d["rain"] for d in days], "wind": [5.0] * len(days),
        "rh_mean": [d["rh_mean"] if daily_rh else None for d in days],
        "rh_max": [d["rh_max"] if daily_rh else None for d in days],
        "hours": hours if hourly else [],
        "temp_hourly": temps if hourly else [],
        "rh_hourly": rhs if hourly else [],
        "current": {}, "today_index": len(past),
    }
    return s
