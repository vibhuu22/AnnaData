"""
A price question with no state: ask where, and name no source that found nothing.

Live, "Aaj aalu ka mandi bhav kya hai?" from a computer without location was
answered "the price is not available, ask your APMC", with "Source: Minimum
Support Price" under it - though potato has no support price and no market had
been checked, because the state was not known. This runs Agent.run_agent with
the parser, model and data sources stubbed (no network, no database).

Run: python eval/test_price_without_state.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GEMINI_API_KEY", "x")

import Agent  # noqa: E402

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


seen = {}
PARSED = {
    "aaj aalu ka mandi bhav kya hai?": dict(crop_type="potato"),
    "aaj gehu ka mandi bhav kya hai?": dict(crop_type="wheat"),
    "aaj aalu ka mandi bhav kya hai, bihar me?": dict(crop_type="potato", state="Bihar", location="Patna"),
}


def fake_parse(query_final, original=None):
    parsed = dict(location="unknown", state="unknown", pest="unknown", intent="market_price",
                  message_type="question", answer="unknown")
    parsed.update(PARSED[(original or query_final).lower()])
    return parsed


def fake_advice(location, state, crop, gathered, query, channel, **kw):
    seen["gathered"] = dict(gathered)
    return "stub answer"


Agent.get_farming_query = lambda query, history: query
Agent.extract_farm_info = fake_parse
Agent.get_farming_advice = fake_advice
Agent.kb_available = lambda: False
Agent.knowledge.documents_loaded = lambda *a, **k: False
Agent.msp.for_crop = lambda crop: "Minimum Support Price for Wheat in 2026-27: Rs 2,585 per quintal." if crop == "wheat" else ""
Agent.get_state_data = lambda state, crop, district=None: f"{crop} in {state}: Rs 1,200 per quintal at Patna mandi"
Agent.locate = lambda name: Agent.Place(None, None)


def ask(query):
    seen.clear()
    return Agent.run_agent(query, latitude=None, longitude=None, history=[], channel="web")


print("Potato, no state, no location")
r = ask("Aaj aalu ka mandi bhav kya hai?")
check("no source is named (potato has no support price; no market was checked)", r.tools_used, [])
check("the answer is told to ask where, not to call the price unavailable",
      Agent.PRICE_NEEDS_PLACE in seen["gathered"], True)
check("the state is asked for", "state" in r.missing_slots, True)

print("\nWheat, no state: the support price is still given, and the state still asked")
r = ask("Aaj gehu ka mandi bhav kya hai?")
check("only the support price is a source", r.tools_used, ["msp"])
check("and the answer is told the market was not checked", Agent.PRICE_NEEDS_PLACE in seen["gathered"], True)

print("\nPotato in Bihar: the market is checked and nothing extra is said")
r = ask("Aaj aalu ka mandi bhav kya hai, Bihar me?")
check("the mandi rate is the source", r.tools_used, ["mandi"])
check("no 'not looked up' note", Agent.PRICE_NEEDS_PLACE in seen["gathered"], False)

print()
if failures:
    print(f"{len(failures)} failed: {failures}")
    sys.exit(1)
print("all passed")
