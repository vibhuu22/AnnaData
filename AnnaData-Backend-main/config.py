"""
Central configuration and feature detection.

Every external integration is optional except Gemini. If a key is missing the
corresponding tool reports itself unavailable and the agent routes around it,
rather than raising at import time and taking the whole service down.
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if value is not None:
        value = value.strip()
    return value or None


# --- Required ---
GEMINI_API_KEY = _get("GEMINI_API_KEY")

# --- Optional integrations ---
LOCATION_API_KEY = _get("LOCATION_API_KEY")      # Google Maps Geocoding
GOV_API_KEY = _get("GOV_API_KEY")                # data.gov.in mandi prices
EE_SERVICE_KEY = _get("EE_SERVICE_KEY")          # Earth Engine soil data
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
CONTEXT_MESSAGES = int(_get("CONTEXT_MESSAGES", "10"))
CONTEXT_TTL_HOURS = int(_get("CONTEXT_TTL_HOURS", "48"))
# How long before a farmer who ignored the location question is asked again.
LOCATION_ASK_COOLDOWN_HOURS = int(_get("LOCATION_ASK_COOLDOWN_HOURS", "24"))

# --- Deployment ---
FRONTEND_URL = _get("FRONTEND_URL")
CORS_ORIGINS = _get("CORS_ORIGINS")              # comma-separated, optional

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

# Retries inside one model before failing over. Kept low on purpose: the client
# backs off 2s, 4s, 8s, 16s, 32s by default, which spends a minute stalling on a
# quota error when another model would have answered immediately.
LLM_MAX_RETRIES = int(_get("LLM_MAX_RETRIES", "1"))
# The final model in the chain has no fallback behind it, so it gets a larger
# budget to ride out a transient 503.
LLM_LAST_RESORT_RETRIES = int(_get("LLM_LAST_RESORT_RETRIES", "3"))

# --- Tunables ---
MANDI_MAX_RECORDS = int(_get("MANDI_MAX_RECORDS", "80"))
HTTP_TIMEOUT = int(_get("HTTP_TIMEOUT", "20"))
# data.gov.in is markedly slower than the other upstreams and returns 502 under
# load, so it gets its own budget and is retried rather than failing the answer.
GOV_API_TIMEOUT = int(_get("GOV_API_TIMEOUT", "45"))
GOV_API_ATTEMPTS = int(_get("GOV_API_ATTEMPTS", "2"))


def feature_status() -> dict[str, bool]:
    """Which integrations are configured. Surfaced on /health."""
    return {
        "gemini": bool(GEMINI_API_KEY),
        "geocoding": bool(LOCATION_API_KEY),
        "mandi_prices": bool(GOV_API_KEY),
        "soil": bool(EE_SERVICE_KEY),
        "knowledge_base": bool(
            KNOWLEDGE_BASE_ID and AWS_ACCESS_KEY and AWS_SECRET_KEY
        ),
        "farmer_profiles": bool(DATABASE_URL),
    }
