"""
Whether the weather has favoured a disease, computed in code from published rules.

The answer prompt used to receive the weather as a paragraph and was told not to
mention it on a pest question unless it changed the advice. So the one thing a
plant pathologist looks at first - has it been humid and mild for a week? - was
never actually worked out. A model asked to read "humidity 93%" off a sentence
and compare it to a threshold it half remembers is exactly the inference this
system does not delegate.

So the rules live here as data, each taken from a source that was opened and
read, and each says where it came from. What is computed is deliberately modest:

- Risk ranks possible causes. It never confirms one, and it never unlocks a
  dose. A week of blast weather does not mean the farmer's rice has blast.
- Missing data is "unknown", never "low". A forecast that could not be fetched
  says nothing about the disease.
- Every rule carries `reviewed: False` until someone qualified signs it off.
  The thresholds below are the published ones; the counting windows used for
  the extension-guide rules (how many days of the last seven) are this
  module's reading of guidance that states conditions without a duration, and
  are marked as such in `interpretation`.

Wheat has no rule yet: no Indian source with stated thresholds for the rusts
or powdery mildew was found and read, and a rule without one is left out
rather than written from memory.

Soil "lookalikes" are separate: conditions under which a nutrient shortage or
waterlogging produces the same yellowing or wilting a disease would. They are
offered only when the symptoms are of that kind - soil does not cause spots or
pustules - and they too only rank, never decide.
"""
from datetime import date

# --- Sources ----------------------------------------------------------------

JHULSACAST_WB = (
    "Modified JHULSACAST, West Bengal plains (Potato Journal, ICAR-CPRI): "
    "https://epubs.icar.org.in/index.php/PotatoJ/article/view/50164"
)
JHULSACAST_PB = (
    "JHULSACAST, Punjab (Potato Journal, ICAR-CPRI): "
    "https://epubs.icar.org.in/index.php/PotatoJ/article/view/32182"
)
TNAU_BLAST = ("TNAU Agritech, rice blast: https://agritech.tnau.ac.in/crop_protection/"
              "rice_diseases/another%20methods_rice_1.html")
TNAU_SHEATH = ("TNAU Agritech, rice sheath blight: https://agritech.tnau.ac.in/"
               "crop_protection/rice_diseases/rice_6.html")
TNAU_BLB = ("TNAU Agritech, rice bacterial leaf blight: https://agritech.tnau.ac.in/"
            "crop_protection/rice_diseases/rice_3.html")
TNAU_GREY = ("TNAU Agritech, cotton grey mildew: https://agritech.tnau.ac.in/"
             "crop_protection/cotton_diseases/cotton_d4.html")

CROP_ALIASES = {"paddy": "rice", "dhan": "rice", "aloo": "potato", "kapas": "cotton"}

# --- Hourly models (JHULSACAST) ---------------------------------------------
#
# JHULSACAST counts hours in a moving window: so many hours at or above a
# humidity, so many inside the "congenial" temperature band of 7.2-26.6 C.
# Regional versions differ, and each was validated only where it was built, so
# a version met outside its own state is reported a level lower and says so.

CONGENIAL = (7.2, 26.6)

HOURLY_MODELS = [
    {
        "crop": "potato", "disease": "late blight", "model": "JHULSACAST (West Bengal)",
        "states": {"west bengal"},
        "lead": "within 14 days",
        # Either option satisfies the model.
        "options": [
            # 7-day moving RH >= 90% for >= 105 h with congenial temperature for
            # >= 150 h, prevailing for 7 consecutive days.
            {"window_days": 7, "rh_at_least": 90, "rh_hours": 105,
             "temp_hours": 150, "persist_days": 7, "rain_2day_mm": None},
            # 5-day moving RH >= 90% for >= 65 h with congenial temperature for
            # >= 105 h for 5 consecutive days, and two consecutive days of rain
            # summing to >= 2.5 mm.
            {"window_days": 5, "rh_at_least": 90, "rh_hours": 65,
             "temp_hours": 105, "persist_days": 5, "rain_2day_mm": 2.5},
        ],
        "source": JHULSACAST_WB, "reviewed": False,
        "interpretation": "'prevail for 7 consecutive days' is read as the moving "
                          "window meeting the threshold on each of 7 consecutive days.",
    },
    {
        "crop": "potato", "disease": "late blight", "model": "JHULSACAST (Punjab)",
        "states": {"punjab"},
        "lead": "within 10 days",
        "options": [
            # 7-day moving RH > 85% for >= 90 h with congenial temperature for
            # >= 115 h. ">" is honoured: 85% itself does not count.
            {"window_days": 7, "rh_above": 85, "rh_hours": 90,
             "temp_hours": 115, "persist_days": 1, "rain_2day_mm": None},
        ],
        "source": JHULSACAST_PB, "reviewed": False,
        "interpretation": "No persistence is stated, so one qualifying window is enough.",
    },
]

# --- Daily rules (extension guides) -----------------------------------------
#
# These guides state favourable conditions but not for how long, so a day is
# counted as favourable when it meets them and the count over a week decides
# the level. `day` receives one day's figures: tmin, tmax, tmean, rh_mean,
# rh_max, rain.

COUNT_HIGH, COUNT_MODERATE = 5, 3

DAILY_RULES = [
    {
        "crop": "rice", "disease": "blast",
        "favourable": "humidity reaching 93% or more with nights below 26 C",
        "day": lambda d: d["rh_max"] >= 93 and d["tmin"] < 26,
        "months": None,
        "source": TNAU_BLAST, "reviewed": False,
        "interpretation": "TNAU: RH 93-99%, low night temperature (15-20 C or "
                          "below 26 C), intermittent drizzle. Daily maximum "
                          "humidity and minimum temperature stand in for these.",
    },
    {
        "crop": "rice", "disease": "sheath blight",
        "favourable": "humidity reaching 96% or more with mean temperature of 28-32 C",
        "day": lambda d: d["rh_max"] >= 96 and 28 <= d["tmean"] <= 32,
        "months": None,
        "source": TNAU_SHEATH, "reviewed": False,
        "interpretation": "TNAU: RH 96-100%, temperature 28-32 C, frequent rain. "
                          "The day's mean temperature is used for the band.",
    },
    {
        "crop": "rice", "disease": "bacterial leaf blight",
        "favourable": "mean temperature of 25-30 C with rain or heavy dew",
        "day": lambda d: 25 <= d["tmean"] <= 30 and (d["rain"] >= 2.5 or d["rh_max"] >= 95),
        "months": None,
        "source": TNAU_BLB, "reviewed": False,
        "interpretation": "TNAU: heavy rain, heavy dew, flooding, severe wind and "
                          "25-30 C. Rain is counted from 2.5 mm (the IMD rainy "
                          "day); heavy dew is approximated by humidity reaching 95%.",
    },
    {
        "crop": "cotton", "disease": "grey mildew",
        "favourable": "humid or rainy weather at 20-30 C",
        "day": lambda d: 20 <= d["tmean"] <= 30 and (d["rh_mean"] >= 80 or d["rain"] >= 2.5),
        "months": {10, 11, 12, 1},
        "source": TNAU_GREY, "reviewed": False,
        "interpretation": "TNAU: wet humid conditions, intermittent rain, low "
                          "temperature (20-30 C) during October-January. 'Humid' "
                          "is read as a daily mean humidity of 80% or more.",
    },
]


def normalise_crop(crop: str | None) -> str | None:
    if not crop or crop == "unknown":
        return None
    c = crop.strip().lower()
    return CROP_ALIASES.get(c, c)


def covered(crop: str | None) -> bool:
    """Whether any rule exists for this crop."""
    c = normalise_crop(crop)
    return any(r["crop"] == c for r in HOURLY_MODELS + DAILY_RULES)


# --- Reading the series -----------------------------------------------------

def _days(series: dict) -> list[dict]:
    """One dict per day, with None where a figure is missing."""
    out = []
    for i, day in enumerate(series.get("dates") or []):
        def at(key):
            values = series.get(key) or []
            return values[i] if i < len(values) else None
        tmin, tmax = at("tmin"), at("tmax")
        out.append({
            "date": day, "tmin": tmin, "tmax": tmax,
            "tmean": (tmin + tmax) / 2 if tmin is not None and tmax is not None else None,
            "rh_mean": at("rh_mean"), "rh_max": at("rh_max"),
            "rain": at("precip"),
        })
    return out


def _complete(day: dict, keys=("tmin", "tmax", "rh_mean", "rh_max")) -> bool:
    return all(day.get(k) is not None for k in keys)


def _hourly_by_day(series: dict) -> dict[str, list[tuple]]:
    """{date: [(temperature, humidity), ...]} from the hourly lists."""
    by_day: dict[str, list[tuple]] = {}
    hours = series.get("hours") or []
    temps = series.get("temp_hourly") or []
    rhs = series.get("rh_hourly") or []
    for i, stamp in enumerate(hours):
        t = temps[i] if i < len(temps) else None
        h = rhs[i] if i < len(rhs) else None
        by_day.setdefault(stamp[:10], []).append((t, h))
    return by_day


def _window_ok(option: dict, day_list: list[str], by_day, rain_by_day) -> bool | None:
    """Whether one moving window, ending on the last day of `day_list`, meets
    an option. None when the hours needed are missing."""
    window = day_list[-option["window_days"]:]
    if len(window) < option["window_days"]:
        return None
    pairs = [p for d in window for p in by_day.get(d, [])]
    if len(pairs) < 24 * option["window_days"] or any(t is None or h is None for t, h in pairs):
        return None
    if "rh_above" in option:
        rh_hours = sum(1 for _, h in pairs if h > option["rh_above"])
    else:
        rh_hours = sum(1 for _, h in pairs if h >= option["rh_at_least"])
    temp_hours = sum(1 for t, _ in pairs if CONGENIAL[0] <= t <= CONGENIAL[1])
    ok = rh_hours >= option["rh_hours"] and temp_hours >= option["temp_hours"]
    if ok and option.get("rain_2day_mm") is not None:
        rains = [rain_by_day.get(d) for d in window]
        ok = any(
            a is not None and b is not None and a + b >= option["rain_2day_mm"]
            for a, b in zip(rains, rains[1:])
        )
    return ok


def _option_met(option: dict, days: list[str], end: int, by_day, rain_by_day) -> bool | None:
    """Whether the option holds for `persist_days` consecutive window-ends
    finishing at index `end` of `days`."""
    results = []
    for k in range(option["persist_days"]):
        last = end - k
        if last < 0:
            return None
        results.append(_window_ok(option, days[:last + 1], by_day, rain_by_day))
    if any(r is None for r in results):
        return None
    return all(results)


def _hours_short(option, days, end, by_day) -> float | None:
    """How close the latest window came, as the smaller of the two fractions
    of required hours. Used only to call a near miss "moderate"."""
    window = days[max(0, end - option["window_days"] + 1):end + 1]
    pairs = [p for d in window for p in by_day.get(d, [])]
    if not pairs or any(t is None or h is None for t, h in pairs):
        return None
    if "rh_above" in option:
        rh = sum(1 for _, h in pairs if h > option["rh_above"])
    else:
        rh = sum(1 for _, h in pairs if h >= option["rh_at_least"])
    temp = sum(1 for t, _ in pairs if CONGENIAL[0] <= t <= CONGENIAL[1])
    return min(rh / option["rh_hours"], temp / option["temp_hours"])


NEAR_MISS = 2 / 3


def _assess_hourly(model: dict, series: dict, today: date, state: str | None) -> dict:
    by_day = _hourly_by_day(series)
    days = sorted(by_day)
    rain_by_day = {d["date"]: d["rain"] for d in _days(series)}
    today_s = today.isoformat()
    past_end = max((i for i, d in enumerate(days) if d < today_s), default=-1)
    own_region = (state or "").strip().lower() in model["states"]
    where = ", ".join(sorted(s.title() for s in model["states"]))

    # `reason` is written for the farmer: it reaches the answer, so it says what
    # the weather has been like, never a model's name or a threshold - a live
    # answer told a farmer "JHULSACAST threshold ke hisaab se". Which model
    # decided it, and any caveat about where it was validated, go in their own
    # fields for the API and for reviewers.
    disease = model["disease"]
    note = None if own_region else f"model validated for {where}, not this state"
    base = {"disease": disease, "model": model["model"], "source": model["source"],
            "reviewed": model["reviewed"], "forecast": False, "note": note}

    met_now = [_option_met(o, days, past_end, by_day, rain_by_day) for o in model["options"]]
    if all(m is None for m in met_now):
        return {**base, "level": "unknown",
                "reason": "hourly humidity and temperature were not available"}

    if any(met_now):
        level = "high" if own_region else "moderate"
        reason = (f"the last week has been damp and mild for long enough that "
                  f"{disease} is likely to appear {model['lead']}")
        return {**base, "level": level, "reason": reason}

    # Not met on observed days. Does the forecast reach it within 7 days? Here
    # one qualifying window is enough, without the persistence the model asks
    # for: this is an early warning worded as "moderate", not the model's own
    # prediction, and requiring a week of forecast windows would only ever fire
    # once the observed days had met it already.
    last = len(days) - 1
    for end in range(past_end + 1, min(last, past_end + 7) + 1):
        if any(_option_met({**o, "persist_days": 1}, days, end, by_day, rain_by_day)
               for o in model["options"]):
            ahead = end - past_end
            return {**base, "level": "moderate", "forecast": True,
                    "reason": f"the next {ahead} day{'s' if ahead != 1 else ''} are "
                              f"forecast to be damp and mild enough to favour {disease}"}

    closeness = [c for c in (_hours_short(o, days, past_end, by_day) for o in model["options"])
                 if c is not None]
    if closeness and max(closeness) >= NEAR_MISS:
        return {**base, "level": "moderate",
                "reason": f"the last week has been fairly damp and mild, close to "
                          f"what {disease} needs"}
    return {**base, "level": "low",
            "reason": f"the last week has not been damp and mild for long enough "
                      f"to favour {disease}"}


def _assess_daily(rule: dict, series: dict, today: date) -> dict:
    base = {"disease": rule["disease"], "model": "extension guidance",
            "source": rule["source"], "reviewed": rule["reviewed"], "forecast": False}
    if rule["months"] and today.month not in rule["months"]:
        return {**base, "level": "low", "reason": "out of season for it"}

    days = _days(series)
    today_s = today.isoformat()
    past = [d for d in days if d["date"] < today_s][-7:]
    ahead = [d for d in days if d["date"] >= today_s][:7]

    usable = [d for d in past if _complete(d) and d["rain"] is not None]
    if len(usable) < 5:
        return {**base, "level": "unknown", "reason": "too few days of humidity on record"}

    count = sum(1 for d in usable if rule["day"](d))
    ahead_usable = [d for d in ahead if _complete(d) and d["rain"] is not None]
    ahead_count = sum(1 for d in ahead_usable if rule["day"](d))

    span = f"{count} of the last {len(usable)} days had {rule['favourable']}"
    if count >= COUNT_HIGH:
        return {**base, "level": "high", "reason": span}
    if count >= COUNT_MODERATE:
        return {**base, "level": "moderate", "reason": span}
    if ahead_usable and ahead_count >= COUNT_MODERATE:
        return {**base, "level": "moderate", "forecast": True,
                "reason": f"{ahead_count} of the next {len(ahead_usable)} days are "
                          f"forecast to have {rule['favourable']}"}
    return {**base, "level": "low", "reason": span}


def assess(crop: str | None, series: dict | None, today: date | None = None,
           state: str | None = None) -> list[dict]:
    """Risk for every disease with a rule for this crop, highest first.

    Each item: disease, level (high | moderate | low | unknown), reason (plain,
    countable), forecast (whether the level comes from the days ahead), model,
    source and reviewed.
    """
    c = normalise_crop(crop)
    if not c:
        return []
    today = today or date.today()
    rules = [r for r in HOURLY_MODELS if r["crop"] == c]
    daily = [r for r in DAILY_RULES if r["crop"] == c]
    if not rules and not daily:
        return []
    if not series:
        names = dict.fromkeys(r["disease"] for r in rules + daily)
        return [{"disease": n, "level": "unknown", "forecast": False, "model": None,
                 "source": None, "reviewed": False,
                 "reason": "the weather series was not available"} for n in names]

    results = []
    # Several regional versions of one model answer one question: keep the one
    # that applies to this state if any, else the strongest.
    by_disease: dict[str, list[dict]] = {}
    for model in rules:
        by_disease.setdefault(model["disease"], []).append(
            (model, _assess_hourly(model, series, today, state)))
    order = {"high": 0, "moderate": 1, "low": 2, "unknown": 3}
    for disease, pairs in by_disease.items():
        own = [r for m, r in pairs if (state or "").strip().lower() in m["states"]]
        pick = own[0] if own else min((r for _, r in pairs), key=lambda r: order[r["level"]])
        results.append(pick)
    results += [_assess_daily(r, series, today) for r in daily]
    return sorted(results, key=lambda r: order[r["level"]])


# --- Soil lookalikes --------------------------------------------------------
#
# Symptom words arrive in English: the extraction call translates what the
# farmer wrote, and the photograph is described in English. Each lookalike
# needs a symptom of its kind; spots, pustules and powdery growth are what a
# pathogen leaves, and when they are reported soil is not offered at all.

SYMPTOM_WORDS = {
    "yellowing": ("yellow", "chlorosis", "chlorotic", "pale"),
    "wilting":   ("wilt", "droop", "drying"),
    "stunting":  ("stunt", "poor growth", "not growing", "small plant"),
    "purple":    ("purple", "reddish leaves"),
}
PATHOGEN_SIGNS = ("spot", "lesion", "pustule", "powder", "mildew", "rust", "hole",
                  "streak", "ring", "mould", "mold", "ooze")

CLAY = {"Clay", "Silty clay", "Sandy clay", "Clay loam", "Silty clay loam"}
SANDY = {"Sand", "Loamy sand", "Sandy loam"}


def symptom_kinds(text: str | None) -> set[str]:
    t = (text or "").lower()
    return {kind for kind, words in SYMPTOM_WORDS.items() if any(w in t for w in words)}


def has_pathogen_signs(text: str | None) -> bool:
    t = (text or "").lower()
    return any(w in t for w in PATHOGEN_SIGNS)


def soil_lookalikes(soil: dict | None, series: dict | None, symptoms: str | None,
                    today: date | None = None) -> list[dict]:
    """Nutrient or water problems that would show as the reported symptoms."""
    kinds = symptom_kinds(symptoms)
    if not kinds or has_pathogen_signs(symptoms):
        return []
    soil = soil or {}
    ph, texture = soil.get("ph"), soil.get("texture")
    today = today or date.today()

    rain_10 = None
    if series:
        past = [d for d in _days(series) if d["date"] < today.isoformat()][-10:]
        if past and all(d["rain"] is not None for d in past):
            rain_10 = sum(d["rain"] for d in past)

    found = []
    if ph is not None and ph >= 8.0 and "yellowing" in kinds:
        found.append({"name": "iron or zinc shortage", "kind": "deficiency",
                      "reason": f"soil pH {ph} is alkaline, which locks up iron and zinc"})
    if ph is not None and ph < 5.5 and kinds & {"yellowing", "stunting", "purple"}:
        found.append({"name": "phosphorus shortage or acid-soil stress", "kind": "deficiency",
                      "reason": f"soil pH {ph} is strongly acidic"})
    if ph is not None and ph >= 8.0 and "purple" in kinds:
        found.append({"name": "phosphorus shortage", "kind": "deficiency",
                      "reason": f"soil pH {ph} is alkaline, which ties up phosphorus"})
    if texture in CLAY and rain_10 is not None and rain_10 >= 50 and kinds & {"yellowing", "wilting"}:
        found.append({"name": "waterlogging or root rot", "kind": "abiotic",
                      "reason": f"{texture.lower()} soil after {rain_10:.0f} mm of rain "
                                f"in the last 10 days drains slowly"})
    if texture in SANDY and rain_10 is not None and rain_10 < 5 and "wilting" in kinds:
        found.append({"name": "water stress", "kind": "abiotic",
                      "reason": f"{texture.lower()} soil holds little water and only "
                                f"{rain_10:.0f} mm of rain fell in the last 10 days"})
    return found
