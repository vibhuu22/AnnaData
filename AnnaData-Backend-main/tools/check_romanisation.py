"""
Find the next garbled phrase by measuring, instead of spotting it in a screenshot.

"prataye quintal" was noticed by eye, in one answer, by luck. It had reached
production and would have kept reaching it. This reads every answer the system
has sent and reports two things:

  1. What sits in the unit slot - the word immediately before "quintal",
     "hectare", "acre", "kg". That slot is formulaic, so anything in it other
     than "prati" or a quantity is a defect, and output_guards.fix_units should
     already have caught it. Anything listed under "escaped the guard" is a
     garbling the guard does not recognise yet.

  2. Words written more than one way. Most of this is harmless - farmers
     themselves write baarish and barish - and nothing here is corrected
     automatically. It is a list to read, not a list to act on. What is worth
     acting on is a term that is formulaic rather than phonetic: a unit, a
     scheme name, a crop name, a figure's qualifier.

Costs no model calls and no network.

Usage:  python -m tools.check_romanisation [--limit N]
"""
import argparse
import collections
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402
import output_guards  # noqa: E402

UNIT_SLOT = re.compile(rf"\b([A-Za-z]{{2,12}})\s+(?:{output_guards.UNIT_NOUNS})\b", re.I)
WORD = re.compile(r"[A-Za-z]{4,}")

# Spellings that differ only in vowel length or a doubled consonant are the same
# romanisation, not different words. Folding those together groups baarish with
# barish without merging unrelated English words the way dropping every vowel
# would - "from" and "farm" stay apart.
def fold(word: str) -> str:
    w = word.lower()
    for long, short in (("aa", "a"), ("ee", "i"), ("ii", "i"),
                        ("oo", "u"), ("uu", "u"), ("chh", "ch")):
        w = w.replace(long, short)
    return re.sub(r"(.)\1+", r"\1", w)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="only the most recent N answers")
    args = ap.parse_args()

    if not db.init():
        print("Database unavailable")
        return 1
    try:
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT body FROM messages WHERE direction = 'outbound'"
                " AND body IS NOT NULL ORDER BY created_at DESC"
                + (" LIMIT %s" % args.limit if args.limit else "")
            ).fetchall()
    finally:
        db.close()

    answers = [r[0] for r in rows]
    print(f"{len(answers)} answer(s) scanned\n")

    print("What sits in front of a unit of measure")
    slot = collections.Counter()
    escaped = collections.Counter()
    for answer in answers:
        for word in UNIT_SLOT.findall(answer):
            slot[word.lower()] += 1
            if word.lower() not in output_guards.PER_ALLOWED:
                # The guard runs before an answer is sent, so anything still
                # here is a form it does not recognise.
                if output_guards.fix_units(f"{word} quintal")[1] is False:
                    escaped[word.lower()] += 1
    for word, n in slot.most_common():
        mark = "  " if word in output_guards.PER_ALLOWED else "??"
        print(f"  {mark} {n:4d}  {word}")
    if escaped:
        print("\n  ESCAPED THE GUARD - extend PER_ALLOWED or the distance rule:")
        for word, n in escaped.most_common():
            print(f"       {n:4d}  {word}")
    else:
        print("\n  nothing escaped the guard")

    print("\nWords written more than one way (read, do not auto-correct)")
    counts = collections.Counter()
    for answer in answers:
        counts.update(w.lower() for w in WORD.findall(answer))
    groups = collections.defaultdict(list)
    for word, n in counts.items():
        groups[fold(word)].append((word, n))
    interesting = []
    for spellings in groups.values():
        if len(spellings) > 1 and sum(n for _, n in spellings) >= 3:
            interesting.append(sorted(spellings, key=lambda x: -x[1]))
    for spellings in sorted(interesting, key=lambda s: -sum(n for _, n in s)):
        print("   " + ", ".join(f"{w} x{n}" for w, n in spellings))
    if not interesting:
        print("   none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
