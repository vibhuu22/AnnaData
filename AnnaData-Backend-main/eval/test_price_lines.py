"""
Reported mandi prices are written under the answer by code, exactly as published.

The model rounded ("about Rs 800" for 810), averaged markets, and once invented
a rate with no data at all. Now it is told to write no amount, and the figures
come from the data.gov.in rows. Runs Agent.run_agent with the parser, model and
mandi service stubbed: no network, no database.

Run: python eval/test_price_lines.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GEMINI_API_KEY", "x")

import Agent  # noqa: E402
import price_lines  # noqa: E402

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


ROWS = ("Market: Ghatal APMC | Commodity: Potato (Jyoti) | Grade: FAQ | Arrival Date: 04/11/2026 | "
        "Min Price: Rs800 | Max Price: Rs820 | Modal Price: Rs810\n"
        "Market: Garbeta(Medinipur) APMC | Commodity: Potato (Jyoti) | Grade: FAQ | "
        "Arrival Date: 04/11/2026 | Min Price: Rs640 | Max Price: Rs680 | Modal Price: Rs660")

print("The block")
text = price_lines.block(ROWS, "आलू का भाव घाटल में सबसे अच्छा है।")
check("Hindi answer, Hindi block", text.splitlines()[0], "**मंडी भाव (data.gov.in):**")
check("the modal price and range, exactly", "₹810 प्रति क्विंटल (₹800–820)" in text, True)
check("the date, readable", "4 Nov 2026" in text, True)
check("Hinglish answer, Hinglish block",
      price_lines.block(ROWS, "Aalu ka bhav Ghatal mein achha hai.").splitlines()[0],
      "**Mandi bhav (data.gov.in):**")
check("no rows, no block", price_lines.block("No potato rate appears in the latest data.", "x"), "")
check("not added twice", price_lines.append(price_lines.append("ok ok", ROWS)[0], ROWS)[1], False)

print("\nThrough the answer")
seen = {}


def fake_advice(location, state, crop, gathered, query, channel, **kw):
    seen["gathered"] = dict(gathered)
    return "Ghatal mein aalu ka bhav sabse achha hai, lagbhag 750 rupaye prati quintal. Kya aap bechna chahte hain?"


Agent.get_farming_query = lambda query, history: query
Agent.extract_farm_info = lambda q, original=None: dict(
    location="Medinipur", state="West Bengal", crop_type="potato", pest="unknown",
    intent="market_price", message_type="question", answer="unknown")
Agent.get_farming_advice = fake_advice
Agent.kb_available = lambda: False
Agent.knowledge.documents_loaded = lambda *a, **k: False
Agent.msp.for_crop = lambda crop: ""
Agent.get_state_data = lambda state, crop, district=None: ROWS
Agent.locate = lambda name: Agent.Place(22.42, 87.32, state="West Bengal", district="Paschim Medinipur",
                                       name="Medinipur")
r = Agent.run_agent("aaj aalu ka bhav medinipur me", history=[], channel="web")
check("the model's rounded 'lagbhag 750' is removed", "lagbhag 750" in r.answer, False)
check("its question stays", "Kya aap bechna chahte hain?" in r.answer, True)
check("the reported prices are under the answer", "Rs 810 prati quintal (Rs 800-820)" in r.answer, True)
check("the rows reached the answer's data", bool(price_lines.rows(seen["gathered"].get("mandi"))), True)

print()
if failures:
    print(f"{len(failures)} failed: {failures}")
    sys.exit(1)
print("all passed")
