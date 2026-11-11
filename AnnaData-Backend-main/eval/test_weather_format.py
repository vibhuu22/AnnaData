"""
The weather text the prompt receives, unchanged by the split into a series.

weather_tool used to parse Open-Meteo and write the report in one function. It
now builds a series of numbers first, because disease risk is computed from
humidity and temperature and cannot be read back out of a sentence, and then
writes the report from that series. The report must not change: every answer
that quotes the weather depends on it.

eval/fixtures/weather_openmeteo.json holds a fixed Open-Meteo response and the
text the code wrote for it BEFORE the split, captured by running the old
function against that response. This checks the new code writes the same
bytes, and that the series carries what the risk rules need.

Run: python eval/test_weather_format.py
"""
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import weather_tool as w

failures = []


def check(name: str, got, want):
    ok = got == want
    print(f"  {'pass' if ok else 'FAIL'}   {name}"
          + ("" if ok else f"\n           got  {got!r}\n           want {want!r}"))
    if not ok:
        failures.append(name)


def main() -> int:
    fixture = json.loads(
        (Path(__file__).parent / "fixtures" / "weather_openmeteo.json").read_text(encoding="utf-8"))
    data, expected = fixture["data"], fixture["expected"]

    series = w.series_from_response(data, 22.3, 87.3, date(2026, 11, 11))
    check("a well-formed response becomes a series", isinstance(series, dict), True)
    check("the report is byte for byte what it was before the split",
          w.format_weather(series), expected)
    check("today is located by its date", series["dates"][series["today_index"]], "2026-11-11")
    check("daily humidity is carried for the risk rules",
          series["rh_mean"][:3], data["daily"]["relative_humidity_2m_mean"][:3])
    check("a missing rainfall day stays missing in the series, not zero",
          series["precip"][3], None)

    broken = w.series_from_response({"daily": {}}, 22.3, 87.3, date(2026, 11, 11))
    check("a response without days is the unavailable notice",
          isinstance(broken, str) and broken.startswith("Weather data unavailable"), True)

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
