"""
Who the caller is.

Until now `user_id` arrived in the request body and was believed. On SMS that is
sound - the gateway reports the sender and a farmer cannot forge the network's
idea of their own number. On the web it was not sound at all: anyone could send
another farmer's phone number and have the agent recall that farmer's profile
and recent conversation into an answer, then write into their message log. With
one farmer and no public URL that was theoretical. With a public URL it is not.

So identity is proved once, by a code sent to the phone, and carried afterwards
in a signed token. The endpoints take the farmer's id from the token and ignore
anything the body says about it.

WHY A PHONE NUMBER AND NOT AN EMAIL. `user_id` has always been the phone number
on SMS. Signing in with the same number produces the same key, so a farmer who
signs up in a browser and later texts the gateway is one farmer with one history,
not two rows that never learn about each other. An email login would have forked
the identity space of a product whose main channel is SMS.

THE CODE GOES OUT THROUGH THE EXISTING HANDSET GATEWAY. That is a deliberate,
temporary choice: it is free, it already works, and it avoids registering DLT
templates for a service that has not yet been piloted. It has two honest costs.
The gateway is one Android phone, so if it is off nobody can sign in - and a
login that fails is worse than an answer that fails. And routing one-time codes
through a handset intended for person-to-person messaging is a greyer area than
the free-form advisory traffic it was chosen for. Both are accepted until the
move to a registered DLT sender, which is planned as one change rather than a
drip. `sms_out.py` is where the sender swaps.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

import config
import db


# --- Phone numbers --------------------------------------------------------

# India only, for now, and deliberately strict. A number that is nearly right is
# a code sent to a stranger's handset, at the founder's expense.
_DIGITS = re.compile(r"[^\d+]")


def normalise_phone(raw: str | None) -> str | None:
    """A phone number in E.164, or None if it is not one we can send to.

    Accepts the forms a farmer actually types: 9876543210, 09876543210,
    +91 98765 43210, 91-9876543210. Anything else is refused rather than
    guessed at.
    """
    if not raw:
        return None
    value = _DIGITS.sub("", str(raw).strip())
    if value.startswith("+"):
        value = value[1:]
        if value.startswith("91"):
            value = value[2:]
    elif value.startswith("91") and len(value) == 12:
        value = value[2:]
    elif value.startswith("0") and len(value) == 11:
        value = value[1:]

    # An Indian mobile number is ten digits and starts 6, 7, 8 or 9. Landlines
    # cannot receive an SMS, so they are not a sign-in method.
    if len(value) != 10 or value[0] not in "6789":
        return None
    return "+91" + value


def mask_phone(phone: str | None) -> str:
    """For logs and for the screen: +91 ***** 43210."""
    if not phone or len(phone) < 4:
        return "unknown"
    return f"{phone[:3]} ***** {phone[-5:]}"


# --- One-time codes -------------------------------------------------------

def _secret() -> bytes:
    return (config.AUTH_SECRET or "").encode("utf-8")


def _hash_code(phone: str, code: str) -> str:
    """Keyed hash of a code, bound to the phone it was issued for.

    Binding to the phone means a hash lifted from one row cannot be replayed
    against another, even if two farmers are issued the same six digits.
    """
    return hmac.new(_secret(), f"{phone}:{code}".encode("utf-8"), hashlib.sha256).hexdigest()


def new_code() -> str:
    """Six digits from a cryptographic source, never `random`."""
    return f"{secrets.randbelow(1_000_000):06d}"


class CodeRequest:
    """What happened when a code was asked for."""

    __slots__ = ("ok", "code", "reason", "retry_after")

    def __init__(self, ok, code=None, reason=None, retry_after=0):
        self.ok = ok
        self.code = code
        self.reason = reason
        self.retry_after = retry_after


def issue_code(phone: str) -> CodeRequest:
    """Mint and store a code for this phone, unless one was just sent.

    The cooldown is not politeness. Every code is a real SMS from the founder's
    own SIM, so an unthrottled endpoint is a way to drain the handset's balance
    and to use it to harass a stranger.
    """
    if not db.is_available():
        return CodeRequest(False, reason="database unavailable")

    now = datetime.now(timezone.utc)
    try:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT sent_at, sent_count FROM login_codes WHERE phone = %s",
                (phone,),
            ).fetchone()

            if row:
                sent_at, sent_count = row
                since = (now - sent_at).total_seconds()
                if since < config.OTP_RESEND_COOLDOWN:
                    return CodeRequest(
                        False,
                        reason="a code was just sent",
                        retry_after=int(config.OTP_RESEND_COOLDOWN - since),
                    )
                # Sends within one window, not guesses. Someone walking through
                # numbers pays this before the SIM does.
                if sent_count >= config.OTP_MAX_SENDS and since < config.OTP_SEND_WINDOW:
                    return CodeRequest(
                        False,
                        reason="too many codes requested; try later",
                        retry_after=int(config.OTP_SEND_WINDOW - since),
                    )

            code = new_code()
            expires = now + timedelta(seconds=config.OTP_TTL)
            conn.execute(
                """
                INSERT INTO login_codes (phone, code_hash, expires_at, attempts, sent_at, sent_count)
                VALUES (%s, %s, %s, 0, %s, 1)
                ON CONFLICT (phone) DO UPDATE SET
                    code_hash  = EXCLUDED.code_hash,
                    expires_at = EXCLUDED.expires_at,
                    attempts   = 0,
                    sent_at    = EXCLUDED.sent_at,
                    sent_count = CASE
                        WHEN login_codes.sent_at > %s THEN login_codes.sent_count + 1
                        ELSE 1
                    END
                """,
                (phone, _hash_code(phone, code), expires, now,
                 now - timedelta(seconds=config.OTP_SEND_WINDOW)),
            )
            return CodeRequest(True, code=code)
    except Exception as e:
        print(f"Could not issue a login code for {mask_phone(phone)}: {e}")
        return CodeRequest(False, reason="could not issue a code")


def check_code(phone: str, code: str) -> tuple[bool, str | None]:
    """(accepted, reason). A used or expired code is destroyed either way."""
    if not db.is_available():
        return False, "database unavailable"
    if not code or not code.strip().isdigit():
        return False, "that code is not six digits"

    given = code.strip()
    now = datetime.now(timezone.utc)
    try:
        with db.connection() as conn:
            row = conn.execute(
                "SELECT code_hash, expires_at, attempts FROM login_codes WHERE phone = %s",
                (phone,),
            ).fetchone()
            if not row:
                return False, "ask for a code first"

            code_hash, expires_at, attempts = row
            if now > expires_at:
                conn.execute("DELETE FROM login_codes WHERE phone = %s", (phone,))
                return False, "that code has expired"
            if attempts >= config.OTP_MAX_ATTEMPTS:
                conn.execute("DELETE FROM login_codes WHERE phone = %s", (phone,))
                return False, "too many wrong tries; ask for a new code"

            # compare_digest, not ==, so the time taken says nothing about how
            # much of the code was right.
            if not hmac.compare_digest(code_hash, _hash_code(phone, given)):
                conn.execute(
                    "UPDATE login_codes SET attempts = attempts + 1 WHERE phone = %s",
                    (phone,),
                )
                left = config.OTP_MAX_ATTEMPTS - attempts - 1
                return False, (f"that code is wrong, {left} tries left" if left > 0
                               else "too many wrong tries; ask for a new code")

            # Correct. One code, one sign-in.
            conn.execute("DELETE FROM login_codes WHERE phone = %s", (phone,))
            return True, None
    except Exception as e:
        print(f"Could not check a login code for {mask_phone(phone)}: {e}")
        return False, "could not check that code"


# --- Tokens ---------------------------------------------------------------

def issue_token(user_id: str, token_version: int = 0) -> str:
    """A signed token naming the farmer. Stateless apart from token_version."""
    import jwt

    now = int(time.time())
    return jwt.encode(
        {
            "sub": user_id,
            "ver": token_version,
            "iat": now,
            "exp": now + config.SESSION_TTL,
        },
        config.AUTH_SECRET,
        algorithm="HS256",
    )


def read_token(token: str | None) -> str | None:
    """The farmer's id from a token, or None if it does not hold up.

    Every failure is the same None. Telling a caller whether a token was expired,
    forged or simply malformed tells an attacker which half of their guess was
    right.
    """
    if not token or not config.AUTH_SECRET:
        return None
    import jwt

    try:
        claims = jwt.decode(token, config.AUTH_SECRET, algorithms=["HS256"])
    except Exception:
        return None

    user_id = claims.get("sub")
    if not user_id:
        return None

    # token_version is how a farmer signs out everywhere: bump the column and
    # every token already issued stops decoding to a user.
    if db.is_available():
        try:
            with db.connection() as conn:
                row = conn.execute(
                    "SELECT token_version FROM farmers WHERE user_id = %s", (user_id,)
                ).fetchone()
            if row is not None and int(row[0] or 0) != int(claims.get("ver", 0)):
                return None
        except Exception as e:
            # A database blip must not sign everyone out. The signature is still
            # valid and unexpired; only revocation is unavailable for a moment.
            print(f"Could not check token version, accepting the signature: {e}")

    return user_id
