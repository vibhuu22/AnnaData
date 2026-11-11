"""
Soil readings are fetched once per place, and the report is unchanged by it.

Earth Engine was the slowest call a disease question made (~1.4 s), and the
map it reads never changes, so readings are cached: in memory, then in
Postgres. Here Earth Engine is replaced by a counter, so a test can see
exactly when it was asked. The properties that matter:

  - a second question from the same place does not reach Earth Engine
  - the report names the farmer's own coordinates, not the cached point's
  - a failed or partial lookup is never kept
  - the report text is what it was before caching existed
  - with a database, a reading survives the process forgetting it

Run: python eval/test_soil_cache.py
"""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import soil_cache
import startup
import Soil_Tool

failures = []


def check(name: str, got, want):
    ok = got == want
    print(f"  {'pass' if ok else 'FAIL'}   {name}"
          + ("" if ok else f"\n           got  {got!r}\n           want {want!r}"))
    if not ok:
        failures.append(name)


# Kharagpur's real readings as Earth Engine stores them: texture class 4,
# pH x10, organic carbon /5.
KHARAGPUR = {"texture": 4.0, "ph": 63.0, "soc": 2.0}
EXPECTED = ("Soil Report for (22.346, 87.232):\n"
            "- Soil texture (USDA class): Clay loam\n"
            "- Soil pH (H2O): 6.3 (slightly acidic)\n"
            "- Soil organic carbon: 1.00% (10.0 g/kg, high)\n")

calls = []
behaviour = {"result": (KHARAGPUR, True)}


def fake_fetch(lat, lon):
    calls.append((lat, lon))
    result = behaviour["result"]
    if isinstance(result, Exception):
        raise result
    return dict(result[0]), result[1]


def main() -> int:
    Soil_Tool._fetch_readings = fake_fetch
    startup.init_earth_engine = lambda: True
    real_available = db.is_available
    db.is_available = lambda: False       # memory layer only, to begin with

    print("Memory layer")
    soil_cache.clear_memory()
    text, values = Soil_Tool.soil_reading(22.346, 87.232)
    check("first question reaches Earth Engine", len(calls), 1)
    check("the report is exactly what it was before caching", text, EXPECTED)
    check("the numbers come with it",
          values, {"texture": "Clay loam", "ph": 6.3, "ph_rating": "slightly acidic",
                   "soc_percent": 1.0})

    again = Soil_Tool.soil_reading(22.346, 87.232)
    check("the same place again does not", len(calls), 1)
    check("and answers identically", again, (text, values))

    text2, _ = Soil_Tool.soil_reading(22.3462, 87.2318)
    check("a position 20 m away shares the reading", len(calls), 1)
    check("but the report names the farmer's own coordinates",
          text2.splitlines()[0], "Soil Report for (22.3462, 87.2318):")

    Soil_Tool.soil_reading(22.360, 87.232)
    check("1.5 km away is a different place", len(calls), 2)

    startup.init_earth_engine = lambda: False
    check("a cached place still answers when Earth Engine is down",
          Soil_Tool.soil_reading(22.346, 87.232)[0], EXPECTED)
    check("an uncached one says it is unavailable",
          Soil_Tool.soil_reading(10.0, 10.0),
          ("Soil data unavailable (Earth Engine not configured).", None))
    startup.init_earth_engine = lambda: True

    print("\nFailures are not kept")
    behaviour["result"] = ({"texture": 4.0, "ph": None, "soc": 2.0}, False)
    before = len(calls)
    Soil_Tool.soil_reading(11.0, 11.0)
    Soil_Tool.soil_reading(11.0, 11.0)
    check("a layer that raised: asked again next time", len(calls) - before, 2)

    behaviour["result"] = RuntimeError("Earth Engine timeout")
    before = len(calls)
    check("an Earth Engine error is the lookup-failed notice",
          Soil_Tool.soil_reading(12.0, 12.0), ("Soil data unavailable (lookup failed).", None))
    Soil_Tool.soil_reading(12.0, 12.0)
    check("and is asked again next time", len(calls) - before, 2)

    behaviour["result"] = ({"texture": None, "ph": None, "soc": None}, True)
    before = len(calls)
    check("a point with no soil (water) says so",
          Soil_Tool.soil_reading(13.0, 13.0)[0],
          "Soil data unavailable (no readings at this location).")
    Soil_Tool.soil_reading(13.0, 13.0)
    check("and that answer is kept - it will not change", len(calls) - before, 1)
    behaviour["result"] = (KHARAGPUR, True)

    check("another dataset version misses",
          soil_cache.get(22.346, 87.232, "OpenLandMap/v03"), None)

    print("\nPostgres layer")
    db.is_available = real_available
    db.init()
    if not db.is_available():
        print("  skip   no database configured")
    else:
        source = f"test-{uuid.uuid4().hex}"
        try:
            soil_cache.put(1.234, 5.678, source, KHARAGPUR)
            soil_cache.clear_memory()
            check("a reading survives the process forgetting it",
                  soil_cache.get(1.234, 5.678, source), KHARAGPUR)
            soil_cache.put(1.234, 5.678, source, {"texture": 1.0})
            soil_cache.clear_memory()
            check("a second write does not replace the first",
                  soil_cache.get(1.234, 5.678, source), KHARAGPUR)
        finally:
            with db.connection() as conn:
                conn.execute("DELETE FROM soil_cache WHERE source = %s", (source,))
            db.close()

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
