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
    # "doses" is the registered pesticide table. It is what turns a chemical
    # recommendation from something the model recalled into something the
    # registration authority actually approved.
    "disease_pest":         {"weather", "doses"},  # humidity and rain drive disease pressure
    "sowing_planting":      {"weather", "soil"},
    "fertiliser_nutrition": {"soil", "weather"},
    "irrigation_water":     {"weather"},
    "weather_query":        {"weather"},
    # MSP alongside the live rate, not instead of it: the guaranteed floor is
    # stored locally and stays correct for the marketing year, so a price
    # question is still answerable when the live service is down.
    "market_price":         {"mandi", "msp"},
    "scheme_subsidy":       {"kb"},
    "storage_postharvest":  {"kb"},
    "general":              set(),
}

# Slots without which a tool cannot run at all.
TOOL_REQUIREMENTS = {
    "doses":   {"crop"},        # a dose is meaningless without knowing the crop
    "soil":    {"coords"},
    "weather": {"coords"},
    "mandi":   {"state"},
    "msp":     {"crop"},        # the support price is declared per commodity
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

# A message's kind decides how to respond at all, before its topic decides what
# to look up. Treating every message as a request for advice is what made the
# assistant lecture farmers who were simply telling it something.
VALID_MESSAGE_TYPES = {"question", "statement", "meta", "correction", "smalltalk"}


def normalise_message_type(value: str | None) -> str:
    if not value:
        return "question"
    value = value.strip().lower()
    return value if value in VALID_MESSAGE_TYPES else "question"


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
    crop: str | None = None,
) -> set[str]:
    """Tools worth running for this question, given what is actually known."""
    intent = normalise_intent(intent)
    available = {
        "coords": has_coords,
        "state": bool(state),
        "crop": bool(crop),
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


# --- Greeting ---------------------------------------------------------------
#
# A short message with no question in it is one of three things, and they need
# genuinely different replies. The old code read only the profile, which
# separates a stranger from a returning farmer and separates neither of them
# from someone four minutes into a live conversation - so a farmer who wrote
# "kuch nahi karo" was answered with "It is good to hear from you again. How
# are your wheat fields?".
#
# This lives here rather than in Agent.py for the reason everything else here
# does: it is a routing decision made from facts already in hand, so it costs
# no model call and can be checked without one.

GREETING_MODES = ("continuation", "returning", "first_contact")


def profile_facts(profile) -> list:
    """What we already know about this farmer, phrased for a prompt."""
    known = []
    if profile:
        if profile.get("location_text"):
            known.append(f"they farm near {profile['location_text']}")
        if profile.get("crops"):
            known.append(f"they grow {', '.join(profile['crops'])}")
    return known


def greeting_mode(profile, continuing_session: bool = False) -> str:
    """Which of the three a smalltalk message actually is.

      continuation  - mid-conversation. "accha", "shukriya", "kuch nahi karo":
                      the farmer is acknowledging or closing, not arriving. An
                      opening move here is wrong however warmly it is worded,
                      and on SMS it is a billed segment saying nothing.
      returning     - a known farmer starting a fresh conversation. Resume
                      rather than re-introduce.
      first_contact - nobody we know. Say what the service is for.

    Session state wins over the profile: whether we recognise someone says
    nothing about whether we are already talking to them. `continuing_session`
    is false whenever the database is unavailable or the lookup failed, which
    makes the default a greeting - clumsy in the wrong place, but never the
    reason an answer fails to go out.
    """
    if continuing_session:
        return "continuation"
    return "returning" if profile_facts(profile) else "first_contact"
