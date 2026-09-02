"""
The unit a price is quoted in.

"Rs 3100 prataye quintal" reached two of five price answers in production while
fourteen local runs of the same model produced none, so the fault is real but
not reproducible on demand. That rules out an A/B, and it rules out a cases.yaml
entry, which would pass or fail on the roll of the model rather than on the
code. What can be tested is the correction itself, against inputs written by
hand - which is the right level for a guard whose whole job is to be
deterministic.

Half of these check that the guard does NOT fire. That half matters more: the
same corpus shows baarish/barish and six spellings of achha, and a normaliser
that started tidying those would be doing damage in the name of consistency.

Run: python eval/test_romanisation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import output_guards

failures = []


def check(name, got, want):
    ok = got == want
    print(f"  {'pass' if ok else 'FAIL'}   {name}"
          + ("" if ok else f"\n           got  {got!r}\n           want {want!r}"))
    if not ok:
        failures.append(name)


def fixed(text):
    return output_guards.fix_units(text)[0]


def main():
    print("Garbled qualifiers are corrected")
    # The two forms actually observed.
    check("prataye quintal",
          fixed("Gulavati APMC mein modal bhav Rs 3100 prataye quintal raha."),
          "Gulavati APMC mein modal bhav Rs 3100 prati quintal raha.")
    check("two in one answer",
          fixed("Rs 3100 prataye quintal aur Rs 1600 prataye quintal."),
          "Rs 3100 prati quintal aur Rs 1600 prati quintal.")
    # Garblings nobody has seen, which a blacklist could not have covered.
    for bad in ("pratay", "pratye", "pratii", "pratee", "praati", "prtai"):
        check(f"unseen garble {bad}",
              fixed(f"2,585 rupaye {bad} quintal"), "2,585 rupaye prati quintal")
    check("other units too",
          fixed("100 kg prataye hectare aur 40 kg pratay acre"),
          "100 kg prati hectare aur 40 kg prati acre")
    check("case is preserved on the unit",
          fixed("Rs 3100 Prataye Quintal"), "Rs 3100 prati Quintal")

    print("\nCorrect text is left exactly as written")
    for good in (
        "2,585 rupaye prati quintal nirdharit kiya gaya hai",
        "Rs 2,585 per quintal at a procurement centre",
        "pratyek quintal ke liye",
        "ek quintal se kam",
        "do quintal gehu",
        "aadha quintal",
        "har hectare mein 100 kg",
        "about 2 acres of land",
    ):
        check(f"untouched: {good[:34]}", fixed(good), good)

    print("\nOrdinary romanisation variation is not standardised")
    # Both readable, both used by farmers, neither is wrong.
    for spelling in (
        "kal baarish hogi", "kal barish hogi",
        "jankari ke liye", "jaankari ke liye",
        "achha rahega", "accha rahega",
        "prabandh karein", "prapt karein", "prayog karein",
    ):
        check(f"untouched: {spelling}", fixed(spelling), spelling)

    print("\nThe guard reports whether it fired")
    check("fired", output_guards.fix_units("Rs 10 prataye quintal")[1], True)
    check("did not fire", output_guards.fix_units("Rs 10 prati quintal")[1], False)

    print("\nIt runs inside scrub without disturbing the figure checks")
    # kb absent and msp present: no stripping should happen, only the spelling.
    out, removed = output_guards.scrub(
        "Gehu ka samarthan mulya 2,585 rupaye prataye quintal hai.",
        {"msp": "Minimum Support Price for Wheat in 2026-27: Rs 2,585 per quintal."})
    check("spelling fixed", "prati quintal" in out, True)
    check("figure kept", "2,585" in out, True)
    check("not reported as a removal", removed, False)

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
