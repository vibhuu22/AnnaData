"""
A streamed answer must say nothing the whole-answer guards would not let through.

Once a sentence is streamed it is on the farmer's screen or in their ear; it
cannot be taken back when scrub() later sees the whole answer. So every
streamed sentence passes output_guards.SentenceGuard, and this checks that the
guard and scrub() agree: the same model output, streamed or not, ends up
saying the same things. Also that the pieces rejoin into the model's own
layout, that a dose like "0.5 ml" is never split, and that a ```markdown fence
is never sent.

No model calls: the "model" is a list of chunks.

Run: python eval/test_answer_stream.py
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GEMINI_API_KEY", "x")

import answer_stream
import output_guards

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


class FakeLLM:
    def __init__(self, text, size=7):
        self.chunks = [text[i:i + size] for i in range(0, len(text), size)]

    def stream(self, messages):
        for chunk in self.chunks:
            yield NS(content=chunk)


def streamed(text, gathered=None, size=7):
    sent = []
    full = answer_stream.write(FakeLLM(text, size), "prompt", sent.append, gathered or {})
    return sent, full


print("Layout survives being cut into pieces")
answer = ("### Upchar\n*   **Acephate 75% SP:** 780 g/ha, 500-1000 litre paani mein.\n\n"
          "Spray ke 15 din baad tak fasal na todein. Kya hamla zyada hai?")
sent, full = streamed(answer, {"doses": "x"})
check("the full text is returned as the model wrote it", full, answer)
check("the pieces rejoin into the same answer", "".join(sent), answer)
check("it is sent as more than one piece", len(sent) > 2, True)
check("the first piece is the heading, sent as soon as its line ends", sent[0], "### Upchar\n")

print("\nNumbers are not sentence ends")
sent, _ = streamed("Dava 0.5 ml prati litre paani mein milayein. Spray subah karein.", size=3)
check("0.5 ml stays in one piece", any("0.5 ml" in s for s in sent), True)
check("two sentences, two pieces", [s.strip() for s in sent if s.strip()],
      ["Dava 0.5 ml prati litre paani mein milayein.", "Spray subah karein."])

print("\nA fence the model wraps the answer in is not sent")
sent, _ = streamed("```markdown\nGehu ki buwai November mein karein.\n```")
check("no fence reaches the farmer", any("```" in s for s in sent), False)
check("the answer inside it does", "".join(sent).strip(), "Gehu ki buwai November mein karein.")

print("\nThe guards agree with scrub()")
cases = [
    ("an unsupported support price",
     "Gehu ki buwai November mein karein, beej upchar zaroor karein. Gehu ka MSP Rs 2,425 prati quintal hai. Mandi mein bhav dekh lein.",
     {}),
    ("a supported support price is kept",
     "Gehu ka MSP Rs 2,425 prati quintal hai. Mandi mein bhav dekh lein.",
     {"msp": "Wheat MSP 2025-26: Rs 2,425/quintal"}),
    ("nothing but an unsupported figure",
     "Gehu ka MSP Rs 2,425 prati quintal hai.",
     {}),
]
for name, text, gathered in cases:
    sent, full = streamed(text, gathered)
    scrubbed, _ = output_guards.scrub(full, gathered)
    norm = lambda t: " ".join(t.split())
    check(f"{name}: streamed says what scrub keeps", norm("".join(sent)), norm(scrubbed))

print("\nA model that sends a list of parts")
check("its text is read", answer_stream._text_of(NS(content=[{"type": "text", "text": "Haan"}, " ji"])), "Haan ji")

print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)
