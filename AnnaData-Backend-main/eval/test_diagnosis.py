"""
The ranked list of likely causes, and what may and may not settle one.

diagnosis.differential weighs the photograph, the labelled bank, the farmer's
words, the weather risk and the soil into at most three candidates. The order
is arithmetic and the rule for `settled` is fixed, so both are checked here
without a model. The property that matters most: weather and soil can rank a
cause, but they can never make one settled - a humid week is a reason to look
for blast, not proof of it.

Run: python eval/test_diagnosis.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import diagnosis as dg

failures = []


def check(name: str, got, want):
    ok = got == want
    print(f"  {'pass' if ok else 'FAIL'}   {name}"
          + ("" if ok else f"\n           got  {got!r}\n           want {want!r}"))
    if not ok:
        failures.append(name)


def risk(disease, level, reason="5 of the last 7 days were humid"):
    return {"disease": disease, "level": level, "reason": reason, "forecast": False}


def names(d):
    return [c["name"] for c in d["candidates"]]


def main() -> int:
    # The agent sets a disputed reading's pest to "unknown" before this runs.
    disputed = {"pest": "unknown", "confidence": "low",
                "corroboration": {"verdict": "disputed",
                                  "alternatives": ["blast", "brown spot"]}}
    d = dg.differential("rice", None, "brown spots", disputed,
                        [risk("blast", "high")], [])
    check("disputed photo, blast weather: blast ranked first", names(d)[0], "blast")
    check("but not settled - the weather cannot settle it", d["settled"], None)
    check("the weather reason is carried",
          any(r.startswith("weather:") for r in d["candidates"][0]["for"]), True)

    confirmed = {"pest": "blast", "confidence": "high",
                 "corroboration": {"verdict": "confirmed", "disease": "blast"}}
    d = dg.differential("rice", None, None, confirmed, [], [])
    check("bank confirms the photo: settled", (d["settled"], d["basis"]), ("blast", "photo+bank"))

    d = dg.differential("rice", None, None, None, [risk("blast", "high")], [])
    check("weather alone: blast listed", names(d), ["blast"])
    check("weather alone never settles", d["settled"], None)

    d = dg.differential("rice", "stem borer", None, None, [risk("blast", "low")], [])
    check("the farmer named stem borer: settled on their word",
          (d["settled"], d["basis"]), ("stem borer", "farmer"))
    check("a low risk for something nobody suspects adds nothing", names(d), ["stem borer"])

    low_conf = {"pest": "blast", "confidence": "low"}
    d = dg.differential("rice", None, None, low_conf, [], [])
    check("a low-confidence photo alone is not settled", d["settled"], None)

    medium = {"pest": "brown spot", "confidence": "medium",
              "corroboration": {"verdict": "uncovered"}}
    d = dg.differential("rice", "blast", None, medium, [], [])
    check("a confident photo outranks the farmer's guess for settling",
          (d["settled"], d["basis"]), ("brown spot", "photo"))
    check("and the farmer's guess stays on the list", "blast" in names(d), True)

    d = dg.differential("rice", None, None, None, [risk("sheath blight", "moderate")], [])
    check("a moderate risk never introduces a cause nobody saw or named", names(d), [])

    d = dg.differential("rice", "blast", None, None,
                        [risk("blast", "low", "only 1 of the last 7 days was humid")], [])
    check("a low risk counts against a suspected cause",
          d["candidates"][0]["against"], ["weather: only 1 of the last 7 days was humid"])

    look = [{"name": "iron or zinc shortage", "kind": "deficiency",
             "reason": "soil pH 8.4 is alkaline"}]
    d = dg.differential("rice", None, "yellowing", None, [], look)
    check("a soil lookalike is a candidate of its own kind",
          [(c["name"], c["kind"]) for c in d["candidates"]],
          [("iron or zinc shortage", "deficiency")])

    crowded = {"pest": "unknown", "confidence": "low",
               "corroboration": {"verdict": "disputed",
                                 "alternatives": ["blast", "brown spot", "narrow brown spot",
                                                  "leaf scald"]}}
    d = dg.differential("rice", "stem borer", None, crowded,
                        [risk("blast", "high"), risk("bacterial leaf blight", "high")], look)
    check("never more than three candidates", len(d["candidates"]) <= dg.MAX_CANDIDATES, True)
    check("the settled cause is kept even when crowded out",
          "stem borer" in names(d), True)

    check("'leaf blast' and 'blast' are one candidate",
          names(dg.differential("rice", "blast", None, {"pest": "leaf blast", "confidence": "high"},
                                [], [])), ["leaf blast"])

    print("\nThe prompt section")
    text = dg.format_differential(dg.differential("rice", None, None, None,
                                                  [risk("blast", "high")], []))
    check("unsettled says so", "NOT SETTLED" in text, True)
    text = dg.format_differential(dg.differential("rice", None, None, confirmed, [], []))
    check("settled names the cause and its basis",
          "IDENTIFIED: blast (from the photo, confirmed against labelled photos)" in text, True)
    check("nothing to say writes no section",
          dg.format_differential(dg.differential("rice", None, None, None, [], [])), "")
    text = dg.format_differential(dg.differential(
        "potato", None, "black leaves", None,
        [risk("late blight", "low", "the last days stayed well short of the threshold")], []))
    check("no candidate, but weather against a disease is still reported",
          text.startswith("WEATHER CHECK") and "late blight low" in text, True)
    text = dg.format_differential(dg.differential(
        "rice", None, None, None, [risk("blast", "high"), risk("sheath blight", "low")], []))
    check("a listed cause is not repeated in the weather check",
          "WEATHER CHECK" in text and "blast high" not in text and "sheath blight low" in text, True)
    check("unknown risk is left out of the weather check",
          dg.format_differential(dg.differential(
              "rice", None, None, None, [risk("blast", "unknown", "no data")], [])), "")

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
