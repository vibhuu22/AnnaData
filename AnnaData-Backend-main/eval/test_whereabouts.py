"""
Which place an answer is for: the phone's, when it is allowed, and asked only
when there is none.

A guest in Kharagpur with location allowed was greeted from Shimla, and asked
"Tell us your village or district" under answers the browser could have placed
itself. This runs the real answer path - app._answer and Agent.run_agent -
against a local Postgres, with every model, geocoder and data source stubbed,
so it makes no model or network call. What it checks is where the place came
from and where it went: the weather and soil coordinates, the state for mandi
prices, the district for the dose table, the advice prompt, the greeting, the
follow-up asks and what is written to the profile.

Needs DATABASE_URL pointing at a scratch database (it writes and removes its
own farmers). Without one it says so and exits cleanly.

Run: python eval/test_whereabouts.py
"""
import os
import sys
import uuid
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


import whereabouts as wh  # noqa: E402
from Address_Convertor import Place  # noqa: E402

print("Yes and no")
for said, want in (("haan", True), ("Haan ji", True), ("yes", True), ("ji", True), ("ha", True),
                   ("हाँ", True), ("ਹਾਂ ਜੀ", True), ("nahi", False), ("ji nahi", False), ("no", False),
                   ("नहीं", False), ("haan par mera khet Medinipur me hai", None), ("aloo me rog", None),
                   # An acknowledgement of the answer above the question, not a yes to it.
                   ("ok", None), ("theek hai", None), ("okk thaks", None)):
    check(f"{said!r}", wh.yes_or_no(said), want)

print("\nThe order places are chosen in")
KGP = Place(22.34, 87.30, kind="city", district="Paschim Medinipur", state="West Bengal", name="Kharagpur")
SHIMLA = {"location_text": "Shimla", "state": "Himachal Pradesh", "district": "Shimla",
          "latitude": 31.10, "longitude": 77.17, "crops": ["potato"]}
NEAR = {"location_text": "Salua", "state": "West Bengal", "district": "Paschim Medinipur",
        "latitude": 22.30, "longitude": 87.25}
check("a place named in the message first",
      wh.choose(named="Midnapore", geocoded=Place(22.42, 87.32, state="West Bengal"),
                phone=KGP, profile=SHIMLA).source, "message")
check("then one named earlier in the chat",
      wh.choose(named="Midnapore", named_in_message=False, phone=KGP).source, "chat")
check("then the phone", wh.choose(phone=KGP, profile=None).name, "Kharagpur")
check("the phone over a stored farm 1,400 km away", wh.choose(phone=KGP, profile=SHIMLA).name, "Kharagpur")
check("a stored farm within 50 km of the phone is the better name for it",
      wh.choose(phone=KGP, profile=NEAR).name, "Salua")
check("the stored farm when there is no phone", wh.choose(phone=None, profile=SHIMLA).name, "Shimla")
check("nothing at all", wh.choose().known, False)
check("a phone whose place could not be looked up still places the answer",
      wh.choose(phone=Place(22.34, 87.30)).known, True)

try:
    import db
    import app as appmod
    import Agent
    import profile_store
except Exception as e:
    print(f"\nBackend not importable here ({type(e).__name__}: {e}); skipping the answer path")
    Agent = None

if Agent is not None and not (os.getenv("DATABASE_URL") and (db.init() or db.is_available())):
    print("\nNo scratch DATABASE_URL; skipping the answer path")
    Agent = None

if Agent is not None:
    # --- Stubs: no model, no geocoder, no data source -------------------------
    PARSED = {
        # The parser invents a place from the crop, as it did live.
        "aloo me jhulsa rog": dict(location="Jalandhar", state="Punjab", crop_type="potato",
                                   pest="blight", intent="disease_pest", message_type="question"),
        "hello": dict(location="unknown", state="unknown", crop_type="unknown", pest="unknown",
                      intent="general", message_type="smalltalk"),
        "i am not in shimla": dict(location="Shimla", state="Himachal Pradesh", crop_type="unknown",
                                   pest="unknown", intent="general", message_type="correction"),
        "gehu me kaun si khad daalein": dict(location="unknown", state="unknown", crop_type="wheat",
                                            pest="unknown", intent="fertiliser_nutrition",
                                            message_type="question"),
    }
    seen = {}

    def fake_parse(query_final, original=None):
        parsed = dict(PARSED[original or query_final])
        parsed.setdefault("answer", "unknown")
        return parsed

    def fake_gather(tools, **kw):
        seen["gather"] = kw
        return {}, {}

    def fake_advice(location, state, crop, gathered, query, channel, **kw):
        seen["advice"] = (location, state)
        return f"Advice for {location} in {state}."

    class FakeLLM:
        def invoke(self, messages):
            seen["prompt"] = messages[0].content
            return type("R", (), {"content": "Namaste! Main AnnaData hoon."})()

    Agent.get_farming_query = lambda query, history: query
    Agent.extract_farm_info = fake_parse
    Agent.reverse = lambda lat, lon: KGP if round(lat, 1) == 22.3 else Place(lat, lon)
    Agent.locate = lambda name: {"shimla": Place(31.10, 77.17, kind="city", state="Himachal Pradesh",
                                                 district="Shimla")}.get(name.lower(), Place(None, None))
    Agent.gather = fake_gather
    Agent.get_farming_advice = fake_advice
    Agent.llm = FakeLLM()
    Agent.kb_available = lambda: False
    Agent.knowledge.documents_loaded = lambda: False

    made = []

    def guest():
        user = "guest:" + str(uuid.uuid4())
        made.append(user)
        return user

    def ask(user, query, lat=22.34, lon=87.30, channel="web", history=None):
        seen.clear()
        return appmod._answer(query, user_id=user, channel=channel, latitude=lat, longitude=lon,
                              history=[] if history is None and channel != "sms" else history,
                              chat_id="chat-test-0001")

    def stored(user):
        return profile_store.get_profile(user) or {}

    try:
        print("\nPhone in Kharagpur, nothing stored: 'aloo me jhulsa rog'")
        user = guest()
        r = ask(user, "aloo me jhulsa rog")
        check("weather and soil at the phone", (seen["gather"]["lat"], seen["gather"]["lon"]), (22.34, 87.30))
        check("mandi state and dose district from the phone's place",
              (seen["gather"]["state"], seen["gather"]["district"]), ("West Bengal", "Paschim Medinipur"))
        check("the advice is for Kharagpur, West Bengal (not the invented Jalandhar)",
              (seen["advice"][0].startswith("Kharagpur"), seen["advice"][1]), (True, "West Bengal"))
        check("no location ask", (r["needs_location"], "location" in r["missing_slots"]), (False, False))
        check("'Is your farm near Kharagpur?' is asked", r["confirm_place"], "Kharagpur")
        check("and nothing is stored as the farm yet", stored(user).get("location_text"), None)
        check("not even the state", stored(user).get("state"), None)

        print("\n'hello' in a new chat, phone in Kharagpur")
        r = ask(guest(), "hello")
        check("a greeting carries no farm question under it", r["confirm_place"], None)

        print("\n... then 'haan'")
        r = ask(user, "haan")
        check("Kharagpur is saved as the farm", (stored(user).get("location_text"), stored(user).get("state")),
              ("Kharagpur", "West Bengal"))
        check("and the reply says so", "Kharagpur" in r["answer"], True)
        r = ask(user, "aloo me jhulsa rog")
        check("the farm is not asked about again", r["confirm_place"], None)

        print("\n... or 'nahi'")
        user = guest()
        ask(user, "aloo me jhulsa rog")
        r = ask(user, "nahi")
        check("nothing saved", stored(user).get("location_text"), None)
        r = ask(user, "aloo me jhulsa rog")
        check("still answered for the phone", seen["advice"][0].startswith("Kharagpur"), True)
        check("and never asked about Kharagpur again", r["confirm_place"], None)
        check("nor asked for a village or district", r["needs_location"], False)

        print("\nStored Shimla, phone in Kharagpur")
        user = guest()
        profile_store.remember(user, channel="web", location_text="Shimla", latitude=31.10, longitude=77.17,
                               state="Himachal Pradesh", district="Shimla", location_kind="city", crop="potato")
        ask(user, "aloo me jhulsa rog")
        check("Kharagpur is used", (seen["advice"][0].startswith("Kharagpur"), seen["gather"]["state"]),
              (True, "West Bengal"))
        ask(user, "hello")
        check("the greeting does not mention Shimla", "Shimla" in seen["prompt"], False)
        check("nor ask where they farm", "invite them to say where they farm" in seen["prompt"], False)

        print("\n'i am not in shimla', phone in Kharagpur")
        r = ask(user, "i am not in shimla")
        check("Shimla is cleared from the profile", stored(user).get("location_text"), None)
        check("the reply names Kharagpur", r["answer"], "Got it, I'll use Kharagpur, where your phone is.")
        check("and asks nothing", r["needs_location"], False)

        print("\nSMS, no coordinates, stored place")
        user = guest()
        profile_store.remember(user, channel="sms", location_text="Shimla", latitude=31.10, longitude=77.17,
                               state="Himachal Pradesh", district="Shimla", location_kind="city")
        r = ask(user, "gehu me kaun si khad daalein", lat=None, lon=None, channel="sms")
        check("the stored place is used", (seen["gather"]["lat"], seen["gather"]["state"]),
              (31.10, "Himachal Pradesh"))
        check("no ask", (r["needs_location"], r["missing_slots"], r["confirm_place"]), (False, [], None))

        print("\nNo coordinates and nothing stored")
        user = guest()
        r = ask(user, "gehu me kaun si khad daalein", lat=None, lon=None)
        check("asks for the location", (r["needs_location"], "location" in r["missing_slots"]), (True, True))
        check("and asks nothing about a farm", r["confirm_place"], None)
    finally:
        with db.connection() as conn:
            for user in made:
                conn.execute("DELETE FROM messages WHERE user_id = %s", (user,))
                conn.execute("DELETE FROM feedback WHERE user_id = %s", (user,))
                conn.execute("DELETE FROM farmers WHERE user_id = %s", (user,))

print()
if failures:
    print(f"{len(failures)} failed: {failures}")
    sys.exit(1)
print("all passed")
os._exit(0)   # the pool's worker threads would otherwise hold the exit
