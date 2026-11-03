"""
Decide whether an incoming SMS came from a person or from a machine.

`is_replyable` in app.py already drops DLT sender IDs like "JR-JIOPAY-S",
because nothing alphanumeric can receive a reply. That test is about the
sender. This module is about the text, and it exists because the sender test
is not enough: an operator's own notices arrive from a plain numeric
shortcode, pass the sender check, and are then answered as though a farmer had
asked something. One did - a Jio missed-call notice reached the agent, was
refined into a farming question, cost a model call, and wrote a row to the
farmer table.

The asymmetry that shapes this list: a false negative costs one model call,
while a false positive silently swallows a farmer's real question. So every
marker here is a phrase a farmer writing to an advisory service would
essentially never use, and generic words that merely *appear* in machine
traffic - "balance", "offer", "data" - are deliberately absent unless pinned
down by surrounding context.
"""
import re

# Each pattern is matched case-insensitively against the whole message.
_MARKERS = (
    # Salutations. A farmer addresses the service, not "Dear Customer".
    r"\bdear\s+(customer|user|subscriber|member)\b",

    # Operator sign-offs, with or without the "Team" prefix.
    r"\bteam\s+(jio|airtel|vi|vodafone|idea|bsnl|mtnl)\b",

    # Call and message notices.
    r"\bmissed\s+call\b",
    r"\bcall\s+(was\s+)?(not\s+)?(answered|completed)\b",

    # One-time passwords, and the warning that always travels with them.
    r"\b(otp|one[\s-]?time\s+password)\b",
    r"\b(do\s+not|don'?t|never)\s+share\b[^.]{0,40}\b(otp|pin|password|code)\b",

    # Bank and payment notices.
    r"\b(debited|credited)\b[^.]{0,60}\b(a/?c|account)\b",
    r"\bavailable\s+balance\b",
    r"\b(upi|imps|neft|txn)\s*(ref|id|no|number)\b",

    # Recharge, pack and validity notices: the operator words only count when
    # they sit beside a price, a size or a date, which is what makes them a
    # notice rather than a farmer's turn of phrase.
    r"\b(recharge|data\s*pack|validity)\b[^.]{0,40}(rs\.?\s*\d|₹\s*\d|\d+\s*(gb|mb)\b|\d+\s*days?\b)",
    r"\byour\s+(balance|plan|pack|validity)\s+(is|has|will|expires)\b",

    # Marketing boilerplate.
    r"\bt\s*&\s*c\s+apply\b",
    r"\bterms\s+and\s+conditions\s+apply\b",
    r"\bto\s+(unsubscribe|opt[\s-]?out)\b",
    r"\bclick\s+(here|the\s+link|below)\b",
    r"\bdownload\s+the\s+(app|mobile\s+app)\b",
)

_PATTERN = re.compile("|".join(_MARKERS), re.IGNORECASE)


def is_operator_notice(message: str) -> bool:
    """True when the text reads as operator, bank or marketing traffic.

    Checked after the sender test and before anything that costs money, so a
    notice from a numeric shortcode is dropped without a model call, a database
    row, or a reply SMS to a number that cannot receive one.
    """
    if not message:
        return False
    return bool(_PATTERN.search(message))


__all__ = ["is_operator_notice"]
