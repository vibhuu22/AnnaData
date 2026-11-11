"""
The final answer, sent a sentence at a time while the model is still writing.

A farmer used to wait for the whole answer - about seven seconds of thinking -
before seeing or hearing any of it. Streaming the last model call, the one that
writes the answer, puts the first sentence on screen and into speech while the
rest is still being written.

Every sentence passes output_guards.SentenceGuard before it is sent, because a
sent sentence cannot be taken back. The whole answer still goes through
scrub() and ensure_registered_doses() afterwards in run_agent exactly as
before; that result is authoritative and is sent last, so anything added at the
end (a registered dose the model left out) reaches the farmer too.

Only the writing of the answer streams. Understanding the question, choosing
tools and fetching data happen first and take the time they take.
"""
from __future__ import annotations

import re

from langchain_core.messages import HumanMessage

import output_guards

# A sentence ends at . ! ? or the danda, followed by space - but not the full
# stop inside "0.5 ml" or "25.3%". A line break always ends a piece, so a
# markdown heading or list item is sent as soon as it is complete.
_BOUNDARY = re.compile(r"(?:(?<!\d)[.!?।॥](?=\s)|(?<=\d)[.!?।॥](?=\s+\D)|\n)")
_FENCE = re.compile(r"^\s*```(?:markdown)?\s*$")


def _text_of(chunk) -> str:
    content = getattr(chunk, "content", chunk)
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # some models send a list of parts
        return "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
    return str(content or "")


class SentenceStreamer:
    """Collects streamed text and hands on each complete, guarded sentence."""

    def __init__(self, on_text, gathered: dict | None = None, doses: dict | None = None):
        self.on_text = on_text
        self.guard = output_guards.SentenceGuard(gathered or {}, doses)
        self.buffer = ""
        self.raw = []

    def feed(self, text: str) -> None:
        if not text:
            return
        self.raw.append(text)
        self.buffer += text
        while True:
            match = _BOUNDARY.search(self.buffer)
            if not match:
                break
            end = match.end()
            # Keep the whitespace that follows with this piece, so the pieces
            # joined back together are the answer's own layout.
            while end < len(self.buffer) and self.buffer[end] in " \t":
                end += 1
            piece, self.buffer = self.buffer[:end], self.buffer[end:]
            self._send(piece)

    def _send(self, piece: str) -> None:
        if not piece.strip():
            if piece:
                self.on_text(piece)
            return
        if _FENCE.match(piece.strip("\n")):
            return  # a ```markdown fence the model wrapped the answer in
        kept = self.guard.check(piece)
        if kept is not None:
            self.on_text(kept)

    def finish(self) -> str:
        """Send what is left; return the whole raw text, as invoke() would have."""
        if self.buffer:
            self._send(self.buffer)
            self.buffer = ""
        closing = self.guard.closing()
        if closing:
            self.on_text("\n\n" + closing)
        return "".join(self.raw)


def write(llm, prompt: str, on_text, gathered: dict | None = None,
          doses: dict | None = None) -> str:
    """llm.invoke, streamed. Returns the full text, exactly as invoke returns it."""
    streamer = SentenceStreamer(on_text, gathered, doses)
    for chunk in llm.stream([HumanMessage(content=prompt)]):
        streamer.feed(_text_of(chunk))
    return streamer.finish()
