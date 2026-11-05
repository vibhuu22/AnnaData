"""
Sending an SMS from the backend.

The bridge in AnnaData-SMS-main already talks to the handset gateway, but it is
a separate service and the sign-in path should not depend on a second hop being
up. The gateway's API is one authenticated POST, so the backend calls it
directly with the same credentials.

THE SEAM. Everything here goes through `send`, and `send` picks a transport from
configuration. Today that is the Android handset on sms-gate.app, which is free
and already running. When one-time codes move to a registered DLT sender, that
is a new branch in `send` and an environment variable - not a change anywhere
else in the codebase. That was the point of putting it behind a function.

With no gateway credentials configured, `send` prints the message instead of
transmitting it. That is what makes local development possible without a SIM,
and it is loud about what it is doing so it can never be mistaken for a
delivery.
"""
from __future__ import annotations

import requests

import config


# One segment of GSM-7 is 153 characters. A code that arrives as two messages
# costs twice as much and can arrive out of order, so this stays short - and in
# plain Latin letters, because one Devanagari character turns the whole message
# into UCS-2 and cuts a segment to 67 characters.
#
# WORDED LIKE A TEXT FROM A PERSON, NOT LIKE A BANK'S OTP. The codes go out from
# an ordinary 10-digit SIM, not a registered business sender, and Indian
# networks refuse messages from such SIMs that look commercial. The first
# wording - "{code} is your AnnaData sign-in code. It expires in 10 minutes. Do
# not share it with anyone." - came back from the gateway phone as Failed,
# while conversational answers from the same SIM went through. "OTP", "code",
# "sign-in", "verify" and "do not share" are the words those filters key on, so
# none of them is used. eval/test_code_message.py holds this to all of the
# above.
def code_message(code: str) -> str:
    minutes = max(1, config.OTP_TTL // 60)
    return (
        f"AnnaData: {code} - yeh number website par daalein. "
        f"{minutes} minute tak chalega."
    )


def _send_via_gateway(phone: str, text: str) -> bool:
    """POST to the SMS Gateway for Android cloud API."""
    try:
        response = requests.post(
            config.sms_messages_url(),
            json={"phoneNumbers": [phone], "textMessage": {"text": text}},
            auth=(config.SMS_GATEWAY_USER, config.SMS_GATEWAY_PASSWORD),
            timeout=config.SMS_SEND_TIMEOUT,
        )
        if response.status_code in (200, 201, 202):
            return True
        print(f"SMS gateway refused ({response.status_code}): {response.text[:200]}")
        return False
    except Exception as e:
        # The handset is one phone. Off, out of balance or off the network all
        # arrive here, and the caller must be able to say "we could not send it"
        # rather than claim a code is on its way.
        print(f"SMS gateway unreachable: {e}")
        return False


def _send_to_console(phone: str, text: str) -> bool:
    print("=" * 62)
    print(f"  NO SMS GATEWAY CONFIGURED - not sent to {phone}")
    print(f"  {text}")
    print("=" * 62)
    return True


def transport() -> str:
    """Which transport is live. Reported by /health so it is never a guess."""
    if config.sms_gateway_ready():
        return "android-gateway"
    return "console"


def send(phone: str, text: str) -> bool:
    if config.sms_gateway_ready():
        return _send_via_gateway(phone, text)
    return _send_to_console(phone, text)


def send_code(phone: str, code: str) -> bool:
    return send(phone, code_message(code))
