"""
Configuration for the SMS bridge.

Supports all three SMS Gateway for Android modes:
  cloud   - api.sms-gate.app (default; no LAN or ngrok needed)
  local   - the device's own HTTP server on your LAN
  private - your own self-hosted gateway server
"""
import os
from dotenv import load_dotenv

load_dotenv()


def _get(name, default=None):
    v = os.getenv(name, default)
    return v.strip() if isinstance(v, str) else v


SMS_MODE = (_get("SMS_MODE", "cloud") or "cloud").lower()

CLOUD_BASE_URL = _get("CLOUD_BASE_URL", "https://api.sms-gate.app/3rdparty/v1")
PRIVATE_BASE_URL = _get("PRIVATE_BASE_URL")
DEVICE_IP = _get("DEVICE_IP")
DEVICE_PORT = _get("DEVICE_PORT", "8080")

USERNAME = _get("APP_USERNAME")
PASSWORD = _get("PASSWORD")

_AI_ENDPOINT_RAW = _get("AI_ENDPOINT")     # e.g. https://api.example.com/agent
PUBLIC_URL = _get("PUBLIC_URL") or _get("NGROK_URL")  # where this bridge is reachable


def _normalise_endpoint(value: str | None) -> str | None:
    """Accept a bare host or a full URL and return a full /agent URL.

    Deploy dashboards hand you a hostname, not a URL, so a pasted value often
    arrives as "annadata-backend.onrender.com" with no scheme and no path.
    """
    if not value:
        return None
    value = value.strip().rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    if not value.endswith("/agent"):
        value += "/agent"
    return value


AI_ENDPOINT = _normalise_endpoint(_AI_ENDPOINT_RAW)

DEDUP_TTL = int(_get("DEDUP_TTL", "600"))
AI_TIMEOUT = int(_get("AI_TIMEOUT", "150"))
# Attempts at the backend per incoming SMS. The first can be spent waking a
# sleeping free-tier instance, so more than one matters in practice.
AI_ATTEMPTS = int(_get("AI_ATTEMPTS", "2"))
SMS_TIMEOUT = int(_get("SMS_TIMEOUT", "30"))
MAX_SMS_CHARS = int(_get("MAX_SMS_CHARS", "480"))    # hard character ceiling
# Billed segments. Latin fits 153 chars per segment, Devanagari only 67, so
# this is the cap that actually controls cost across languages.
MAX_SMS_SEGMENTS = int(_get("MAX_SMS_SEGMENTS", "4"))
WEBHOOK_PATH = _get("WEBHOOK_PATH", "/incoming-sms")


def public_url() -> str | None:
    """PUBLIC_URL with a scheme, however it was pasted."""
    if not PUBLIC_URL:
        return None
    url = PUBLIC_URL.strip().rstrip("/")
    return url if url.startswith(("http://", "https://")) else "https://" + url


def base_url() -> str:
    """Gateway API base URL for the configured mode."""
    if SMS_MODE == "cloud":
        return CLOUD_BASE_URL.rstrip("/")
    if SMS_MODE == "private":
        if not PRIVATE_BASE_URL:
            raise RuntimeError("SMS_MODE=private requires PRIVATE_BASE_URL")
        return PRIVATE_BASE_URL.rstrip("/") + "/3rdparty/v1"
    if SMS_MODE == "local":
        if not DEVICE_IP:
            raise RuntimeError("SMS_MODE=local requires DEVICE_IP")
        return f"http://{DEVICE_IP}:{DEVICE_PORT}"
    raise RuntimeError(f"Unknown SMS_MODE: {SMS_MODE!r} (use cloud, local or private)")


def messages_url() -> str:
    """Local mode exposes /message; cloud and private expose /messages."""
    return f"{base_url()}/message" if SMS_MODE == "local" else f"{base_url()}/messages"


def webhooks_url() -> str:
    return f"{base_url()}/webhooks"


def validate() -> list[str]:
    """Return a list of configuration problems, empty if healthy."""
    problems = []
    if not USERNAME or not PASSWORD:
        problems.append("APP_USERNAME / PASSWORD not set (gateway credentials)")
    if not AI_ENDPOINT:
        problems.append("AI_ENDPOINT not set (backend /agent URL)")
    try:
        base_url()
    except RuntimeError as e:
        problems.append(str(e))
    return problems
