"""
Refusing to state a support price we do not hold.

The advisory prompt is told never to name a price scheme it has no figure for.
It named one anyway: asked for the sugarcane MSP, with no MSP section in its
context, it produced "the Fair and Remunerative Price for the 2026-27 season is
340 rupees per quintal" - a fluent, specific, entirely invented number, which
then carried into the next turn as established fact.

This is the same lesson as pesticide doses. An instruction not to state a figure
competes with a fluent continuation and loses often enough to matter, and the
cost is not a clumsy sentence but a farmer selling a harvest against a price
nobody guaranteed. So the check is code, not wording: if no support price was
retrieved for this crop, a sentence that names a support scheme and a number
does not leave the building.
"""
import re

SCHEME = re.compile(
    r"\b(msp|frp|minimum support price|fair and remunerative|"
    r"support price|procurement price|floor price|samarthan mulya)\b",
    re.I,
)
# A quantity, in either script, with or without a currency word.
FIGURE = re.compile(r"(?:\d[\d,]*\.?\d*)|[\u0966-\u096F]+")

FALLBACK = ("I do not have the official support price for this crop on record. "
            "Your local APMC mandi can give you the current rate, and for "
            "sugarcane the cooperative sugar mill publishes the price it pays.")


def _sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?।])\s+", text)


def scrub(answer: str, gathered: dict) -> tuple[str, bool]:
    """Remove support-price claims that no retrieved figure backs.

    Returns the answer and whether anything was removed. Only sentences that
    assert both a scheme and a number are dropped; telling a farmer to ask the
    sugar mill is useful and stays.
    """
    if not answer or gathered.get("msp"):
        return answer, False          # a real figure was retrieved; nothing to check

    kept, removed = [], False
    for sentence in _sentences(answer):
        if SCHEME.search(sentence) and FIGURE.search(sentence):
            removed = True
            continue
        kept.append(sentence)

    if not removed:
        return answer, False

    text = " ".join(s for s in kept if s.strip()).strip()
    # Stripping can leave a reply that no longer answers anything.
    if len(text) < 40:
        text = FALLBACK
    return text, True
