"""
Disease risk from the weather, and soil conditions that mimic disease.

disease_risk turns a weather series into "the weather has favoured late
blight" using published rules, and nothing about it needs a model: so it is
checked here against weather constructed hour by hour, where the number of
hours above a humidity is known exactly. The properties that matter:

  - a rule fires on the conditions its source states, and not on others
  - a regional model met outside its own state is reported a level lower
  - missing data is "unknown", never "low"
  - a soil lookalike needs a symptom it could actually cause

Run: python eval/test_disease_risk.py
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import disease_risk as dr
from weather_fixtures import TODAY, day, series

failures = []


def check(name: str, got, want):
    ok = got == want
    print(f"  {'pass' if ok else 'FAIL'}   {name}"
          + ("" if ok else f"\n           got  {got!r}\n           want {want!r}"))
    if not ok:
        failures.append(name)


def level(results, disease):
    r = next((r for r in results if r["disease"] == disease), None)
    return (r["level"], r["forecast"]) if r else None


def reason(results, disease):
    return next(r["reason"] for r in results if r["disease"] == disease)


def main() -> int:
    humid = day(tmin=14, tmax=22, humid_hours=20, rh_high=95)
    dry = day(tmin=14, tmax=22, humid_hours=0, rh_low=60, rh_mean=55, rh_max=65)
    hot = day(tmin=28, tmax=36, humid_hours=0, rh_low=40, rh_mean=40, rh_max=50)

    print("Potato late blight (JHULSACAST)")
    s = series([humid] * 14, [humid] * 7)
    got = dr.assess("potato", s, TODAY, state="West Bengal")
    check("two cool humid weeks in West Bengal: high", level(got, "late blight"), ("high", False))
    check("the reason names the model it came from",
          "JHULSACAST (West Bengal)" in reason(got, "late blight"), True)

    got = dr.assess("potato", s, TODAY, state="Uttar Pradesh")
    check("the same weather outside a validated state is one level lower",
          level(got, "late blight"), ("moderate", False))
    check("and says the model was validated elsewhere",
          "validated for" in reason(got, "late blight"), True)

    got = dr.assess("aloo", series([hot] * 14, [hot] * 7), TODAY, state="West Bengal")
    check("hot dry weeks: low (and 'aloo' is potato)", level(got, "late blight"), ("low", False))

    got = dr.assess("potato", series([dry] * 14, [humid] * 7), TODAY, state="West Bengal")
    check("dry so far, humid week forecast: moderate, from the forecast",
          level(got, "late blight"), ("moderate", True))

    got = dr.assess("potato", series([humid] * 14, [humid] * 7, hourly=False), TODAY,
                    state="West Bengal")
    check("no hourly data: unknown, never low", level(got, "late blight"), ("unknown", False))

    got = dr.assess("potato", None, TODAY, state="West Bengal")
    check("no weather series at all: unknown", level(got, "late blight"), ("unknown", False))

    # 20 humid hours a day reach 105 hours in 7 days; 14 do not (98).
    short = day(tmin=14, tmax=22, humid_hours=14, rh_high=95)
    got = dr.assess("potato", series([short] * 14, [short] * 7), TODAY, state="West Bengal")
    check("98 humid hours in a week is close but short: moderate, not high",
          level(got, "late blight")[0], "moderate")

    print("\nRice and cotton (extension guidance)")
    blast_day = day(tmin=22, tmax=30, rh_mean=88, rh_max=95, rain=1.0)
    got = dr.assess("paddy", series([blast_day] * 10, [blast_day] * 7), TODAY)
    check("a week of humid nights below 26 C: blast high", level(got, "blast"), ("high", False))
    check("the reason counts the days",
          reason(got, "blast").startswith("7 of the last 7 days"), True)

    clear = day(tmin=22, tmax=30, rh_mean=60, rh_max=80, rain=0.0)
    got = dr.assess("rice", series([clear] * 10, [clear] * 7), TODAY)
    check("humidity never above 80%: blast low", level(got, "blast"), ("low", False))
    check("and sheath blight low", level(got, "sheath blight"), ("low", False))

    got = dr.assess("rice", series([clear] * 10, [clear] * 7, daily_rh=False), TODAY)
    check("no daily humidity: blast unknown", level(got, "blast"), ("unknown", False))

    june = date(2026, 6, 15)
    mild = day(tmin=22, tmax=28, rh_mean=85, rh_max=95, rain=3.0)
    got = dr.assess("cotton", series([mild] * 10, [mild] * 7, today=june), june)
    check("grey mildew in June: low, out of season", level(got, "grey mildew"), ("low", False))
    check("with that as the reason", reason(got, "grey mildew"), "out of season for it")

    got = dr.assess("cotton", series([mild] * 10, [mild] * 7), TODAY)
    check("grey mildew weather in November: high", level(got, "grey mildew"), ("high", False))

    check("a crop with no rule returns nothing", dr.assess("wheat", s, TODAY), [])
    check("highest risk first",
          [r["level"] for r in dr.assess("rice", series([blast_day] * 10, [blast_day] * 7), TODAY)][0],
          "high")

    print("\nSoil lookalikes")
    alkaline = {"ph": 8.4, "texture": "Loam"}
    names = lambda found: [f["name"] for f in found]
    check("pH 8.4 and yellowing: iron or zinc shortage",
          names(dr.soil_lookalikes(alkaline, None, "yellowing")), ["iron or zinc shortage"])
    check("pH 8.4 with yellowing AND brown spots: soil not offered",
          names(dr.soil_lookalikes(alkaline, None, "yellowing, brown spots")), [])
    check("pH 8.4 with no symptom described: nothing",
          names(dr.soil_lookalikes(alkaline, None, None)), [])
    check("neutral soil and yellowing: nothing",
          names(dr.soil_lookalikes({"ph": 7.0, "texture": "Loam"}, None, "yellowing")), [])

    wet = day(rain=8.0)
    clay = {"ph": 7.0, "texture": "Clay"}
    check("clay after 80 mm in 10 days and wilting: waterlogging",
          names(dr.soil_lookalikes(clay, series([wet] * 10, [wet] * 2), "wilting", TODAY)),
          ["waterlogging or root rot"])
    check("the same clay after a dry spell: nothing",
          names(dr.soil_lookalikes(clay, series([dry] * 10, [dry] * 2), "wilting", TODAY)), [])
    check("sand, no rain and wilting: water stress",
          names(dr.soil_lookalikes({"ph": 7.0, "texture": "Sand"},
                                   series([dry] * 10, [dry] * 2), "wilting", TODAY)),
          ["water stress"])
    check("acid soil and purple leaves: phosphorus or acid stress",
          names(dr.soil_lookalikes({"ph": 5.0}, None, "purple leaves")),
          ["phosphorus shortage or acid-soil stress"])

    print("\nRules carry their provenance")
    rules = dr.HOURLY_MODELS + dr.DAILY_RULES
    check("every rule names a source", all(r.get("source") for r in rules), True)
    check("every rule is marked unreviewed until signed off",
          all(r.get("reviewed") is False for r in rules), True)

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
