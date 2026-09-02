"""
A farmer's location must not be coarsened by mentioning their own state.

The case this reproduces reached a real farmer. They are in Kharagpur, and the
system had been answering from it for three days - weather, soil type, sowing
dates, and a mandi price from Medinipur(West) APMC. Then they asked "rice
varieity in west bengal". Their own state geocoded perfectly well, and because
COALESCE skips only NULL and knows nothing of specificity, the state's centroid
was written over their farm: 83 km away, near Bankura. Three hours later the
same question about potato prices could no longer name a mandi, and asked them
which one they meant.

The visible symptom was the question. The silent one was worse - weather and
soil are sampled at those coordinates, so both had quietly moved.

No model calls. Geocoding is stubbed, so this neither hits Nominatim nor
depends on what it returns today.

Run: python eval/test_profile_location.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import profile_store
from Address_Convertor import precision

USER = "+919999000002"          # reserved for this test, removed afterwards
failures = []

# As Nominatim actually returns them; see eval notes in Address_Convertor.
KHARAGPUR = dict(location_text="Kharagpur", latitude=22.34309, longitude=87.3012875,
                 location_kind="city", state="West Bengal", district="Paschim Medinipur")
WEST_BENGAL = dict(location_text="West Bengal", latitude=22.9964948, longitude=87.6855882,
                   location_kind="state", state="West Bengal")
BARABANKI = dict(location_text="Barabanki", latitude=26.9, longitude=81.2,
                 location_kind="state_district", state="Uttar Pradesh",
                 district="Barabanki")


def check(name, got, want):
    ok = got == want
    print(f"  {'pass' if ok else 'FAIL'}   {name}"
          + ("" if ok else f"\n           got  {got!r}\n           want {want!r}"))
    if not ok:
        failures.append(name)


def cleanup():
    with db.connection() as conn:
        conn.execute("DELETE FROM farmers WHERE user_id = %s", (USER,))


def profile():
    return profile_store.get_profile(USER) or {}


def main():
    if not db.init():
        print("Database unavailable; cannot run")
        return 1
    cleanup()
    try:
        print("Precision ranking")
        check("village beats city", precision("village") > precision("city"), True)
        check("city beats district", precision("city") > precision("state_district"), True)
        check("district beats state", precision("state_district") > precision("state"), True)
        check("unknown type has no rank", precision("banana"), None)

        print("\nThe farmer's own case")
        profile_store.remember(USER, **KHARAGPUR)
        p = profile()
        check("Kharagpur stored", p["location_text"], "Kharagpur")
        check("district recorded", p["district"], "Paschim Medinipur")

        profile_store.remember(USER, **WEST_BENGAL)      # "rice variety in west bengal"
        p = profile()
        check("state does NOT replace the city", p["location_text"], "Kharagpur")
        check("coordinates stay on the farm", round(p["latitude"], 4), 22.3431)
        check("longitude stays too", round(p["longitude"], 4), 87.3013)
        check("district survives", p["district"], "Paschim Medinipur")
        check("state still recorded", p["state"], "West Bengal")

        print("\nA finer location still replaces a coarser one")
        cleanup()
        profile_store.remember(USER, **WEST_BENGAL)
        profile_store.remember(USER, **KHARAGPUR)
        p = profile()
        check("city replaces state", p["location_text"], "Kharagpur")
        check("coordinates moved to the city", round(p["latitude"], 4), 22.3431)

        print("\nAn equally specific location replaces it (a farmer may move)")
        cleanup()
        profile_store.remember(USER, **BARABANKI)
        profile_store.remember(USER, location_text="Lucknow", latitude=26.85,
                               longitude=80.95, location_kind="city",
                               state="Uttar Pradesh", district="Lucknow")
        p = profile()
        check("Lucknow replaces Barabanki", p["location_text"], "Lucknow")
        check("its district replaces too", p["district"], "Lucknow")

        print("\nSilence still never erases anything")
        cleanup()
        profile_store.remember(USER, **KHARAGPUR)
        profile_store.remember(USER, crop="wheat")
        p = profile()
        check("location kept when none mentioned", p["location_text"], "Kharagpur")
        check("crop still recorded", "wheat" in (p.get("crops") or []), True)

        print("\nA name without coordinates does not move the farm")
        # Geocoding failed: writing the name alone is how text and coordinates
        # came to disagree, pointing at two different places at once.
        profile_store.remember(USER, location_text="Some Unresolvable Place",
                               location_kind="village")
        p = profile()
        check("name ignored without coordinates", p["location_text"], "Kharagpur")
        check("coordinates untouched", round(p["latitude"], 4), 22.3431)

        print("\nAn unfamiliar place type is still stored, not rejected")
        cleanup()
        profile_store.remember(USER, location_text="Somewhere", latitude=25.0,
                               longitude=82.0, location_kind="dairy_farm")
        check("stored despite unknown kind", profile()["location_text"], "Somewhere")
    finally:
        cleanup()
        db.close()

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
