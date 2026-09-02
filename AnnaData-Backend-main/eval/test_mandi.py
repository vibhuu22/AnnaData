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

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
