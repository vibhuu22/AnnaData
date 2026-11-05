"""
A participant id on the admin dashboard must not be a phone number in disguise.

India has few enough mobile numbers that a plain hash of each can be computed
in hours, so an unkeyed hash is reversible. The id is an HMAC under a secret.

Run: python eval/test_pseudonym.py
"""
import hashlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["ANALYTICS_PSEUDONYM_KEY"] = "test-key-one"

import metrics_store as ms

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")


phone = "+919876543210"
plain = hashlib.sha256(phone.encode()).hexdigest()[:20]
pid = ms.participant_id(phone)
check("not the plain hash anyone could compute from the number", pid == plain, False)
check("the same farmer however the number is written", ms.participant_id("09876543210"), pid)
check("stable for the same key", ms.participant_id(phone), pid)
os.environ["ANALYTICS_PSEUDONYM_KEY"] = "test-key-two"
check("a different key gives a different id", ms.participant_id(phone) == pid, False)

print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)
