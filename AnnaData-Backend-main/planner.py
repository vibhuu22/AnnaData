"""
Deciding which tools a question actually needs.

Previously every tool ran whenever coordinates were known, so a question about
leaf spots fetched mandi prices for the whole state - which on a bad day meant
waiting ninety seconds for a dead API to answer a question that never wanted
prices. Two costs, both real: latency, and a prompt stuffed with data the model
has to ignore, which is itself a source of confused answers.

Everything here is plain data and plain functions. No model call is made to
decide any of it: the intent already arrives from the extraction step that runs
regardless, so tool selection is free.
"""

# Which tools each kind of question can actually use.
TOOLS_FOR_INTENT = {
    "disease_pest":         {"weather"},           # humidity and rain drive disease pressure
    "sowing_planting":      {"weather", "soil"},
    "fertiliser_nutrition": {"soil", "weather"},
    "irrigation_water":     {"weather"},
    "weather_query":        {"weather"},
    "market_price":         {"mandi"},
    "scheme_subsidy":       {"kb"},
    "storage_postharvest":  {"kb"},
    "general":              set(),
}

# Slots without which a tool cannot run at all.
TOOL_REQUIREMENTS = {
    "soil":    {"coords"},
    "weather": {"coords"},
    "mandi":   {"state"},
    "kb":      set(),
}

# What the farmer must tell us before the answer can be specific. Used to ask
# for one precise missing thing instead of a generic "where are you?".
REQUIRED_SLOTS = {
    "disease_pest":         ("crop",),
    "sowing_planting":      ("crop", "location"),
    "fertiliser_nutrition": ("crop", "location"),
    "irrigation_water":     ("crop",),
    "weather_query":        ("location",),
    "market_price":         ("crop", "state"),
    "scheme_subsidy":       (),
    "storage_postharvest":  (),
    "general":              (),
}

VALID_INTENTS = set(TOOLS_FOR_INTENT)


def normalise_intent(intent: str | None) -> str:
    if not intent:
        return "general"
    intent = intent.strip().lower().replace(" ", "_").replace("-", "_")
    return intent if intent in VALID_INTENTS else "general"


def plan_tools(
    intent: str,
    *,
    has_coords: bool,
    state: str | None,
    kb_available: bool,
) -> set[str]:
    """Tools worth running for this question, given what is actually known."""
    intent = normalise_intent(intent)
    available = {
        "coords": has_coords,
        "state": bool(state),
    }

    chosen = set()
    for tool in TOOLS_FOR_INTENT[intent]:
        if tool == "kb" and not kb_available:
            continue
        if all(available.get(req, False) for req in TOOL_REQUIREMENTS[tool]):
            chosen.add(tool)
    return chosen


def missing_slots(intent: str, *, crop: str | None, location: str | None,
                  state: str | None) -> list[str]:
    """Which required details this question is still missing, most useful first."""
    have = {"crop": bool(crop), "location": bool(location), "state": bool(state)}
    return [slot for slot in REQUIRED_SLOTS[normalise_intent(intent)] if not have.get(slot)]
