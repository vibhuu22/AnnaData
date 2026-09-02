"""
Mandi (market) prices from data.gov.in.

The previous version paged through every record for a state with no cap and no
commodity filter, then fed the whole dump into the LLM prompt - thousands of
rows for a large state. It now filters by commodity where known and stops at
MANDI_MAX_RECORDS.
"""
import re
import threading
import time

import requests

from config import (
    GOV_API_KEY,
    MANDI_MAX_RECORDS,
    GOV_API_TIMEOUT,
    GOV_API_DEADLINE,
    GOV_API_ATTEMPTS,
    GOV_FAILURE_THRESHOLD,
    GOV_CIRCUIT_COOLDOWN,
)

RESOURCE_URL = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
PAGE_SIZE = 100

# data.gov.in's edge drops connections whose User-Agent is the requests default,
# without a status line - the client sees a read timeout or RemoteDisconnected,
# which is indistinguishable from the upstream being down. It is not down: the
# same URL, key and IP answer in under a second under any other User-Agent,
# including an invented one. This was misread as a multi-day outage and cost the
# service its market prices for a week. Identify ourselves explicitly.
HEADERS = {"User-Agent": "AnnaData/1.0 (farmer advisory service)"}

# Circuit breaker. After repeated failures the upstream is presumed down and
# calls are skipped until the cooldown expires, so a farmer gets an immediate
# answer minus prices rather than waiting out two timeouts to be told the same.
_consecutive_failures = 0
_circuit_opened_at = 0.0
_breaker_lock = threading.Lock()


def _circuit_open() -> bool:
    with _breaker_lock:
        if _consecutive_failures < GOV_FAILURE_THRESHOLD:
            return False
        if time.monotonic() - _circuit_opened_at < GOV_CIRCUIT_COOLDOWN:
            return True
        # Cooldown elapsed: allow one probe through to test recovery.
        return False


def _record_success():
    global _consecutive_failures
    with _breaker_lock:
        _consecutive_failures = 0


def _record_failure():
    global _consecutive_failures, _circuit_opened_at
    with _breaker_lock:
        _consecutive_failures += 1
        if _consecutive_failures >= GOV_FAILURE_THRESHOLD:
            _circuit_opened_at = time.monotonic()
            print(f"data.gov.in circuit opened after {_consecutive_failures} "
                  f"failures; pausing calls for {GOV_CIRCUIT_COOLDOWN}s")


# The circuit breaker above lives in one process, so a freshly started instance
# believes the upstream is healthy until it fails once - and on a platform that
# scales to zero, that is most instances. Recording the outcome makes the outage
# survive a restart, which matters because it is what the service consults
# before telling a farmer it can quote market prices.
HEALTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS mandi_health (
    id                   BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (id),
    last_success         TIMESTAMPTZ,
    last_failure         TIMESTAMPTZ,
    consecutive_failures INTEGER NOT NULL DEFAULT 0
);
"""


def _record_outcome(ok: bool) -> None:
    import db

    if not db.is_available():
        return
    try:
        with db.connection() as conn:
            conn.execute(HEALTH_SCHEMA)
            if ok:
                conn.execute(
                    """INSERT INTO mandi_health (id, last_success, consecutive_failures)
                       VALUES (TRUE, now(), 0)
                       ON CONFLICT (id) DO UPDATE
                       SET last_success = now(), consecutive_failures = 0"""
                )
            else:
                conn.execute(
                    """INSERT INTO mandi_health (id, last_failure, consecutive_failures)
                       VALUES (TRUE, now(), 1)
                       ON CONFLICT (id) DO UPDATE
                       SET last_failure = now(),
                           consecutive_failures = mandi_health.consecutive_failures + 1"""
                )
    except Exception as e:
        print(f"Could not record mandi outcome: {e}")


def is_available() -> bool:
    """Whether market prices can currently be expected to work.

    Consulted before the service describes itself. Announcing a capability that
    is failing is the same fault as denying one that works - the difference is
    only which way the farmer is misled.
    """
    if not GOV_API_KEY:
        return False
    if _circuit_open():
        return _cache_is_fresh()

    import db
    from datetime import datetime, timedelta, timezone

    if not db.is_available():
        return True                       # no record either way; assume usable
    try:
        with db.connection() as conn:
            conn.execute(HEALTH_SCHEMA)
            row = conn.execute(
                "SELECT last_failure, consecutive_failures FROM mandi_health WHERE id = TRUE"
            ).fetchone()
    except Exception:
        return True

    if not row or not row[0]:
        return True
    last_failure, failures = row
    if failures < GOV_FAILURE_THRESHOLD:
        return True
    if datetime.now(timezone.utc) - last_failure > timedelta(seconds=GOV_CIRCUIT_COOLDOWN):
        return True

    # The live call is failing, but a cache warmed from elsewhere is a working
    # capability, not a degraded one: mandi prices are published once a day, so
    # yesterday's snapshot is what a live call would mostly have returned. The
    # answer states the date either way.
    return _cache_is_fresh()


# How stale the cache may be before market prices stop being offered at all.
# Two days covers a missed run without letting a week-old price be quoted as if
# it were current.
CACHE_MAX_AGE_DAYS = 2


def _cache_is_fresh(max_age_days: int = CACHE_MAX_AGE_DAYS) -> bool:
    import db
    from datetime import datetime, timedelta, timezone

    if not db.is_available():
        return False
    try:
        with db.connection() as conn:
            conn.execute(CACHE_SCHEMA)
            row = conn.execute("SELECT max(fetched_at) FROM mandi_cache").fetchone()
    except Exception:
        return False
    if not row or not row[0]:
        return False
    return datetime.now(timezone.utc) - row[0] < timedelta(days=max_age_days)


# Names for published labels that unpacking alone does not reach.
#
# aliases_for() splits on brackets and slashes, which handles "Paddy(Common)"
# and "Red gram/Arhar/Tur(whole)". It cannot handle a label whose crop name is
# one word of several - "Green Chilli", "Bitter gourd" - and splitting on spaces
# is not the answer: "gram" would then match Bengal Gram, Black Gram and Green
# Gram, three different pulses, which is the very error being fixed. So the
# multi-word labels get their names listed explicitly, in the vernacular a
# farmer in the Hindi belt actually types.
#
# Keyed by the published label lowercased. Deliberately separate from
# CROP_SYNONYMS, which is the pesticide register's vocabulary, not Agmarknet's.
LABEL_ALIASES = {
    "green chilli":        {"mirch", "mirchi", "chilli", "hari mirch"},
    "chili red":           {"mirch", "mirchi", "chilli", "lal mirch"},
    "chilly capsicum":     {"shimla mirch", "capsicum"},
    "capsicum":            {"shimla mirch"},
    "bitter gourd":        {"karela"},
    "bottle gourd":        {"lauki", "ghiya"},
    "sponge gourd":        {"nenua"},
    "ridgeguard(tori)":    {"torai", "turai"},
    "ashgourd":            {"petha"},
    "snakeguard":          {"chichinda"},
    "cluster beans":       {"guar", "gawar"},
    "indian beans(seam)":  {"sem", "sem phali"},
    "cowpea(veg)":         {"lobia", "chawli"},
    "peas wet":            {"matar", "peas", "hara matar"},
    "french beans(frasbean)": {"farasbean", "beans"},
    "black gram(urd beans)(whole)": {"urad", "urd", "urad dal", "kali dal"},
    "green gram(moong)(whole)":     {"mung", "moong dal"},
    "colacasia":           {"arbi", "arvi", "ghuiyan"},
    "elephant yam(suran)/amorphophallus": {"jimikand", "ol"},
    "drumstick":           {"sahjan", "munga"},
    "raddish":             {"mooli", "radish"},
    "beetroot":            {"chukandar"},
    "carrot":              {"gajar"},
    "cabbage":             {"patta gobhi", "bandh gobhi"},
    "cauliflower":         {"phool gobhi", "gobhi", "phulgobhi"},
    "spinach":             {"palak"},
    "coriander(leaves)":   {"dhaniya", "hara dhaniya"},
    "amaranthus":          {"chaulai"},
    "sweet pumpkin":       {"kaddu", "mitha kaddu"},
    "pumpkin":             {"kaddu"},
    "tamarind fruit":      {"imli", "tamarind"},
    "tender coconut":      {"daab", "nariyal pani"},
    "coconut":             {"nariyal"},
    "banana - green":      {"kaccha kela", "green banana"},
    "banana":              {"kela"},
    "mousambi(sweet lime)": {"mosambi", "sweet lime"},
    "lemon":               {"nimbu", "neembu"},
    "guava":               {"amrud"},
    "papaya":              {"papita"},
    "mango":               {"aam"},
    "pomegranate":         {"anar"},
    "apple":               {"seb"},
    "cashewnuts":          {"kaju", "cashew"},
    "ginger(dry)":         {"adrak", "sonth"},
    "ginger(green)":       {"adrak", "hara adrak"},
    "gur(jaggery)":        {"gud"},
    "spiny gourd / kartali(kantola)": {"kakora", "kakrol"},
    "little gourd(kundru)": {"kundri"},
    "pointed gourd(parval)": {"parwal", "palwal"},
}


def _label_names(label: str) -> set:
    """Every name that identifies one published commodity label."""
    import msp

    return set(msp.aliases_for(label)) | LABEL_ALIASES.get(label.strip().lower(), set())


def _wanted_names(commodity: str) -> set:
    """Every name that should count as the crop the farmer asked about.

    Both directions matter. A farmer typing "bhindi" is canonicalised to okra,
    and the register publishes "Bhindi(Ladies Finger)" - so the canonical form
    alone matches nothing, and the typed form alone misses the English label.
    """
    from knowledge import CROP_SYNONYMS, canonical_crop

    name = (commodity or "").strip().lower()
    if not name:
        return set()
    canonical = canonical_crop(name) or name
    names = {name, canonical}
    names |= {k for k, v in CROP_SYNONYMS.items() if v == canonical}
    return names


def _select(records, commodity: str | None) -> list:
    """The rows that really are the requested crop.

    The published labels pack synonyms into brackets and slashes - "Paddy
    (Common)", "Red gram/Arhar/Tur(whole)" - so matching is done against the
    unpacked aliases, the same way support prices are looked up.
    """
    if not commodity:
        return records
    wanted = _wanted_names(commodity)
    return [r for r in records
            if wanted & _label_names(r.get("commodity") or "")]


def no_arrivals(state: str, commodity: str) -> str:
    """Said when the crop is genuinely not trading, which is common and normal.

    A server-side filter that matches nothing used to fall back to the whole
    state, so asking for wheat in September - when no wheat arrives in Uttar
    Pradesh at all - returned cauliflower and okra. Those are real prices for
    real crops and nothing in the text says they are not wheat, which invites
    the model to quote one as the answer. An absent crop is a fact worth
    stating; another crop's price is not an approximation of it.
    """
    return (
        f"No {commodity} rate appears in the latest published data for {state} "
        f"mandis. The daily publication only covers markets that reported, so a "
        f"crop can be missing either because it is out of season or because no "
        f"reporting market traded it - do not assert which. Say plainly that "
        f"today's {commodity} rate is not available, and give the support price "
        f"instead if one appears in the Context. Do NOT quote any other crop's "
        f"price as though it were {commodity}."
    )


def format_state_data(records) -> str:
    """Convert market records into a readable summary."""
    if not records:
        return "No mandi price data available for the selected state."

    lines = []
    for record in records:
        lines.append(
            f"Market: {record.get('market', 'N/A')} | "
            f"Commodity: {record.get('commodity', 'N/A')} "
            f"({record.get('variety', 'N/A')}) | "
            f"Grade: {record.get('grade', 'N/A')} | "
            f"Arrival Date: {record.get('arrival_date', 'N/A')} | "
            f"Min Price: Rs{record.get('min_price', 'N/A')} | "
            f"Max Price: Rs{record.get('max_price', 'N/A')} | "
            f"Modal Price: Rs{record.get('modal_price', 'N/A')}"
        )

    return "\n".join(lines)


# The register's spelling of a few states differs from the one geocoding returns,
# and a mismatch is silent: the farmer simply gets no prices for their own state.
STATE_ALIASES = {
    "keralam": "kerala",
    "orissa": "odisha",
    "pondicherry": "puducherry",
    "uttaranchal": "uttarakhand",
    "nct of delhi": "delhi",
    "jammu and kashmir": "jammu & kashmir",
}


def _norm_state(state: str | None) -> str:
    name = (state or "").strip().lower()
    return STATE_ALIASES.get(name, name)


# Districts are written one way by the geocoder and another by the register:
# "Paschim Medinipur" against "Medinipur(W)", "Purba Bardhaman" against
# "Bardhaman(E)". Both name the same place with the direction in a different
# language and a different position, so both are reduced to a set of words with
# the direction in English, and compared that way.
DIRECTIONS = {
    "paschim": "west", "pashchim": "west", "w": "west",
    "purba": "east", "purva": "east", "poorba": "east", "e": "east",
    "uttar": "north", "uttara": "north", "n": "north",
    "dakshin": "south", "dakshina": "south", "sounth": "south", "s": "south",
}
DISTRICT_NOISE = {"district", "dist", "zila", "zilla", "jila"}


def _district_words(name: str | None) -> frozenset:
    """A district name reduced to comparable words."""
    if not name:
        return frozenset()
    words = re.split(r"[^a-z0-9]+", name.strip().lower())
    out = set()
    for word in words:
        if not word or word in DISTRICT_NOISE:
            continue
        out.add(DIRECTIONS.get(word, word))
    return frozenset(out)


def _in_district(record: dict, district: str | None) -> bool:
    if not district:
        return True
    return _district_words(record.get("district")) == _district_words(district)


def _in_state(record: dict, state: str) -> bool:
    """Whether a row is really from the state we asked for.

    filters[state] matches on tokens, not on the whole value, so asking for
    "Uttar Pradesh" returns Andhra Pradesh and Himachal Pradesh as well - they
    share the word "Pradesh". Of 106 rows returned for Uttar Pradesh, 19 were
    actually from it. A farmer in Barabanki was being quoted paddy from
    Kothabommali, 1,500 km away, with the market named but the state not.

    The upstream filter is still sent: it cuts the volume enormously. It just
    cannot be trusted as the last word.
    """
    return _norm_state(record.get("state")) == _norm_state(state)


def _fetch(state: str, commodity: str | None) -> list:
    records = []
    offset = 0
    deadline = time.monotonic() + GOV_API_DEADLINE

    while len(records) < MANDI_MAX_RECORDS:
        # Paging multiplies the per-request timeout, so the fetch as a whole
        # gets a deadline. Whatever has arrived by then is returned: a partial
        # list of markets is a usable answer, a timeout is not.
        if time.monotonic() > deadline:
            print(f"Mandi fetch deadline reached with {len(records)} record(s)")
            break

        params = {
            "api-key": GOV_API_KEY,
            "format": "json",
            "filters[state]": state,
            "limit": PAGE_SIZE,
            "offset": offset,
        }
        if commodity:
            params["filters[commodity]"] = commodity

        page = None
        for attempt in range(1, GOV_API_ATTEMPTS + 1):
            try:
                response = requests.get(RESOURCE_URL, params=params,
                                        headers=HEADERS,
                                        timeout=GOV_API_TIMEOUT)
                response.raise_for_status()
                page = response.json().get("records", [])
                break
            except Exception as e:
                print(f"data.gov.in attempt {attempt} failed: {e}")
                if attempt == GOV_API_ATTEMPTS:
                    raise
        if page is None:
            break

        # An empty page means the end of the data. A page with no rows for our
        # state does not - see _in_state - so the two cases are separated here.
        if not page:
            break

        records.extend(r for r in page if _in_state(r, state))
        offset += PAGE_SIZE

    return records[:MANDI_MAX_RECORDS]


# Successful lookups are kept so an outage degrades to a stale price rather
# than to nothing. A farmer deciding when to sell is better served by "cotton
# was Rs 7,200 a quintal in Nagpur on 25 August" than by silence, provided the
# date is stated plainly and they can see how old it is.
CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS mandi_cache (
    state      TEXT NOT NULL,
    commodity  TEXT NOT NULL DEFAULT '',
    summary    TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (state, commodity)
);
"""

# The rows behind the summary. Holding the day's snapshot structured rather than
# pre-rendered is what lets a cached answer be narrowed to one crop: without it
# the only cached entry for a state is the whole state, and serving that to a
# farmer who asked about wheat is the wrong-crop bug by another route.
CACHE_RECORDS_COLUMN = "ALTER TABLE mandi_cache ADD COLUMN IF NOT EXISTS records JSONB;"


def _cache_key(state: str, commodity: str | None) -> tuple:
    return (_norm_state(state), (commodity or "").strip().lower())


def _cache_store(state: str, commodity: str | None, summary: str,
                 records=None) -> None:
    import json

    import db

    if not db.is_available() or not summary:
        return
    st, cm = _cache_key(state, commodity)
    try:
        with db.connection() as conn:
            conn.execute(CACHE_SCHEMA)
            conn.execute(CACHE_RECORDS_COLUMN)
            conn.execute(
                """
                INSERT INTO mandi_cache (state, commodity, summary, records, fetched_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (state, commodity)
                DO UPDATE SET summary    = EXCLUDED.summary,
                              records    = EXCLUDED.records,
                              fetched_at = now()
                """,
                (st, cm, summary,
                 json.dumps(records) if records is not None else None),
            )
    except Exception as e:
        print(f"Could not cache mandi prices: {e}")


def _cache_lookup(state: str, commodity: str | None,
                  district: str | None = None) -> str | None:
    import db
    from datetime import datetime, timezone

    if not db.is_available():
        return None
    st, cm = _cache_key(state, commodity)
    try:
        with db.connection() as conn:
            conn.execute(CACHE_SCHEMA)
            conn.execute(CACHE_RECORDS_COLUMN)
            row = conn.execute(
                """
                SELECT summary, records, fetched_at FROM mandi_cache
                 WHERE state = %s AND (commodity = %s OR commodity = '')
              ORDER BY (commodity = %s) DESC, fetched_at DESC
                 LIMIT 1
                """,
                (st, cm, cm),
            ).fetchone()
    except Exception as e:
        print(f"Mandi cache lookup failed: {e}")
        return None

    if not row:
        return None

    summary, records, fetched = row

    # The query above deliberately falls back to the whole-state entry, because
    # a broad answer beats none when no crop was named. When one WAS named that
    # fallback is the wrong-crop bug: narrow it here against the stored rows,
    # and say the crop was absent rather than handing over its neighbours.
    if commodity and records:
        selected = _select(records, commodity)
        if not selected:
            return no_arrivals(state, commodity)
        selected, note = narrow_to_district(selected, district, commodity, state)
        summary = note + format_state_data(selected)
    elif commodity:
        # Pre-existing entry with no structured rows: it may be the whole state,
        # and cannot be narrowed. Refusing is the only safe reading.
        return None

    age_days = (datetime.now(timezone.utc) - fetched).days
    when = fetched.strftime("%d %B %Y")

    # Whether this is a degraded answer depends entirely on its age, and the
    # cache is now refreshed daily rather than only written when a live call
    # happened to succeed. Calling same-day prices "temporarily unavailable"
    # would have the model apologise while quoting the correct figure.
    if age_days == 0:
        preamble = f"Mandi prices published on {when}. State that date to the farmer:"
    else:
        preamble = (
            f"Live mandi prices are unavailable. These are the last prices on "
            f"record, from {when} ({age_days} day(s) old) - tell the farmer that "
            f"date and that they should confirm today's rate at the mandi:"
        )
    return f"{preamble}\n{summary}"


def narrow_to_district(records: list, district: str | None, commodity: str | None,
                       state: str) -> tuple[list, str]:
    """Prefer the farmer's own district, and say plainly when it has no arrivals.

    A farmer in Kharagpur asking a potato price was handed every rate in West
    Bengal - Rs 580 in Coochbehar, Rs 1500 in Darjeeling, 600 km apart - and
    then asked which mandi they meant. Their district was known and unused. It
    is the difference between a price they can act on and a spread they cannot.

    When their own district reported nothing, the state picture is still worth
    giving, but it is labelled as such rather than passed off as their rate.
    """
    if not district or not records:
        return records, ""
    local = [r for r in records if _in_district(r, district)]
    if local:
        return local, (f"These are the rates in the farmer's own district "
                       f"({district}). Lead with them.\n")
    crop = commodity or "this crop"
    return records, (
        f"No {crop} arrivals were reported from the farmer's own district "
        f"({district}) in this data. Say that plainly first. The rates below "
        f"are from other districts of {state} and are NOT their local rate - "
        f"give them only as a general picture, and do not ask the farmer which "
        f"mandi they mean, because their district is already known.\n"
    )


def get_state_data(state: str, commodity: str | None = None,
                   district: str | None = None) -> str:
    """Mandi prices for a state, narrowed to a commodity and district when known."""
    if not state or state.lower() == "unknown":
        return "Mandi price data unavailable (no state identified)."

    if not GOV_API_KEY:
        return "Mandi price data unavailable (GOV_API_KEY not set)."

    if commodity and commodity.lower() == "unknown":
        commodity = None

    if _circuit_open():
        return _cache_lookup(state, commodity, district) or             "Mandi price data unavailable (the government price service is down)."

    try:
        records = _fetch(state, commodity)

        # The server-side commodity filter matches the published label exactly,
        # so it misses "okra" against "Bhindi(Ladies Finger)". Widening and
        # selecting locally recovers those. What it must not do any more is
        # return the wider list as though it answered the question.
        if commodity:
            selected = _select(records, commodity)
            if not selected:
                everything = _fetch(state, None)
                selected = _select(everything, commodity)
                # Deliberately not cached under the whole-state key. _fetch
                # stops at MANDI_MAX_RECORDS (80) because that list is headed
                # for a prompt, and writing it here overwrote the warm job's
                # complete snapshot with a truncated one - Uttar Pradesh held 80
                # rows against 261 published. The state-wide entry belongs to
                # the job that fetches the state in full.
            records = selected

        _record_success()
        _record_outcome(True)

        if commodity and not records:
            return no_arrivals(state, commodity)

        # Cache the state's rows, not the district's slice: the entry is shared
        # by every farmer in the state, and narrowing belongs to the reader.
        if records:
            _cache_store(state, commodity, format_state_data(records), records=records)

        records, note = narrow_to_district(records, district, commodity, state)
        return note + format_state_data(records)

    except Exception as e:
        _record_failure()
        _record_outcome(False)
        print(f"Mandi price lookup failed for state={state!r}: {e}")
        return _cache_lookup(state, commodity, district) or             "Mandi price data unavailable (lookup failed)."
