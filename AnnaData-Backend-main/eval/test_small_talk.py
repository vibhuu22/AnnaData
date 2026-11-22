"""
Small talk is only small talk when nothing else was said.

From the 22 November export: labelled smalltalk mid-conversation, "Main
Sitapur, UP mein rehta hoon", "मौसम कैसा है, समाचार दो" and "Hello, kaise ho
tum? Kya tum mujhe khet ki jankari de sakte ho?" were each answered with a
goodbye; "Hello kaise ho tum" mid-chat got "Bilkul, koi baat nahi"; and a bare
"thanks", labelled a question, got a paragraph on wheat. Runs Agent.run_agent
with the parser and model stubbed: no network, no database.

Run: python eval/test_small_talk.py
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


class FakeLLM:
    def invoke(self, messages):
        seen["prompt"] = messages[0].content
        return type("R", (), {"content": "stub reply"})()


LABEL = {}
INTENT = {}


def fake_parse(query_final, original=None):
    q = original or query_final
    return dict(location="unknown", state="unknown", crop_type="unknown", pest="unknown",
                intent=INTENT.get(q, "general"), message_type=LABEL[q], answer="unknown")


Agent.get_farming_query = lambda query, history: query
Agent.extract_farm_info = fake_parse
Agent.llm = FakeLLM()
Agent.kb_available = lambda: False
Agent.knowledge.documents_loaded = lambda *a, **k: False
Agent.locate = lambda name: Agent.Place(None, None)
Agent.get_open_ended_answer = lambda *a, **k: "open answer"

MID = [{"role": "user", "content": "gehu ki buwai kab karein"},
       {"role": "assistant", "content": "November mein karein."}]


def run(query, label, history=MID, continuing=True):
    LABEL[query] = label
    seen.clear()
    return Agent.run_agent(query, history=history, channel="web", continuing_session=continuing)


print("Labelled smalltalk, but saying something")
for q, want in (("Main Sitapur Uttar Pradesh mein rehta hoon.", "statement"),
                ("मौसम कैसा है, समाचार दो", "question"),
                ("Hello, kaise ho tum? Kya tum mujhe khet ki jankari de sakte ho?", "question"),
                ("ओके मेरे को एक चीज बताओ की 100 को 200 से मल्टिप्लाई करूंगा तो क्या होगा?", "question")):
    r = run(q, "smalltalk")
    check(f"{q[:40]!r} is a {want}, not a greeting", (r.message_type, "greeting" in r.tools_used),
          (want, False))

print("\nReal small talk")
r = run("Hello kaise ho tum", "smalltalk")
check("hello mid-conversation is greeted, not said goodbye to",
      ("greeted you again" in seen["prompt"], "write again whenever" in seen["prompt"]), (True, False))
r = run("theek hai", "smalltalk")
check("'theek hai' mid-conversation is a short close", "signalled they are done" in seen["prompt"], True)
r = run("thanks", "question")
check("a bare 'thanks' labelled a question is answered as small talk",
      (r.message_type, r.tools_used), ("smalltalk", ["greeting"]))
r = run("Hello", "smalltalk", history=[], continuing=False)
check("'Hello' opening a chat is a greeting", r.tools_used, ["greeting"])

print("\nAfter we asked them something (live, 22 November)")
ASKED = [{"role": "user", "content": "gehu ki buwai kab karein"},
         {"role": "assistant", "content": "November mein karein. Kya aapne beej le liya hai?"}]
INTENT["thanks"] = "sowing_planting"
r = run("thanks", "question", history=ASKED)
check("'thanks' is not taken as the answer to our question, even with a topic attached",
      (r.message_type, r.tools_used), ("smalltalk", ["greeting"]))
INTENT.pop("thanks")
r = run("Hello kaise ho tum", "question", history=ASKED)
check("nor is 'Hello kaise ho tum'", (r.message_type, "greeted you again" in seen["prompt"]), ("smalltalk", True))
r = run("haan", "smalltalk", history=ASKED)
check("but 'haan' still answers it", r.message_type, "question")

print("\nThe name, in the answer's own script")
check("Bengali letters in Hinglish become AnnaData",
      Agent.fix_name("Namaste, main hoon অন্নদাতা, aapka kheti salahkar."),
      "Namaste, main hoon AnnaData, aapka kheti salahkar.")
check("and the answer is then read in an Indian-English voice, not Bengali",
      Agent.speech_language(Agent.fix_name("Namaste, main hoon অন্নদাতা.")), "en-IN")
check("Bengali letters in Hindi become Devanagari", Agent.fix_name("नमस्ते, मैं অন্নদাতা हूँ।"),
      "नमस्ते, मैं अन्नदाता हूँ।")
check("a letter-by-letter spelling is corrected", Agent.fix_name("मैं अन्नाडेटा हूँ"), "मैं अन्नदाता हूँ")
check("a Bengali answer keeps the Bengali name", Agent.fix_name("নমস্কার, আমি অন্নদাতা।"), "নমস্কার, আমি অন্নদাতা।")

check("one Hindi word in a Hinglish answer does not make it a Hindi voice",
      Agent.speech_language("Aap apne nazdiki CSC ya कृषि vibhag ke karyalay se sampark karein."), "en-IN")
check("a Hindi answer is still read in Hindi", Agent.speech_language("आप अपने नजदीकी कृषि कार्यालय जाएं।"), "hi-IN")

print()
if failures:
    print(f"{len(failures)} failed: {failures}")
    sys.exit(1)
print("all passed")
