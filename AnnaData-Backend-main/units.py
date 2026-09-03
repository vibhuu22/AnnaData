"""
Land area, converted in code rather than left to the model.

Every dose in the CIB&RC register is a rate - "500 ml in 750 litres of water
per hectare". A farmer standing in a shop cannot buy a rate. Converting the
rate into a quantity needs the size of their field, and the size of their field
arrives in whatever unit they think in, which is almost never hectares.

THE PROBLEM THIS FILE EXISTS FOR. A bigha is not a unit. It is a different area
in nearly every state that uses one:

    West Bengal      0.3306 acre        Uttar Pradesh (pucca)  0.625 acre
    Assam            0.3306 acre        Uttar Pradesh (kaccha) 0.2083 acre
    Bihar            0.6250 acre        Rajasthan (pucca)      0.625 acre
    Madhya Pradesh   0.2755 acre        Gujarat                0.400 acre
    Punjab           0.2500 acre        Himachal Pradesh       0.200 acre
    Uttarakhand      0.1562 acre        Haryana                0.250 acre

So "2 bigha" is between 0.31 and 1.25 acres depending on where the farmer is
standing - a factor of four. Asking a language model to resolve that produces a
confident number with no basis, and a four-fold error in a pesticide quantity is
the exact failure this system exists to avoid. Hence: convert here, from a table,
using the farmer's state, and REFUSE to convert when the state is unknown rather
than picking the most common value.

These figures are the ones in common revenue use, and they are still approximate:
bigha varies by district and sometimes by village, and several states have both a
pucca and a kaccha bigha. The value below is the one a farmer in that state is
most likely to mean. Where that guess matters - which is any dose calculation -
`convert` returns the assumption alongside the number so the caller can say it
out loud instead of burying it.
"""
from __future__ import annotations

# The two conversions that are exact by definition.
HECTARES_PER_ACRE = 0.40468564224
SQFT_PER_ACRE = 43560.0


# Units that mean the same thing everywhere, as hectares.
FIXED_UNITS: dict[str, float] = {
    "hectare": 1.0,
    "acre": HECTARES_PER_ACRE,
    # Maharashtra and Karnataka. 1 guntha = 1089 sq ft, and 40 guntha = 1 acre.
    "guntha": HECTARES_PER_ACRE / 40,
    # Tamil Nadu and Kerala. 1 cent = 1/100 acre, exactly.
    "cent": HECTARES_PER_ACRE / 100,
    # Punjab, Haryana, Jammu. 8 kanal = 1 acre.
    "kanal": HECTARES_PER_ACRE / 8,
    # 20 marla = 1 kanal.
    "marla": HECTARES_PER_ACRE / 160,
    # Tamil Nadu. 1 ground = 2400 sq ft.
    "ground": 2400 / SQFT_PER_ACRE * HECTARES_PER_ACRE,
    "square metre": 0.0001,
    "square foot": 1 / SQFT_PER_ACRE * HECTARES_PER_ACRE,
}


# A bigha, per state, in acres. Keys are lowercase state names as the geocoder
# returns them; see `_STATE_ALIASES` for the spellings actually seen in the wild.
BIGHA_ACRES: dict[str, float] = {
    "west bengal": 0.3306,
    "assam": 0.3306,
    "tripura": 0.3306,
    "bihar": 0.6250,
    "jharkhand": 0.6248,
    "uttar pradesh": 0.6250,
    "uttarakhand": 0.1562,
    "rajasthan": 0.6250,
    "madhya pradesh": 0.2755,
    "gujarat": 0.4000,
    "punjab": 0.2500,
    "haryana": 0.2500,
    "himachal pradesh": 0.2000,
}

_STATE_ALIASES = {
    "orissa": "odisha",
    "uttaranchal": "uttarakhand",
    "pondicherry": "puducherry",
    "nct of delhi": "delhi",
}


# What a farmer wrote, mapped to the unit key above. Plurals and the common
# romanisations, because this arrives as free text from a form or a question.
UNIT_WORDS: dict[str, str] = {
    "ha": "hectare", "hectare": "hectare", "hectares": "hectare",
    "hect": "hectare", "hektar": "hectare",
    "ac": "acre", "acre": "acre", "acres": "acre", "eker": "acre",
    "ekad": "acre", "eakad": "acre",
    "bigha": "bigha", "bighas": "bigha", "biga": "bigha", "beegha": "bigha",
    "vigha": "bigha",
    "guntha": "guntha", "gunta": "guntha", "gunthas": "guntha",
    "cent": "cent", "cents": "cent",
    "kanal": "kanal", "kanals": "kanal", "canal": "kanal",
    "marla": "marla", "marlas": "marla",
    "ground": "ground", "grounds": "ground",
    "sqm": "square metre", "m2": "square metre", "square metre": "square metre",
    "sqft": "square foot", "square foot": "square foot",
}


class AreaResult:
    """A converted area, and what had to be assumed to get there.

    `note` is not decoration. When a bigha was involved, the number depends on a
    state-level convention that may not match this particular village, and the
    answer should say so rather than presenting a derived quantity as a fact.
    """

    __slots__ = ("hectares", "unit", "said", "note")

    def __init__(self, hectares: float, unit: str, said: float, note: str | None = None):
        self.hectares = hectares
        self.unit = unit
        self.said = said
        self.note = note

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"AreaResult({self.hectares:.4f} ha from {self.said} {self.unit})"


def normalise_unit(raw: str | None) -> str | None:
    """The canonical unit name for whatever the farmer wrote, or None."""
    if not raw:
        return None
    key = " ".join(str(raw).strip().lower().replace(".", "").split())
    return UNIT_WORDS.get(key)


def normalise_state(raw: str | None) -> str | None:
    if not raw:
        return None
    key = " ".join(str(raw).strip().lower().split())
    return _STATE_ALIASES.get(key, key)


def convert(value: float | None, unit: str | None, state: str | None = None) -> AreaResult | None:
    """Area in hectares, or None when it cannot be known.

    Returning None is a real answer here. A bigha with no state attached is not
    a quantity, and inventing one would put a number into a dose calculation
    that nothing supports.
    """
    if value is None:
        return None
    try:
        said = float(value)
    except (TypeError, ValueError):
        return None
    if said <= 0:
        return None

    canonical = normalise_unit(unit)
    if canonical is None:
        return None

    if canonical in FIXED_UNITS:
        return AreaResult(said * FIXED_UNITS[canonical], canonical, said)

    if canonical == "bigha":
        key = normalise_state(state)
        acres = BIGHA_ACRES.get(key) if key else None
        if acres is None:
            # Deliberately not a default. See the module docstring.
            return None
        return AreaResult(
            said * acres * HECTARES_PER_ACRE,
            "bigha",
            said,
            note=(f"a bigha in {state} is taken as {acres:g} acre; "
                  "it varies between districts"),
        )

    return None


def to_unit(hectares: float | None, unit: str | None, state: str | None = None) -> float | None:
    """Hectares back into the unit the farmer thinks in."""
    if hectares is None:
        return None
    canonical = normalise_unit(unit)
    if canonical is None:
        return None
    if canonical in FIXED_UNITS:
        return hectares / FIXED_UNITS[canonical]
    if canonical == "bigha":
        acres = BIGHA_ACRES.get(normalise_state(state) or "")
        if acres is None:
            return None
        return hectares / (acres * HECTARES_PER_ACRE)
    return None


def describe(hectares: float | None, unit: str | None = None, state: str | None = None) -> str | None:
    """A short human phrase for an area, in the farmer's own unit where possible.

    Always carries hectares as well, because that is the unit every dose in the
    register is quoted in, and a farmer comparing the two should be able to.
    """
    if hectares is None or hectares <= 0:
        return None

    own = to_unit(hectares, unit, state)
    if own is not None and normalise_unit(unit) != "hectare":
        return f"{_trim(own)} {normalise_unit(unit)} ({_trim(hectares)} ha)"
    return f"{_trim(hectares)} ha"


def _trim(number: float) -> str:
    """Two decimals at most, and no trailing zeros pretending to be precision."""
    text = f"{number:.2f}".rstrip("0").rstrip(".")
    return text or "0"
