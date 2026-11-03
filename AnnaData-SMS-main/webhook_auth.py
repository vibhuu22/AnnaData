"""Authenticate raw webhook bytes before trusting a claimed farmer identity."""
import hashlib
import hmac
import re
import time


def verify_sms(body: bytes, signature: str, timestamp: str, secret: str,
               *, now: float | None = None, tolerance: int = 300) -> bool:
    if not secret or not re.fullmatch(r"[0-9a-f]{64}", signature or "") or not timestamp:
        return False
    try:
        sent = int(timestamp)
    except (ValueError, TypeError):
        return False
    if abs((time.time() if now is None else now) - sent) > tolerance:
        return False
    expected = hmac.new(secret.encode(), body + timestamp.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_whatsapp(body: bytes, signature: str, secret: str) -> bool:
    if not secret or not re.fullmatch(r"sha256=[0-9a-f]{64}", signature or ""):
        return False
    expected = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
