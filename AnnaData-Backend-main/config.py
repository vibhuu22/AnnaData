"""
Central configuration and feature detection.

Every external integration is optional except Gemini. If a key is missing the
corresponding tool reports itself unavailable and the agent routes around it,
rather than raising at import time and taking the whole service down.
"""
import os
from dotenv import load_dotenv

load_dotenv()
# Optional local admin configuration. Production uses environment secrets.
from pathlib import Path
load_dotenv(Path(__file__).with_name('.env.admin'))


def _get(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is not None:
        value = value.strip()
    return value or None


# --- Required ---
GEMINI_API_KEY = _get("GEMINI_API_KEY")

# --- Optional integrations ---
LOCATION_API_KEY = _get("LOCATION_API_KEY")      # Google Maps Geocoding (optional)

# Geocoding falls back to OpenStreetMap's Nominatim when no Google key is set.
# Their policy requires a User-Agent identifying the application, with a way to
# reach whoever runs it - set a real contact address before any real traffic.
NOMINATIM_URL = _get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
NOMINATIM_USER_AGENT = _get(
    "NOMINATIM_USER_AGENT",
    "AnnaData/1.0 (agricultural advisory for Indian farmers; +https://github.com/vibhuu22/AnnaData)",
)
# Restricts results to India so a district name cannot resolve abroad.
GEOCODE_COUNTRY = _get("GEOCODE_COUNTRY", "in")
GOV_API_KEY = _get("GOV_API_KEY")                # data.gov.in mandi prices
EE_SERVICE_KEY = _get("EE_SERVICE_KEY")          # Earth Engine soil data
# Usually read from the service account key itself; set only if the project
# registered with Earth Engine differs from the key's own project.
EE_PROJECT = _get("EE_PROJECT")
KNOWLEDGE_BASE_ID = _get("KNOWLEDGE_BASE_ID")    # AWS Bedrock knowledge base
AWS_REGION = _get("AWS_REGION", "ap-south-1")
AWS_ACCESS_KEY = _get("AWS_ACCESS_KEY")
AWS_SECRET_KEY = _get("AWS_SECRET_KEY")

# --- Storage (optional) ---
# Postgres for farmer profiles and conversation history. Without it the agent
# runs exactly as before: stateless, no memory, no personalisation.
DATABASE_URL = _get("DATABASE_URL")
DB_POOL_MAX = int(_get("DB_POOL_MAX", "4"))
# Turns of conversation replayed to the model, and how stale they may be.
# Cosine similarity a retrieved passage must reach to be shown to the model.
# Measured against the loaded corpus: questions the documents genuinely cover
# score 0.68-0.80, while questions they do not top out around 0.58. Set too
# low, loosely-related passages are passed along and the model answers from
# general knowledge anyway - retrieval then produces a more confident guess
# rather than a grounded answer.
#
# The floor is corpus dependent and will need revisiting as documents are
# added: it began at 0.65, which was fine for a single scheme, and a question
# about tractor subsidies then scored 0.667 against a PMFBY passage on Gujarat
# leaving the scheme - close enough on wording, entirely wrong on substance. A
# similarity number alone cannot tell relevance from adjacency, so the prompt
# also requires the model to check that a passage actually addresses the
# question before using it.
RAG_MIN_SIMILARITY = float(_get("RAG_MIN_SIMILARITY", "0.70"))
# The same floor for the DPPQ&S pest advisories, measured on 13.11.2026 against
# the 213 loaded passages with crop + pest + question as the query (as gather
# sends it). Ten questions the advisories cover scored 0.739-0.823, each with
# the right advisory on top; six they do not cover scored 0.592-0.707. The one
# that passed 0.70 was okra vein mosaic matching the green gram mosaic
# advisory - close in wording, wrong crop. A small sample: re-measure when
# advisories are added.
ADVISORY_MIN_SIMILARITY = float(_get("ADVISORY_MIN_SIMILARITY", "0.72"))

CONTEXT_MESSAGES = int(_get("CONTEXT_MESSAGES", "10"))
CONTEXT_TTL_HOURS = int(_get("CONTEXT_TTL_HOURS", "48"))
# How long before a farmer who ignored the location question is asked again.
LOCATION_ASK_COOLDOWN_HOURS = int(_get("LOCATION_ASK_COOLDOWN_HOURS", "24"))

# --- Feedback ---
# A conversation is considered finished after this much silence, which is also
# when it becomes fair to ask what the farmer thought of it.
SESSION_GAP_HOURS = int(_get("SESSION_GAP_HOURS", "2"))
# Each farmer is asked at most once a calendar month, on a day drawn for them
# rather than a shared one - a single date would send every reminder at once
# and put a month of SMS through one handset in an afternoon.
FEEDBACK_COOLDOWN_DAYS = int(_get("FEEDBACK_COOLDOWN_DAYS", "25"))
# How long after asking a reply still counts as a rating rather than a question.
FEEDBACK_WINDOW_HOURS = int(_get("FEEDBACK_WINDOW_HOURS", "48"))

# --- Deployment ---
FRONTEND_URL = _get("FRONTEND_URL")
CORS_ORIGINS = _get("CORS_ORIGINS")              # comma-separated, optional


# --- Sign-in --------------------------------------------------------------
#
# Unlike every other integration here, this one does not degrade to "off". A
# missing key elsewhere disables a tool and the agent routes around it; a
# missing signing secret cannot be allowed to mean "let anyone be anyone".
#
# So an absent AUTH_SECRET produces a random one at boot. Sign-in keeps working,
# but the secret dies with the process, which means every farmer is signed out
# by a restart or a second instance. That is a visible, annoying failure rather
# than a silent, invisible one - and on a free tier that sleeps, it is visible
# within the hour. Set AUTH_SECRET in the deployment and it stops happening.
AUTH_SECRET = _get("AUTH_SECRET")
AUTH_SECRET_IS_EPHEMERAL = AUTH_SECRET is None
if AUTH_SECRET_IS_EPHEMERAL:
    import secrets as _secrets
    AUTH_SECRET = _secrets.token_urlsafe(48)
    print("AUTH_SECRET not set: generated one for this process only. "
          "Every sign-in will be lost on restart. Set AUTH_SECRET to fix this.")

# Long, because the farmer is on a phone and signing in costs a real SMS from
# our own SIM. Making them repeat it weekly would be charging ourselves for the
# privilege of annoying them.
SESSION_TTL = int(_get("SESSION_TTL_DAYS", "90")) * 86400

OTP_TTL = int(_get("OTP_TTL_SECONDS", "600"))            # 10 minutes
OTP_MAX_ATTEMPTS = int(_get("OTP_MAX_ATTEMPTS", "5"))    # wrong guesses per code
OTP_RESEND_COOLDOWN = int(_get("OTP_RESEND_COOLDOWN", "60"))
# Sends, not guesses. Each one is a real SMS off the founder's own SIM, so this
# is the limit that protects the balance and stops the gateway being used to
# pester a stranger's handset.
OTP_MAX_SENDS = int(_get("OTP_MAX_SENDS", "5"))
OTP_SEND_WINDOW = int(_get("OTP_SEND_WINDOW", "3600"))

# When false, /agent still accepts a user_id in the request body the way it
# always has. That is only safe with no public URL; it exists so the SMS bridge
# and local development keep working while the frontend is being moved over.
AUTH_REQUIRED = (_get("AUTH_REQUIRED", "true") or "").lower() not in ("0", "false", "no", "off")

# A shared secret the SMS bridge sends instead of a farmer's token. The gateway
# reports the sender's number and a farmer cannot forge the network's idea of
# their own, so the bridge is trusted to name the user_id - but only the bridge.
BRIDGE_TOKEN = _get("BRIDGE_TOKEN")

# Questions from the web app before the farmer has signed in. A farmer now asks
# first and confirms their number only when they choose to save their farm; see
# guest_access.py for why, and for why each of these bounds exists. Per-hour
# figures are per instance, so Cloud Run's three instances can admit up to three
# times as many. Set GUEST_ASK_ENABLED=false to require sign-in again.
GUEST_ASK_ENABLED = (_get("GUEST_ASK_ENABLED", "true") or "").lower() not in ("0", "false", "no", "off")
GUEST_PER_HOUR = int(_get("GUEST_PER_HOUR", "10"))
# Loose on purpose: carrier-grade NAT puts whole villages behind one address.
GUEST_IP_PER_HOUR = int(_get("GUEST_IP_PER_HOUR", "60"))
GUEST_DAILY_CAP = int(_get("GUEST_DAILY_CAP", "400"))


# --- Outbound SMS (sign-in codes) ----------------------------------------
# The same Android handset gateway the bridge uses. See sms_out.py for why the
# backend calls it directly rather than going through the bridge.
# MSG91's OTP widget, for sign-in codes (msg91.py). Secret: set on Cloud Run,
# never in the repository. Unset, sign-in uses the SIM gateway below.
MSG91_AUTHKEY = _get("MSG91_AUTHKEY")
SMS_GATEWAY_BASE = _get("SMS_GATEWAY_BASE", "https://api.sms-gate.app/3rdparty/v1")
SMS_GATEWAY_USER = _get("SMS_GATEWAY_USER") or _get("APP_USERNAME")
SMS_GATEWAY_PASSWORD = _get("SMS_GATEWAY_PASSWORD") or _get("PASSWORD")
SMS_SEND_TIMEOUT = int(_get("SMS_SEND_TIMEOUT", "20"))


def sms_gateway_ready() -> bool:
    return bool(SMS_GATEWAY_USER and SMS_GATEWAY_PASSWORD)


def sms_messages_url() -> str:
    return SMS_GATEWAY_BASE.rstrip("/") + "/messages"

# --- Models ---
# gemini-2.0-flash and gemini-2.5-* are no longer callable by new API keys; the
# API returns 404 pointing at the 3.x line. Note that models.list reports models
# the key cannot actually invoke, so verify with a real generateContent call.
#
# Comma-separated, fastest first. Each is tried in order: on a quota (429),
# overload (503) or missing-model (404) error the next one takes over. Free-tier
# quota is per model, so the fallbacks also multiply usable daily capacity.
TEXT_MODELS = [
    m.strip()
    for m in (_get("TEXT_MODELS")
              or _get("TEXT_MODEL")
              or "gemini-3.1-flash-lite,gemini-3.6-flash,gemini-3.5-flash-lite").split(",")
    if m.strip()
]
TEXT_MODEL = TEXT_MODELS[0]
MEDIA_MODEL = _get("MEDIA_MODEL", "gemini-3.5-flash-lite")

# --- Spoken answers (tts.py) -------------------------------------------------
# Tried in order. Flash-Lite first: a sentence of advice does not need the
# larger model's range, and it is the cheaper of the two once past the free tier.
TTS_MODELS = [
    m.strip()
    for m in _get("TTS_MODELS",
                  "gemini-3.8-flash-lite-tts,gemini-3.8-flash-tts,gemini-2.5-flash-preview-tts").split(",")
    if m.strip()
]
TTS_VOICE = _get("TTS_VOICE", "Kore")
# The language every Latin- or Devanagari-script piece is spoken in. Left to
# itself the model picked a language per piece, so a sentence heavy with
# English words came out in a different delivery from the Hindi around it - the
# farmer heard the voice change mid-answer. Fixed to Indian Hindi, which is
# also how it reads English: as an Indian speaker would. Bengali and Gurmukhi
# text is always spoken as Bengali and Punjabi. Empty lets the model choose.
TTS_LANGUAGE = _get("TTS_LANGUAGE", "hi-IN")
# An optional direction said to the model before the text. EMPTY BY DEFAULT,
# because the model read it out: every piece of every answer began with "Read
# this aloud slowly and clearly...", which a farmer heard and which roughly
# doubled how long each piece took to make. Measured on the live service: four
# words came back as 7.9 seconds of audio. Leave it empty unless a new model is
# checked first to obey a direction rather than say it.
TTS_STYLE = _get("TTS_STYLE", "")
# One piece of an answer per request - the web app sends a sentence or two.
TTS_MAX_CHARS = int(_get("TTS_MAX_CHARS", "600"))
TTS_TIMEOUT = float(_get("TTS_TIMEOUT", "20"))
# Pieces, not questions: one answer is several. Guests only; see /speak.
SPEAK_GUEST_PER_HOUR = int(_get("SPEAK_GUEST_PER_HOUR", "200"))
SPEAK_IP_PER_HOUR = int(_get("SPEAK_IP_PER_HOUR", "1000"))
SPEAK_DAILY_CAP = int(_get("SPEAK_DAILY_CAP", "5000"))

# Retries inside one model before failing over. Kept low on purpose: the client
# backs off 2s, 4s, 8s, 16s, 32s by default, which spends a minute stalling on a
# quota error when another model would have answered immediately.
LLM_MAX_RETRIES = int(_get("LLM_MAX_RETRIES", "1"))
# The final model in the chain has no fallback behind it, so it gets a larger
# budget to ride out a transient 503.
LLM_LAST_RESORT_RETRIES = int(_get("LLM_LAST_RESORT_RETRIES", "3"))
# Seconds any single model call may take before it is abandoned and the next
# model in the chain is tried.
#
# The retry budgets above bound how many times a FAILED call is repeated. They
# do nothing about a call that neither succeeds nor fails, and an unbounded one
# blocks the whole answer: observed at 97 seconds for an extraction call whose
# entire retry chain, had it errored, would have given up in about twenty.
#
# This is the same lesson the mandi fetch taught - a generous timeout is worth
# having when an upstream is slow, and worthless when it is hanging. Every tool
# in this system is bounded; the model calls were not, which made them the one
# place a farmer could wait indefinitely.
#
# 30s is deliberately well above a healthy call (2-4s) and well below the SMS
# bridge's own 150s ceiling, so the chain can try every model and still answer.
LLM_TIMEOUT = float(_get("LLM_TIMEOUT", "30"))

# --- Tunables ---
MANDI_MAX_RECORDS = int(_get("MANDI_MAX_RECORDS", "80"))
HTTP_TIMEOUT = int(_get("HTTP_TIMEOUT", "20"))
# data.gov.in is markedly slower than the other upstreams and returns 502 under
# load, so it gets its own budget and is retried rather than failing the answer.
# data.gov.in answers in a second or two when it is up, and not at all when it
# is not - so a generous timeout buys nothing and costs the farmer the wait.
# At 45s x 2 attempts a market-price question sat for ninety seconds before
# reporting failure, on SMS, where nothing indicates the question was received.
GOV_API_TIMEOUT = int(_get("GOV_API_TIMEOUT", "12"))
# The whole paged fetch, not one request: the per-request timeout multiplies by
# the number of pages, so the deadline is what actually bounds the answer.
GOV_API_DEADLINE = int(_get("GOV_API_DEADLINE", "20"))
GOV_API_ATTEMPTS = int(_get("GOV_API_ATTEMPTS", "1"))
# data.gov.in goes down for long stretches. Once it has failed repeatedly there
# is no sense making every farmer wait out the timeouts to learn the same
# thing, so calls are suspended briefly and answered instantly instead.
GOV_FAILURE_THRESHOLD = int(_get("GOV_FAILURE_THRESHOLD", "2"))
GOV_CIRCUIT_COOLDOWN = int(_get("GOV_CIRCUIT_COOLDOWN", "600"))
# Open-Meteo is fast from a laptop but shared cloud egress IPs see occasional
# rate limiting, so weather retries rather than silently losing the reading.
WEATHER_TIMEOUT = int(_get("WEATHER_TIMEOUT", "25"))
WEATHER_ATTEMPTS = int(_get("WEATHER_ATTEMPTS", "3"))
# Weather is a property of a place, not of a farmer, so neighbours share a
# reading. Caching by rounded coordinate collapses a whole district's traffic
# into one upstream call and keeps us well under Open-Meteo's rate limit.
WEATHER_CACHE_TTL = int(_get("WEATHER_CACHE_TTL", "3600"))
WEATHER_CACHE_PRECISION = int(_get("WEATHER_CACHE_PRECISION", "1"))  # ~11 km
# Soil readings never expire (the map is fixed); the key is rounded to this many
# decimal places, ~110 m at 3 - well inside the 500 m each reading averages.
SOIL_CACHE_PRECISION = int(_get("SOIL_CACHE_PRECISION", "3"))
# MET Norway is the fallback when Open-Meteo rate limits us. Their terms require
# a User-Agent naming the application with a way to make contact.
METNO_USER_AGENT = _get(
    "METNO_USER_AGENT",
    "AnnaData/1.0 agricultural advisory (+https://github.com/vibhuu22/AnnaData)",
)


def _documents_loaded() -> bool:
    try:
        import knowledge
        return knowledge.documents_loaded()
    except Exception:
        return False


def _mandi_reachable() -> bool:
    """Whether market prices actually work, not merely whether a key is set.

    /health reported mandi_prices true throughout a multi-day upstream outage,
    because it was answering a question about configuration. A health check that
    describes intent rather than reality is worse than none.
    """
    try:
        import Mandi_Price_Tool
        return Mandi_Price_Tool.is_available()
    except Exception:
        return bool(GOV_API_KEY)


def feature_status() -> dict:
    """Which integrations are configured. Surfaced on /health."""
    return {
        "gemini": bool(GEMINI_API_KEY),
        # Geocoding always works now: Nominatim needs no key.
        "geocoding": True,
        "geocoding_provider": "google" if LOCATION_API_KEY else "nominatim",
        "mandi_prices": _mandi_reachable(),
        "soil": bool(EE_SERVICE_KEY),
        # Retrieval is served from the local vector store; Bedrock is optional.
        "knowledge_base": _documents_loaded() or bool(
            KNOWLEDGE_BASE_ID and AWS_ACCESS_KEY and AWS_SECRET_KEY
        ),
        "farmer_profiles": bool(DATABASE_URL),
    }


# Largest upload accepted on /agent/media. The container has 1 GiB and reads the
# whole body into memory before touching it, so this is the difference between a
# rejected request and a restarted instance.
MAX_UPLOAD_BYTES = int(_get("MAX_UPLOAD_MB", "12")) * 1024 * 1024
