"""
Signing in with MSG91's widget: the number signed in is the one MSG91 verified.

The browser holds an access token from the widget. The backend asks MSG91 about
it and signs in the identifier MSG91 returns - never a number the browser names,
or anyone could verify their own phone and then claim someone else's. MSG91 can
answer HTTP 200 with an error inside, so the body decides.

MSG91 is stubbed: no network, no auth key. Needs a scratch DATABASE_URL for the
sign-in itself; without one, only the token checks run.

Run: python eval/test_msg91.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GEMINI_API_KEY", "x")

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


import config  # noqa: E402
import msg91  # noqa: E402

sent = []


class Reply:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def answer(status, body):
    def post(url, json=None, **kw):
        sent.append((url, json))
        return Reply(status, body)
    msg91.requests.post = post


print("Without an auth key")
config.MSG91_AUTHKEY = None
check("off", msg91.enabled(), False)
check("nothing is checked", msg91.verified_phone("tok")[0], None)

print("\nWith one")
config.MSG91_AUTHKEY = "test-key"
answer(200, {"type": "success", "message": "919876543210"})
check("the number MSG91 verified", msg91.verified_phone("tok-1"), ("+919876543210", None))
check("asked with the key and the token, as MSG91 names them",
      sent[-1], (msg91.VERIFY_URL, {"authkey": "test-key", "access-token": "tok-1"}))
answer(200, {"type": "error", "message": "invalid token"})
check("an error inside a 200 is a refusal", msg91.verified_phone("tok-2")[0], None)
answer(200, {"type": "success", "message": "farmer@example.com"})
check("a success without a mobile number is a refusal", msg91.verified_phone("tok-3")[0], None)
answer(401, {"type": "error", "message": "authkey"})
check("a refused key is a refusal", msg91.verified_phone("tok-4")[0], None)
check("an empty token is never sent", (msg91.verified_phone("  ")[0], len(sent)), (None, 4))

try:
    import db
    from fastapi.testclient import TestClient
    import app as appmod
    ready = bool(os.getenv("DATABASE_URL")) and (db.init() or db.is_available())
except Exception as e:
    print(f"\nBackend not importable here ({type(e).__name__}); skipping sign-in")
    ready = False

if ready:
    print("\nSigning in")
    web = TestClient(appmod.app)
    phone = "+919999000091"
    answer(200, {"type": "success", "message": "919999000091"})
    r = web.post("/auth/verify-widget", json={"access_token": "tok-5", "phone": "+919999000099"})
    check("signed in", r.status_code, 200)
    check("as the number MSG91 verified, not the one the browser sent",
          appmod.auth.read_token(r.json().get("token")), phone)
    answer(200, {"type": "error", "message": "expired"})
    check("a refused token: 401", web.post("/auth/verify-widget", json={"access_token": "x"}).status_code, 401)
    config.MSG91_AUTHKEY = None
    check("not set up: 503", web.post("/auth/verify-widget", json={"access_token": "x"}).status_code, 503)
    with db.connection() as conn:
        conn.execute("DELETE FROM farmers WHERE user_id = %s", (phone,))

print()
if failures:
    print(f"{len(failures)} failed: {failures}")
    sys.exit(1)
print("all passed")
os._exit(0)
