"""
When a short message is an arrival, and when it is someone closing a conversation.

A farmer in Paschim Medinipur wrote "accha" and then "kuch nahi karo" - fine,
do nothing - and was answered four minutes later with "Namaste! It is good to
hear from you again. How are your wheat fields in Kharagpur?" An opening move,
in the middle of a conversation the farmer was trying to end.

The routing above it was not at fault. Smalltalk carrying a topic is already
treated as a continuation, and a short reply following one of our questions is
already treated as an answer. Neither fires here, correctly: "accha" carries no
topic, and answers_our_question needs our previous turn to contain a question
mark, which it will not when that turn ended on a statement.

greet() was the problem. It branched on whether the profile was recognised,
which separates a stranger from a returning farmer and separates neither of
them from someone four minutes into a live thread. The missing input is whether
a conversation is already in progress, and that boundary already existed in
feedback.py as SESSION_GAP_HOURS.

This cannot be a case in cases.yaml: the decision is made before any model is
called, and what it chooses is which instruction to send. Checked here as the
plain function it is, at no model cost.

Run: python eval/test_greeting.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from planner import greeting_mode

failures = []

KNOWN = {"location_text": "Kharagpur", "crops": ["wheat"]}
CROPS_ONLY = {"crops": ["potato"]}
PLACE_ONLY = {"location_text": "Sitapur"}
EMPTY = {"crops": [], "location_text": None}


def check(profile, continuing, expected, why):
    actual = greeting_mode(profile, continuing)
    ok = actual == expected
    if not ok:
        failures.append(f"expected {expected}, got {actual} - {why}")
    print(f"  [{'ok' if ok else 'FAIL'}] {expected:<13} {why}")


print("Mid-conversation: a greeting is wrong however well it is worded")
# The regression this test exists for. Session state wins over everything the
# profile says, because the farmer is closing rather than arriving.
check(KNOWN, True, "continuation", "known farmer, 4 minutes into a thread")
check(EMPTY, True, "continuation", "unknown farmer, already mid-conversation")
check(None, True, "continuation", "no profile at all, but a live session")
check(CROPS_ONLY, True, "continuation", "crops known, still mid-conversation")

print("\nStarting a conversation: greet, scaled to what we already know")
# "shukriya" arrived 4h29m after the previous turn, past SESSION_GAP_HOURS.
# A new conversation, and greeting it is right.
check(KNOWN, False, "returning", "known farmer after a long gap")
check(CROPS_ONLY, False, "returning", "we know their crop, so resume")
check(PLACE_ONLY, False, "returning", "we know their place, so resume")

print("\nFirst contact: say what the service is for")
check(EMPTY, False, "first_contact", "profile exists but holds nothing usable")
check(None, False, "first_contact", "no profile")
check({}, False, "first_contact", "empty dict")

print("\nDefault")
# in_live_session returns False when there is no database or the lookup fails,
# so the default must be the harmless one: greeting a farmer mid-thread is
# clumsy, but never answering is the failure this project cannot afford.
check(KNOWN, False, "returning", "defaults to greeting, never to silence")

print()
if failures:
    for f in failures:
        print(f"FAIL {f}")
    print(f"\n{len(failures)} failed")
    sys.exit(1)

print("All greeting-mode checks passed")
