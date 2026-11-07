"""Sign-in codes sent and checked by MSG91's OTP widget.

The browser runs the widget (its own UI, AnnaData's screens): it asks MSG91 to
send a code to the farmer's number, the farmer types it, and MSG91 hands the
browser an access token. That token proves nothing until the backend has asked
MSG91 about it - so `verified_phone` posts it to MSG91 with the account's auth
key and takes the phone number from MSG91's answer.

THE NUMBER COMES FROM MSG91, NEVER FROM THE BROWSER. A browser could verify its
own number and then claim to be someone else's; only the identifier MSG91 says
it verified is signed in. An answer without a usable Indian mobile number is a
refusal.

Off until MSG91_AUTHKEY is set (Cloud Run). The SIM-gateway codes in
sms_out.py keep working either way.
"""
from __future__ import annotations

import requests

import auth
import config

VERIFY_URL = "https://control.msg91.com/api/v5/widget/verifyAccessToken"


def enabled() -> bool:
    return bool(config.MSG91_AUTHKEY)


def verified_phone(access_token: str) -> tuple[str | None, str | None]:
    """(phone, None) for a token MSG91 confirms, or (None, why not).

    MSG91 can answer HTTP 200 with an error inside, so the body decides, not
    the status code.
    """
    if not enabled():
        return None, "MSG91 is not configured"
    token = (access_token or "").strip()
    if not token or len(token) > 4096:
        return None, "no access token"
    try:
        response = requests.post(
            VERIFY_URL,
            json={"authkey": config.MSG91_AUTHKEY, "access-token": token},
            headers={"Accept": "application/json"},
            timeout=config.HTTP_TIMEOUT,
        )
        body = response.json()
    except Exception as e:  # network, or not JSON
        print(f"MSG91 token check failed: {type(e).__name__}: {e}")
        return None, "could not reach MSG91"
    if response.status_code != 200 or str(body.get("type", "")).lower() != "success":
        # Logged without the token or the key.
        print(f"MSG91 refused the token: HTTP {response.status_code} {str(body.get('message'))[:120]}")
        return None, "that code could not be confirmed"
    phone = auth.normalise_phone(str(body.get("message") or ""))
    if not phone:
        print("MSG91 confirmed a token but returned no mobile number")
        return None, "that code could not be confirmed"
    return phone, None
