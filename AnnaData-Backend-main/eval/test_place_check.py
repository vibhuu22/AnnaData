"""
A place is the farmer's only if the farmer said it.

A guest in Kharagpur, browser location on, opened a new chat with "hello" and
was greeted "Hello from your fields in Shimla! How are your wheat and potato
crops?" Then "i am not in shimla" was answered by asking for their location,
with Shimla still on the profile. Reproduced live: "aloo me jhulsa rog lag gaya
hai" - potato blight, no place - was parsed as Jalandhar, and the next "hello"
asked how things were in Jalandhar. The parser fills the place slot from what
it associates with the crop.

Three things went wrong, and each is checked here without a model call:
  1. A place absent from everything the farmer wrote was kept.
  2. The stored name was saved again with the browser's coordinates, so the
     profile said Shimla at Kharagpur's position.
  3. "i am not in shimla" changed nothing.

Run: python eval/test_place_check.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GEMINI_API_KEY", "x")

import place_check as pc

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


print("A place the farmer wrote, in any script")
check("Shimla in Latin", pc.said("Shimla", ["main shimla se hoon"]), True)
check("Kharagpur in Devanagari, nukta typed separately", pc.said("Kharagpur", ["मैं खड़गपुर से हूँ"]), True)
check("Bardhaman in Bengali", pc.said("Bardhaman", ["আমি বর্ধমানে থাকি"]), True)
check("Ludhiana in Gurmukhi", pc.said("Ludhiana", ["ਮੈਂ ਲੁਧਿਆਣੇ ਤੋਂ ਹਾਂ"]), True)
check("one word of a two-word district", pc.said("Paschim Medinipur", ["medinipur me dhaan"]), True)
check("a state by its short form", pc.said("Uttar Pradesh", ["up me gehu ka bhav"]), True)
check("an earlier message of theirs", pc.said("Kharagpur", ["aloo ka rog", "I farm in Kharagpur"]), True)

print("\nA place the farmer did not write")
check("potato blight is not Jalandhar", pc.said("Jalandhar", ["aloo me jhulsa rog lag gaya hai"]), False)
check("wheat and potato is not Shimla", pc.said("Shimla", ["wheat and potato which fertilizer"]), False)
check("shimla mirch is capsicum, not Shimla", pc.said("Shimla", ["shimla mirch me kide lag gaye"]), False)
check("nor is शिमला मिर्च", pc.said("Shimla", ["शिमला मिर्च में कीड़े"]), False)

print("\nA place the farmer denies")
check("i am not in shimla", pc.denied("Shimla", "i am not in shimla"), True)
check("shimla me nahi hoon", pc.denied("Shimla", "shimla me nahi hoon"), True)
check("शिमला में नहीं हूँ", pc.denied("Shimla", "शिमला में नहीं हूँ"), True)
check("the place they say instead is not denied",
      pc.denied("Kharagpur", "i am not in shimla, i am in kharagpur"), False)

print("\nDistance")
check("Shimla to Kharagpur is far", pc.km_apart(31.10, 77.17, 22.34, 87.30) > 1000, True)

try:
    import Agent
except Exception as e:  # langchain absent: the rest needs the agent module
    print(f"\nAgent not importable here ({type(e).__name__}); skipping the agent checks")
    Agent = None

if Agent:
    SHIMLA = {"location_text": "Shimla", "state": "Himachal Pradesh", "district": "Shimla",
              "latitude": 31.10, "longitude": 77.17, "crops": ["wheat", "potato"]}

    print("\nThe agent's place check")
    c = Agent._check_place("aloo me jhulsa rog lag gaya hai", [], "Jalandhar", "Punjab", None)
    check("an invented place and its state are dropped", (c["location"], c["state"], c["forget"]),
          ("unknown", "unknown", False))

    c = Agent._check_place("dhaan ka rog, main kharagpur me hoon", [], "Kharagpur", "West Bengal", None)
    check("a named place is kept, as named in this message",
          (c["location"], c["state"], c["in_message"]), ("Kharagpur", "West Bengal", True))

    c = Agent._check_place("dhaan ka rog", [{"role": "user", "content": "main kharagpur me hoon"}],
                           "Kharagpur", "West Bengal", None)
    check("one named earlier in the chat is kept, as from the chat", (c["location"], c["in_message"]),
          ("Kharagpur", False))

    c = Agent._check_place("hello", [{"role": "assistant", "content": "Hello from your fields in Shimla!"}],
                           "Shimla", "Himachal Pradesh", None)
    check("our own reply does not vouch for a place", c["location"], "unknown")

    c = Agent._check_place("up me gehu ka bhav", [], "unknown", "Uttar Pradesh", None)
    check("a state the farmer wrote is kept on its own", c["state"], "Uttar Pradesh")

    c = Agent._check_place("i am not in shimla", [], "Shimla", "Himachal Pradesh", SHIMLA)
    check("a denied stored place is forgotten",
          (c["location"], c["forget"], c["denied"], c["profile"].get("location_text")),
          ("unknown", True, "Shimla", None))

print()
if failures:
    print(f"{len(failures)} failed: {failures}")
    sys.exit(1)
print("all passed")
