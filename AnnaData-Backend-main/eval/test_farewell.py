"""
A farmer who says they are done is answered with a goodbye, and voice mode stops.

The classifier can call a message "farewell" ("bas", "aur kuch nahi chahiye").
It is the one message type with a consequence beyond the reply - the web app's
voice mode stops listening on it - so the rules that keep a false goodbye from
hanging up on a farmer are checked here. No network.

Run: python eval/test_farewell.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GEMINI_API_KEY", "x")

import Agent
import planner
import Query_Parser

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


ASKED = [{"role": "user", "content": "gehu ki buwai kab karu"},
         {"role": "assistant", "content": "Kya aapka khet Kharagpur ke paas hai?"}]
TOLD = [{"role": "user", "content": "gehu ki buwai kab karu"},
        {"role": "assistant", "content": "Gehu ki buwai November ke pehle pakhwade mein karein."}]

print("The classifier may say farewell")
check("farewell is a message type the planner keeps", planner.normalise_message_type("farewell"), "farewell")
check("and one the classifier is offered", "farewell" in Query_Parser.MESSAGE_TYPES, True)

print("\nA real goodbye stays a goodbye")
f = Agent.farewell_or_not
check("'bas, aur kuch nahi chahiye' after an answer", f("farewell", "general", "bas, aur kuch nahi chahiye", TOLD), "farewell")
check("'thank you, bye' with no history", f("farewell", "general", "thank you, bye", []), "farewell")
check("'nahi, ab kuch nahi poochna' even after our question", f("farewell", "general", "nahi, ab kuch nahi poochna", ASKED), "farewell")
check("a bare 'nahi' when we asked nothing is a goodbye", f("farewell", "general", "nahi", TOLD), "farewell")
check("a goodbye after a wheat answer, whose rewrite reads as sowing",
      f("farewell", "sowing_planting", "bas, aur kuch nahi chahiye, dhanyavaad", TOLD), "farewell")

print("\nWhat must not hang up")
check("a bare 'nahin' answering our question", f("farewell", "general", "nahin", ASKED), "question")
check("a bare 'नहीं' answering our question", f("farewell", "general", "नहीं।", ASKED), "question")
check("a bare 'না' answering our question", f("farewell", "general", "না", ASKED), "question")
check("other message types pass through", f("smalltalk", "general", "ok", TOLD), "smalltalk")

print("\nThe goodbye line asks nothing")


class _Said:
    def __init__(self):
        self.prompts = []

    def invoke(self, messages):
        self.prompts.append(messages[0].content)
        return type("R", (), {"content": "Theek hai, jab zarurat ho phir message karna."})()


said = _Said()
real_llm, Agent.llm = Agent.llm, said
try:
    Agent.greet("bas, aur kuch nahi chahiye", None, "voice", continuing_session=True, farewell=True)
    Agent.greet("thanks", None, "voice", continuing_session=True)
finally:
    Agent.llm = real_llm
check("a goodbye is told not to ask a question", "Do NOT ask any question" in said.prompts[0], True)
check("and not to end with one", "End with one question" in said.prompts[0], False)
check("a plain thanks keeps the greeting's one question", "End with one question" in said.prompts[1], True)

print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)
