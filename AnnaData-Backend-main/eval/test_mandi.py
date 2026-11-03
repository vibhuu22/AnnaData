"""
Which rows count as the farmer's crop, in the farmer's state.

Three faults sent a farmer someone else's price, and none of them could be
expressed in cases.yaml: they are selection logic, not language, and the model
never sees the rows that were wrongly included. They are checked here against
fixtures taken from a real day's publication, so the test costs nothing and
does not depend on what is trading today.

  1. filters[state] matches on tokens. "Uttar Pradesh" returned Andhra Pradesh
     and Himachal Pradesh too, because all three contain "Pradesh".
  2. A commodity filter that matched nothing fell back to the whole state, so
     asking for wheat in September returned cauliflower and okra.
  3. The filter matches the published label exactly, so "okra" never matched
     "Bhindi(Ladies Finger)" and a crop that WAS trading looked absent.

Run: python eval/test_mandi.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import Mandi_Price_Tool as mandi

failures = []


def check(name: str, got, want):
    ok = got == want
    print(f"  {'pass' if ok else 'FAIL'}   {name}"
          + ("" if ok else f"\n           got  {got!r}\n           want {want!r}"))
    if not ok:
        failures.append(name)


# Labels exactly as data.gov.in publishes them.
LABELS = [
    "Wheat", "Paddy(Common)", "Bhindi(Ladies Finger)", "Cauliflower",
    "Bengal Gram(Gram)(Whole)", "Black Gram(Urd Beans)(Whole)",
    "Green Gram(Moong)(Whole)", "Red gram/Arhar/Tur(whole)", "Green Chilli",
    "Chili Red", "Bitter gourd", "Bottle gourd", "Coconut", "Tender Coconut",
    "Banana", "Banana - Green", "Cucumbar(Kheera)", "Colacasia", "Pumpkin",
]
ROWS = [{"commodity": label} for label in LABELS]


def matched(crop):
    return [r["commodity"] for r in mandi._select(ROWS, crop)]


def main():
    print("State is checked locally, because the upstream filter is a token match")
    up = {"state": "Uttar Pradesh"}
    for other in ("Andhra Pradesh", "Himachal Pradesh", "Arunachal Pradesh"):
        check(f"{other} is not Uttar Pradesh",
              mandi._in_state({"state": other}, "Uttar Pradesh"), False)
    check("Uttar Pradesh is itself", mandi._in_state(up, "Uttar Pradesh"), True)
    check("case and spacing ignored",
          mandi._in_state({"state": " uttar pradesh "}, "Uttar Pradesh"), True)
    check("Keralam is Kerala", mandi._in_state({"state": "Keralam"}, "Kerala"), True)
    check("Orissa is Odisha", mandi._in_state({"state": "Orissa"}, "Odisha"), True)

    print("\nThe crop asked for is found however it is written")
    for crop, want in [
        ("okra", "Bhindi(Ladies Finger)"),
        ("bhindi", "Bhindi(Ladies Finger)"),
        ("dhaan", "Paddy(Common)"),
        ("rice", "Paddy(Common)"),
        ("arhar", "Red gram/Arhar/Tur(whole)"),
        ("tur", "Red gram/Arhar/Tur(whole)"),
        ("kheera", "Cucumbar(Kheera)"),
        ("karela", "Bitter gourd"),
        ("lauki", "Bottle gourd"),
        ("gobhi", "Cauliflower"),
        ("arbi", "Colacasia"),
        ("kaddu", "Pumpkin"),
        ("gehu", "Wheat"),
    ]:
        check(f"{crop} -> {want}", matched(crop), [want])

    print("\nSimilarly-named crops are never confused with each other")
    # These three share the word "Gram" and are three different pulses. This is
    # why the label is not simply split on spaces.
    check("chana is Bengal gram only", matched("chana"), ["Bengal Gram(Gram)(Whole)"])
    check("urad is Black gram only", matched("urad"), ["Black Gram(Urd Beans)(Whole)"])
    check("moong is Green gram only", matched("moong"), ["Green Gram(Moong)(Whole)"])
    check("coconut is not tender coconut", matched("coconut"), ["Coconut"])
    check("banana is not green banana", matched("banana"), ["Banana"])
    # Both chilli entries are chilli, so matching both is right.
    check("mirch is both chillies", sorted(matched("mirch")),
          ["Chili Red", "Green Chilli"])

    print("\nAn absent crop is reported absent, not replaced")
    absent = mandi._select(ROWS, "sugarcane")
    check("sugarcane matches nothing", absent, [])
    text = mandi.no_arrivals("Uttar Pradesh", "wheat")
    check("names the crop", "wheat" in text, True)
    check("names the state", "Uttar Pradesh" in text, True)
    check("forbids substitution", "any other crop" in text, True)
    for other in ("Cauliflower", "Bhindi", "Pumpkin", "Rs"):
        check(f"carries no {other}", other in text, False)
    check("does not guess the reason", "do not assert which" in text, True)

    print("\nThe farmer's own district is preferred over the whole state")
    # Written by the geocoder on the left, by the register on the right. Same
    # place, different language and position for the direction.
    for mine, published, want in [
        ("Paschim Medinipur", "Medinipur(W)", True),
        ("Paschim Medinipur", "Medinipur(E)", False),
        ("Purba Bardhaman", "Bardhaman(E)", True),
        ("Paschim Bardhaman", "Bardhaman(E)", False),
        ("South 24 Parganas", "Sounth 24 Parganas", True),   # the source's typo
        ("Lucknow", "Lucknow", True),
        ("Paschim Medinipur", "Jhargram", False),
    ]:
        check(f"{mine} vs {published}",
              mandi._in_district({"district": published}, mine), want)
    check("no district means no filtering",
          mandi._in_district({"district": "Anywhere"}, None), True)

    ROWS_WB = [
        {"district": "Medinipur(W)", "market": "Ghatal APMC", "commodity": "Potato"},
        {"district": "Darjeeling", "market": "Darjeeling APMC", "commodity": "Potato"},
        {"district": "Coochbehar", "market": "Haldibari APMC", "commodity": "Potato"},
    ]
    local, note = mandi.narrow_to_district(ROWS_WB, "Paschim Medinipur",
                                           "potato", "West Bengal")
    check("only the home district survives", [r["market"] for r in local],
          ["Ghatal APMC"])
    check("and it is labelled as theirs", "own district" in note, True)

    # A farmer whose district reported nothing must be told so, not handed
    # another district's rate and asked which mandi they meant.
    away, note = mandi.narrow_to_district(ROWS_WB, "Jhargram", "potato", "West Bengal")
    check("state rows kept as a fallback", len(away), 3)
    check("absence stated first", "No potato arrivals were reported" in note, True)
    check("not passed off as their rate", "NOT their local rate" in note, True)
    check("does not ask what it already knows",
          "do not ask the farmer which mandi" in note, True)

    nowhere, note = mandi.narrow_to_district(ROWS_WB, None, "potato", "West Bengal")
    check("unknown district changes nothing", len(nowhere), 3)
    check("and says nothing", note, "")

    # --- which cached entry answers the question ---------------------------
    #
    # The ordering was exact-crop first, recency second. Specificity beat
    # freshness however wide the gap, nothing expires these rows, and so a
    # crop-specific entry shadowed every later state snapshot for that crop.
    # A refresh job could run daily for weeks while farmers were quoted
    # two-month-old prices, which is exactly what happened: live fetching
    # stopped on 2 September and the cache kept answering as though it had not.
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    old = now - timedelta(days=62)

    def entry(commodity, when, label):
        return (label, [{"commodity": commodity or "any"}], when, commodity)

    fresh_state = entry("", now, "state snapshot today")
    stale_crop = entry("potato", old, "potato, 62 days old")
    fresh_crop = entry("potato", now, "potato today")
    older_state = entry("", old, "state snapshot, 62 days old")

    def picked(rows, crop):
        chosen = mandi._pick_cached_row(rows, crop)
        return chosen[0] if chosen else None

    check("fresh state snapshot beats a stale crop entry",
          picked([stale_crop, fresh_state], "potato"), "state snapshot today")
    check("order of the rows does not matter",
          picked([fresh_state, stale_crop], "potato"), "state snapshot today")
    # Same day is where specificity was always the right instinct, and it is
    # kept: ranking is by date, so a same-day crop entry still wins.
    check("same day, the crop entry still wins",
          picked([fresh_state, fresh_crop], "potato"), "potato today")
    check("a stale crop entry still answers when nothing newer exists",
          picked([stale_crop, older_state], "potato"), "potato, 62 days old")
    check("no crop named, the state snapshot answers",
          picked([fresh_state], ""), "state snapshot today")
    check("nothing cached", picked([], "potato"), None)
    # A different crop's entry must never answer. The WHERE clause excludes it,
    # but the ranking must not promote it if one ever reaches here.
    check("another crop's entry does not outrank the state snapshot",
          picked([entry("wheat", now, "wheat today"), fresh_state], "potato"),
          "state snapshot today")

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
