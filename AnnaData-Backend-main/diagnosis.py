"""
A short, ranked list of what is most likely wrong, with the reasons for each.

Before this, a disease question produced one name or "the picture is not
enough", and the evidence that separates causes - a week of blast weather, an
alkaline soil that starves rice of zinc, the farmer saying the leaves are
yellowing rather than spotted - never met in one place. Each was handed to the
answer prompt separately, if at all.

Everything here is plain arithmetic over evidence already gathered. It costs no
model call and the same evidence always gives the same order, so it can be
tested and shown to an agronomist.

What it is allowed to decide, and what it is not:

- It ranks. Weights are small integers, summed: the photograph's own reading
  by its confidence, the labelled bank's verdict, the farmer's words, the
  weather risk and the soil.
- `settled` is NOT decided by the ranking. A cause is settled only on the
  evidence that already identified one before this module existed: the bank
  confirming the photograph, a confident photograph the bank did not dispute,
  or the farmer naming it. Weather and soil can push a cause up or down the
  list; they can never make it settled. A humid week is a reason to look for
  blast, not proof of it.
- It never touches doses. Which chemicals may be named is still decided by the
  register match and the existing rules in the answer prompt.
"""
UNKNOWN = "unknown"
MAX_CANDIDATES = 3

PHOTO_WEIGHT = {"high": 3, "medium": 2, "low": 1}
BANK_CONFIRMED, BANK_LISTED = 3, 1
FARMER_NAMED = 2
RISK_WEIGHT = {"high": 2, "moderate": 1}
RISK_AGAINST = -1
SOIL_WEIGHT = 1


def _known(value) -> str | None:
    if not value:
        return None
    v = str(value).strip()
    return None if not v or v.lower() == UNKNOWN else v


def _same(a: str, b: str) -> bool:
    """One disease under two spellings: "blast" and "leaf blast"."""
    a, b = a.strip().lower(), b.strip().lower()
    return bool(a) and bool(b) and (a in b or b in a)


class _Board:
    def __init__(self):
        self.items: list[dict] = []

    def find(self, name: str) -> dict | None:
        return next((c for c in self.items if _same(c["name"], name)), None)

    def add(self, name: str, kind: str, weight: int, reason: str, *, create=True):
        c = self.find(name)
        if c is None:
            if not create:
                return None
            c = {"name": name, "kind": kind, "for": [], "against": [], "weight": 0}
            self.items.append(c)
        c["weight"] += weight
        (c["for"] if weight >= 0 else c["against"]).append(reason)
        return c


def differential(crop: str | None, farmer_pest: str | None, symptoms: str | None,
                 vision: dict | None, risk: list[dict], lookalikes: list[dict]) -> dict:
    """Ranked candidates, at most three, and whether one is settled.

    `vision` is the photograph's reading AFTER the agent has weighed it against
    the labelled bank, so a disputed reading arrives with pest "unknown".
    """
    board = _Board()
    vision = vision or {}
    corr = vision.get("corroboration") or {}
    verdict = corr.get("verdict")
    seen = _known(vision.get("pest"))
    confidence = vision.get("confidence", "low")

    if seen:
        board.add(seen, "disease", PHOTO_WEIGHT.get(confidence, 1),
                  f"the photo looks like it ({confidence} confidence)")
    if verdict == "confirmed" and _known(corr.get("disease")):
        board.add(corr["disease"], "disease", BANK_CONFIRMED,
                  "labelled photos of this crop with the same symptoms are all this disease")
    elif verdict == "disputed":
        for alt in dict.fromkeys(a for a in corr.get("alternatives") or [] if _known(a)):
            if alt.lower() == "healthy":
                continue
            board.add(alt, "disease", BANK_LISTED,
                      "labelled photos with these symptoms include it")

    named = _known(farmer_pest)
    if named:
        board.add(named, "disease", FARMER_NAMED, "the farmer named it")

    for r in risk:
        level = r.get("level")
        if level == "high":
            board.add(r["disease"], "disease", RISK_WEIGHT["high"], f"weather: {r['reason']}")
        elif level == "moderate":
            # A moderate risk is a reason to rank something already suspected
            # higher, not to introduce a disease nobody saw or named.
            board.add(r["disease"], "disease", RISK_WEIGHT["moderate"],
                      f"weather: {r['reason']}", create=False)
        elif level == "low" and r.get("reason"):
            board.add(r["disease"], "disease", RISK_AGAINST,
                      f"weather: {r['reason']}", create=False)

    for lk in lookalikes:
        board.add(lk["name"], lk["kind"], SOIL_WEIGHT, f"soil: {lk['reason']}")

    settled, basis = None, None
    if verdict == "confirmed" and (seen or _known(corr.get("disease"))):
        settled, basis = seen or corr["disease"], "photo+bank"
    elif seen and confidence in ("high", "medium") and verdict != "disputed":
        settled, basis = seen, "photo"
    elif named:
        settled, basis = named, "farmer"

    ranked = sorted(board.items, key=lambda c: -c["weight"])
    top = ranked[:MAX_CANDIDATES]
    if settled and not any(_same(c["name"], settled) for c in top):
        keep = board.find(settled)
        if keep:
            top = top[:MAX_CANDIDATES - 1] + [keep]

    return {"candidates": top, "settled": settled, "basis": basis,
            "symptoms": _known(symptoms),
            "risk": [{k: r.get(k) for k in ("disease", "level", "reason", "forecast")}
                     for r in risk]}


BASIS_WORDS = {
    "photo+bank": "from the photo, confirmed against labelled photos",
    "photo": "from the photo",
    "farmer": "as the farmer named it",
}


def _weather_check(d: dict) -> str:
    """What the weather says about this crop's diseases, listed or not.

    Without it, a week that plainly did NOT favour late blight never reached
    the answer, because a low risk adds no candidate - and the model, left to
    itself, said "this looks like late blight" to a farmer describing black
    leaves in dry weather. Evidence against a disease is evidence too.
    """
    listed = [c["name"] for c in d.get("candidates") or []]
    notes = [f"{r['disease']} {r['level']} ({r['reason']})"
             for r in d.get("risk") or []
             if r.get("level") in ("high", "moderate", "low")
             and not any(_same(r["disease"], n) for n in listed)]
    if not notes:
        return ""
    return ("WEATHER CHECK (whether recent weather favoured this crop's diseases; "
            "not a diagnosis on its own): " + "; ".join(notes))


def format_differential(d: dict) -> str:
    """The LIKELY CAUSES section of the advisory prompt."""
    if not d:
        return ""
    check = _weather_check(d)
    if not d.get("candidates"):
        return check
    lines = ["Ranked in code from the photo, the farmer's words, the weather of "
             "the last days and the soil. Weather and soil only rank; they never "
             "confirm a cause."]
    for i, c in enumerate(d["candidates"], 1):
        line = f"{i}. {c['name']} ({c['kind']})"
        if c["for"]:
            line += " - for: " + "; ".join(c["for"])
        if c["against"]:
            line += " - against: " + "; ".join(c["against"])
        lines.append(line)
    if d.get("settled"):
        lines.append(f"IDENTIFIED: {d['settled']} ({BASIS_WORDS[d['basis']]}).")
    else:
        lines.append("NOT SETTLED: nothing here identifies one cause. Name the top "
                     "one or two as possibilities, give measures that are safe "
                     "whichever it is, and ask the one question that would tell "
                     "the top two apart.")
    if check:
        lines.append(check)
    return "\n      ".join(lines)
