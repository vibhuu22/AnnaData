"""
A guest's questions follow them onto the number they confirm.

The web app tells a guest that confirming their number keeps their questions
saved. profile_store.claim_guest keeps that promise, in one transaction, and it
is the one part of the guest work that only a real database can check: an
UPDATE ... FROM that silently matches nothing, a crops merge that turns NULL
into nothing at all, or a guest row left behind, would each pass every test
that stubs the database out.

The rules checked here:
  - every guest message moves, and nobody else's does
  - the guest's facts fill gaps but never overwrite what the farmer already
    told us (a district from SMS last month beats one guessed from one question)
  - crops are merged, because a farmer grows more than one thing
  - coordinates move together with their location text, or not at all
  - the guest row is gone afterwards, and claiming twice moves nothing

No model calls. Needs DATABASE_URL; uses ids reserved for this test and removes
them afterwards.

Run: python eval/test_claim_guest.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import farmer_account
import feedback
import profile_store

GUEST = "guest:3f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b90"
NEW = "+919999000071"        # a farmer whose first contact is this sign-in
KNOWN = "+919999000072"      # a farmer we already know from SMS
OTHER = "guest:8f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b91"

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


def cleanup():
    with db.connection() as conn:
        for uid in (GUEST, OTHER, NEW, KNOWN):
            conn.execute("DELETE FROM messages WHERE user_id = %s", (uid,))
            conn.execute("DELETE FROM farmers WHERE user_id = %s", (uid,))


def seed_guest(uid, crops, district, lat=None):
    with db.connection() as conn:
        conn.execute(
            """INSERT INTO farmers (user_id, channel, crops, district, state,
                                    location_text, latitude, longitude)
               VALUES (%s, 'web', %s, %s, 'Haryana', %s, %s, %s)""",
            (uid, crops, district, district if lat else None, lat, 76.9 if lat else None),
        )
    profile_store.log_message(uid, "inbound", "Mere gehun me peela rog")
    profile_store.log_message(uid, "outbound", "Propiconazole 25% EC ...")


def row(uid):
    with db.connection() as conn:
        return conn.execute(
            """SELECT district, state, crops, location_text, latitude
                 FROM farmers WHERE user_id = %s""", (uid,)).fetchone()


def count(uid):
    with db.connection() as conn:
        return conn.execute("SELECT count(*) FROM messages WHERE user_id = %s",
                            (uid,)).fetchone()[0]


if not db.init():
    print("Database unavailable; cannot run")
    sys.exit(1)
feedback.init()   # what app.py does at startup; adds messages.session_id

cleanup()
try:
    print("A farmer whose first contact is this sign-in")
    seed_guest(GUEST, ["wheat"], "Karnal", lat=29.69)
    seed_guest(OTHER, ["cotton"], "Hisar")
    farmer_account.ensure(NEW, channel="web")
    check("both guest messages move", profile_store.claim_guest(GUEST, NEW), 2)
    check("and are now the farmer's", count(NEW), 2)
    check("the guest has none left", count(GUEST), 0)
    check("another guest's messages are untouched", count(OTHER), 2)
    district, state, crops, place, lat = row(NEW)
    check("the crop from the question is on the account", crops, ["wheat"])
    check("district fills the gap", district, "Karnal")
    check("location moves with its coordinates", (place, lat), ("Karnal", 29.69))
    check("the guest row is gone", row(GUEST), None)
    check("claiming again moves nothing", profile_store.claim_guest(GUEST, NEW), 0)
    check("and the account is unchanged by it", row(NEW)[2], ["wheat"])

    print("\nA farmer we already know")
    with db.connection() as conn:
        conn.execute(
            """INSERT INTO farmers (user_id, channel, crops, district, state,
                                    location_text, latitude, longitude)
               VALUES (%s, 'sms', %s, 'Paschim Medinipur', 'West Bengal',
                       'Kharagpur', 22.33, 87.32)""",
            (KNOWN, ["rice"]),
        )
    profile_store.log_message(KNOWN, "inbound", "Dhan me paani kab dein?")
    farmer_account.ensure(KNOWN, channel="web")
    seed_guest(GUEST, ["wheat", "rice"], "Karnal", lat=29.69)
    check("the guest's two messages move", profile_store.claim_guest(GUEST, KNOWN), 2)
    check("joining the farmer's own", count(KNOWN), 3)
    district, state, crops, place, lat = row(KNOWN)
    check("crops are merged, each once", sorted(crops), ["rice", "wheat"])
    check("the district they told us is kept", district, "Paschim Medinipur")
    check("so is the state", state, "West Bengal")
    check("and their own location, not the guess", (place, lat), ("Kharagpur", 22.33))

    print("\nWhat claim_guest refuses to do")
    check("a phone number is not a guest", profile_store.claim_guest(KNOWN, NEW), 0)
    check("so the farmer's messages stayed put", count(KNOWN), 3)
    check("a guest with nothing to claim is fine", profile_store.claim_guest(OTHER.replace("8f", "9f"), NEW), 0)
finally:
    cleanup()

db.close()
print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)
