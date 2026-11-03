"""
Which backend replies the SMS bridge should wait out, and which it should drop.

A farmer texted and got nothing back. The backend was healthy - it answered a
direct request in 0.8 seconds - but the bridge's own health check reported
`agent backend returned HTTP 429`, because a free-tier instance that is still
spinning up is answered by the platform's edge, not by the service.

The bridge already had a retry loop built for exactly this, waiting at roughly
0, 20, 60 and 120 seconds against a cold start of about 140. It only triggered
on 5xx. A 429 is 4xx, so it fell through to `return None`, no reply was sent,
and the message was lost. Silence is this service's worst failure because it is
indistinguishable from working, and nobody finds out until a farmer stops
texting.

This cannot be a case in cases.yaml: there is no language in it, and the model
never sees the status code. It is classification logic, so it is checked here,
on hand-written inputs, at no model cost.

Run: python eval/test_retry.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "AnnaData-SMS-main"))

import config

failures = []


def check(status: int, expected: bool, why: str) -> None:
    actual = config.is_waking(status)
    verdict = "ok" if actual == expected else "FAIL"
    if actual != expected:
        failures.append(f"{status}: expected is_waking={expected}, got {actual} - {why}")
    print(f"  [{verdict}] {status:>3} -> retry={actual!s:<5} {why}")


print("Statuses that mean 'the backend is still waking' (must retry)")
# The regression this test exists for. A cold free-tier instance is answered by
# the edge, which rate-limits rather than reporting the service as unavailable.
check(429, True, "edge rate-limits while the container starts - the lost-message bug")
check(408, True, "a proxy ahead of the service timed out waiting for it")
check(500, True, "service errored, may be mid-boot")
check(502, True, "no upstream yet - the classic cold start")
check(503, True, "explicitly unavailable, which is what waking looks like")
check(504, True, "gateway gave up waiting for a slow boot")

print("\nStatuses that will not improve by asking again (must not retry)")
# Failing fast here is deliberate. Retrying these spends up to three waits and
# roughly 200 seconds to arrive at the same refusal, while the farmer waits.
check(401, False, "bridge is not trusted; BRIDGE_TOKEN is wrong or unset")
check(403, False, "forbidden; asking again does not grant permission")
check(400, False, "malformed payload - a bug on our side, not a cold start")
check(404, False, "wrong AI_ENDPOINT; it will stay wrong")
check(422, False, "payload rejected by validation")

print("\nBoundaries")
check(499, False, "last 4xx that is not a known waking signal")
check(599, True, "still a server error")

print()
if failures:
    for f in failures:
        print(f"FAIL {f}")
    print(f"\n{len(failures)} failed")
    sys.exit(1)

print("All retry-classification checks passed")
