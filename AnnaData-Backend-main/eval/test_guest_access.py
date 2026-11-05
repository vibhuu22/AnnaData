"""
Who may ask without signing in, and how often.

The web app now answers a first question before asking for a phone number,
which reopens an unauthenticated endpoint that spends model quota on every call
- the thing the sign-in work existed to close. What keeps it closed is in
guest_access.py, and every rule there fails silently if it is wrong: a guest id
that can carry a phone number writes into a real farmer's row, an address limit
that counts refused requests locks a whole village out, and a limit that never
triggers just runs up the bill. None of it involves a model, so it is checked
here with a fake clock and no database.

Run: python eval/test_guest_access.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import guest_access as ga

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


GOOD = "3f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b90"

print("Which strings may become a guest's storage key")
check("a browser UUID is accepted", ga.guest_user_id(GOOD), "guest:" + GOOD)
check("case and spaces are normalised", ga.guest_user_id("  " + GOOD.upper() + " "), "guest:" + GOOD)
# The rule that matters most: a phone number must never become a guest key,
# or a guest could write into a real farmer's conversation.
check("a phone number is refused", ga.guest_user_id("+919876543210"), None)
check("an already-prefixed id is refused", ga.guest_user_id("guest:" + GOOD), None)
check("a non-v4 UUID is refused", ga.guest_user_id("3f2a9c1e-5b7d-1e8a-9c21-7d4e5f6a8b90"), None)
check("empty is refused", ga.guest_user_id(""), None)
check("None is refused", ga.guest_user_id(None), None)
check("SQL-ish junk is refused", ga.guest_user_id(GOOD + "'; DROP TABLE farmers;--"), None)
check("guest keys are recognised", ga.is_guest("guest:" + GOOD), True)
check("phone numbers are not guests", ga.is_guest("+919876543210"), False)

print("\nThe caller's address")
check("first forwarded entry is the browser", ga.client_ip("203.0.113.7, 10.0.0.1", "10.0.0.9"), "203.0.113.7")
check("no header falls back to the socket peer", ga.client_ip(None, "127.0.0.1"), "127.0.0.1")
check("nothing at all is 'unknown', not a crash", ga.client_ip("", None), "unknown")

print("\nOne guest, one hour")
clock = Clock()
lim = ga.GuestLimiter(per_guest=3, per_ip=100, daily_cap=1000, clock=clock)
results = [lim.check("guest:a", "1.1.1.1")[0] for _ in range(3)]
check("three questions are admitted", results, [True, True, True])
ok, wait, which = lim.check("guest:a", "1.1.1.1")
check("the fourth is refused", ok, False)
check("and the refusal is the guest limit", which, "guest")
check("with a retry time within the hour", 0 < wait <= 3600, True)
check("a different guest on the same address still gets in", lim.check("guest:b", "1.1.1.1")[0], True)
clock.now += 3601
check("an hour later the first guest may ask again", lim.check("guest:a", "1.1.1.1")[0], True)

print("\nMany guests behind one address")
clock = Clock()
lim = ga.GuestLimiter(per_guest=10, per_ip=4, daily_cap=1000, clock=clock)
admitted = [lim.check(f"guest:{i}", "100.64.0.1")[0] for i in range(4)]
check("four different guests are admitted", admitted, [True] * 4)
ok, _, which = lim.check("guest:new", "100.64.0.1")
check("a fifth on the same address is refused", (ok, which), (False, "address"))
check("a guest on another address is unaffected", lim.check("guest:new", "100.64.0.2")[0], True)

print("\nRefused questions are not counted")
# Otherwise a farmer who hits the limit and keeps tapping send pushes their own
# unlock time further away with every tap.
clock = Clock()
lim = ga.GuestLimiter(per_guest=1, per_ip=100, daily_cap=1000, clock=clock)
lim.check("guest:a", "1.1.1.1")
for _ in range(20):
    lim.check("guest:a", "1.1.1.1")
clock.now += 3601
check("twenty refused retries do not extend the wait", lim.check("guest:a", "1.1.1.1")[0], True)
# And a refusal by one window must not have been recorded in the others.
clock = Clock()
lim = ga.GuestLimiter(per_guest=1, per_ip=2, daily_cap=1000, clock=clock)
lim.check("guest:a", "9.9.9.9")
lim.check("guest:a", "9.9.9.9")  # refused by the guest limit
check("a guest-limit refusal did not use up the address limit",
      lim.check("guest:b", "9.9.9.9")[0], True)

print("\nThe daily ceiling")
clock = Clock()
lim = ga.GuestLimiter(per_guest=100, per_ip=100, daily_cap=2, clock=clock)
lim.check("guest:a", "1.1.1.1")
lim.check("guest:b", "2.2.2.2")
ok, _, which = lim.check("guest:c", "3.3.3.3")
check("the cap applies across every guest and address", (ok, which), (False, "daily"))
clock.now += 86401
check("and lifts after a day", lim.check("guest:c", "3.3.3.3")[0], True)

print("\nA limit of zero closes guest questions entirely")
lim = ga.GuestLimiter(per_guest=0, per_ip=100, daily_cap=100, clock=Clock())
check("nothing is admitted", lim.check("guest:a", "1.1.1.1")[0], False)

print("\nEvery refusal has words for the farmer")
check("all three limits have a message",
      sorted(ga.REFUSALS), ["address", "daily", "guest"])
check("and each one tells them how to keep asking",
      all("Confirm your phone number" in m for m in ga.REFUSALS.values()), True)

print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)
