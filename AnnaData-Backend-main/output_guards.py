"""
Removing figures the retrieved data does not support.

Twice now a prompt instruction has failed to stop the model stating a number it
had no basis for, and both times the fix was to check the output in code rather
than to word the request better.

The first was a support price. Asked for one it did not hold, the model wrote
"the Fair and Remunerative Price for the 2026-27 season is 340 rupees per
quintal" - fluent, specific, invented, and produced despite an explicit
prohibition in the same prompt. The second was a subsidy: retrieval correctly
reported that it covered nothing about solar pumps, the prompt correctly said to
invent no amount, and a percentage appeared anyway in two runs out of four.

The pattern is the same both times. A negative constraint expressed in the same
channel as the generation competes with a fluent continuation, and loses often
enough to matter. Where a figure will be acted upon - a price a harvest is sold
against, a subsidy a farmer travels to claim - the constraint belongs in the
deterministic layer around the model.

Both checks work the same way: a sentence asserting a *scheme or price and a
number together* is removed when nothing retrieved backs it. Sentences that name
the thing without a figure survive, because telling a farmer to ask at the sugar
mill or the district office is useful and true.
"""
import re

# --- what counts as a claim -------------------------------------------------

PRICE_SCHEME = re.compile(
    r"\b(msp|frp|minimum support price|fair and remunerative|"
    r"support price|procurement price|floor price|samarthan mulya)\b",
    re.I,
)

WELFARE_SCHEME = re.compile(
    r"\b(scheme|yojana|yojna|subsidy|subsid(?:ies|ised|y)|anudan|"
    r"pm-?kisan|pmfby|kcc|kisan credit card|fasal bima|crop insurance|"
    r"soil health card|kusum|sarkari yojana)\b",
    re.I,
)

# A quantity that reads as money or a proportion. Bare digits are deliberately
# not enough: a helpline number and a district office address both contain them,
# and removing those sentences would cost the farmer the one useful thing left
# in a refusal.
FIGURE = re.compile(
    r"(?:₹|\brs\.?\b|\binr\b)\s*[\d०-९][\d,०-९]*"
    r"|[\d०-९][\d,०-९]*\s*(?:%|percent|per\s?cent|pratishat|"
    r"rupees?|rupaye|rupaiya|lakh|crore|/-)",
    re.I,
)

# Retrieval says this, verbatim, when nothing it found addresses the question.
KB_UNCOVERED = "The passages retrieved do not answer this specific question"

PRICE_FALLBACK = (
    "I do not have the official support price for this crop on record. "
    "Your local APMC mandi can give you the current rate, and for sugarcane "
    "the cooperative sugar mill publishes the price it pays."
)
SCHEME_FALLBACK = (
    "I do not have the amounts or eligibility rules for that scheme on record. "
    "Your district agriculture office or nearest Krishi Vigyan Kendra can give "
    "you the current figures."
)


# --- the unit a price is quoted in ------------------------------------------
#
# "Rs 3100 prataye quintal". The model writes "prati" most of the time and
# garbles it occasionally: two of five price answers observed in production,
# against none in fourteen local runs of the same model with no fallback and no
# rate limiting in between. It is not a comprehension failure - the model knows
# the word - so there is nothing to explain to it in the prompt, and nothing
# reproducible enough to A/B a fix against.
#
# What makes this fixable in code is that the slot is formulaic. Immediately
# before "quintal" there is essentially one correct Hindi qualifier, so instead
# of enumerating garblings - unbounded, and I would be inventing them - anything
# in that slot that is nearly "prati" and is not a word that legitimately
# belongs there is corrected. That catches garblings nobody has seen yet.
#
# Deliberately narrow. The same corpus shows baarish/barish 10:4, jankari/
# jaankari 12:3 and six spellings of achha; none of those are touched. Hindi
# romanisation has no single standard, farmers write it inconsistently
# themselves, and both spellings read fine. "prataye" is not a variant spelling
# of "prati" - it is a wrong word.
UNIT_NOUNS = (r"quintal|quintals|hectare|hectares|acre|acres|"
              r"kilo|kilos|kilogram|kilograms|litre|litres|liter|liters|bigha")

PER_UNIT = re.compile(rf"\b([A-Za-z]{{3,10}})(\s+(?:{UNIT_NOUNS})\b)", re.I)

# Words that genuinely appear before a unit and must be left alone: the correct
# form itself, its legitimate synonym, the English preposition, and quantities.
PER_ALLOWED = {
    "prati", "pratyek", "per", "each", "har", "one", "two", "three", "half",
    "ek", "dho", "teen", "char", "paanch", "panch", "aadha", "adha", "aadhe",
    "poora", "pura", "sau", "hazaar", "hajar", "kitne", "kitna", "kai", "kuch",
    "aur", "the", "and", "about", "than", "around", "nearly", "approximately",
}
PER_CANONICAL = "prati"
PER_MAX_EDITS = 3


def _edits(a: str, b: str) -> int:
    """Levenshtein distance. Small inputs, so the simple version is fine."""
    if a == b:
        return 0
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1,
                               current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def fix_units(answer: str) -> tuple[str, bool]:
    """Correct a garbled qualifier in front of a unit of measure."""
    changed = False

    def repl(match):
        nonlocal changed
        word, tail = match.group(1), match.group(2)
        lowered = word.lower()
        if lowered in PER_ALLOWED:
            return match.group(0)
        # Only touch tokens that were reaching for this word: the leading "p"
        # keeps quantities and unrelated nouns out of range of the distance
        # test, which is otherwise loose enough to catch a three-edit garble.
        if not lowered.startswith("p"):
            return match.group(0)
        if _edits(lowered, PER_CANONICAL) > PER_MAX_EDITS:
            return match.group(0)
        changed = True
        return PER_CANONICAL + tail

    return PER_UNIT.sub(repl, answer), changed


def _sentences(text: str) -> list[str]:
    return re.split(r"(?<=[.!?।])\s+", text)


def _strip(answer: str, subject: re.Pattern, fallback: str) -> tuple[str, bool]:
    """Drop sentences asserting both the subject and a figure."""
    kept, removed = [], False
    for sentence in _sentences(answer):
        if subject.search(sentence) and FIGURE.search(sentence):
            removed = True
            continue
        kept.append(sentence)

    if not removed:
        return answer, False

    text = " ".join(s for s in kept if s.strip()).strip()
    # Stripping can leave a reply that no longer answers anything.
    if len(text) < 40:
        text = fallback
    return text, True


def scrub(answer: str, gathered: dict) -> tuple[str, bool]:
    """Remove price and scheme figures that nothing retrieved supports.

    Returns the answer and whether anything was removed. Each check is applied
    only when its own evidence is missing, so a retrieved figure is never
    stripped: a farmer who asks what PM-KISAN pays, and whose question retrieval
    actually covered, still gets the amount.
    """
    if not answer:
        return answer, False

    # Spelling, not substance: corrected quietly and not reported as a removal,
    # which is reserved for a figure that had to be taken out.
    answer, _ = fix_units(answer)

    changed = False

    # A support price, with none retrieved for this crop.
    if not gathered.get("msp"):
        answer, hit = _strip(answer, PRICE_SCHEME, PRICE_FALLBACK)
        changed = changed or hit

    # A subsidy or scheme amount, where retrieval ran and covered nothing. If
    # retrieval was not consulted at all there is no claim to check against, and
    # if it returned usable passages the figure may well be theirs.
    kb = gathered.get("kb") or ""
    if kb.startswith(KB_UNCOVERED):
        answer, hit = _strip(answer, WELFARE_SCHEME, SCHEME_FALLBACK)
        changed = changed or hit

    return answer, changed


class SentenceGuard:
    """`scrub`, applied one sentence at a time, for an answer being streamed.

    A streamed sentence is on the farmer's screen - or in their ear - before the
    answer is finished, so it cannot wait for `scrub` to see the whole thing.
    This makes the same decision per sentence: a sentence naming a support
    price or a scheme amount, with a figure in it and no retrieved evidence
    behind it, is never sent. The rule is sentence-scoped in `scrub` too (see
    `_strip`), so nothing it would have kept is dropped here or the reverse.

    The one whole-answer rule - an answer stripped down to under 40 characters
    gets the fallback sentence instead - becomes `closing()`: said at the end,
    after whatever little survived.
    """

    def __init__(self, gathered: dict, doses: dict | None = None):
        self.price = not gathered.get("msp")
        self.scheme = (gathered.get("kb") or "").startswith(KB_UNCOVERED)
        # Products the register listed for the crop but NOT for this pest. A
        # sentence naming one is dropped as it streams, as strip_unmatched_doses
        # drops it from the whole answer.
        self.unmatched = unmatched_products(doses)
        self.figures = unmatched_figures(doses)
        # After a dropped dose sentence, the rest of its paragraph about spraying
        # goes too, as in strip_unmatched_doses. A new line ends the paragraph.
        self.tainted = False
        self.kept = 0
        self.fallback = None

    def check(self, sentence: str) -> str | None:
        """The sentence to send (units corrected), or None to drop it."""
        sentence, _ = fix_units(sentence)
        if self.unmatched:
            if names_any(sentence, self.unmatched, self.figures):
                self.fallback = self.fallback or DOSE_FALLBACK
                self.tainted = not sentence.endswith("\n")
                return None
            if self.tainted and _follows_dose(sentence):
                self.tainted = not sentence.endswith("\n")
                return None
            if "\n" in sentence:
                self.tainted = False
        if FIGURE.search(sentence):
            if self.price and PRICE_SCHEME.search(sentence):
                self.fallback = self.fallback or PRICE_FALLBACK
                return None
            if self.scheme and WELFARE_SCHEME.search(sentence):
                self.fallback = self.fallback or SCHEME_FALLBACK
                return None
        self.kept += len(sentence.strip())
        return sentence

    def closing(self) -> str | None:
        """The fallback, when stripping left almost nothing - as `scrub` does."""
        if self.fallback and self.kept < 40:
            return self.fallback
        return None


# --- the same failure, in the other direction -------------------------------

# Everything above removes a figure the data does not support. This adds one the
# data does support and the model dropped.
#
# Measured on the same photograph and question, four runs in a row: the register
# returned eight products registered against blast on rice - Carbendazim,
# Ediphenphos, Kasugamycin among them - and all four answers told the farmer
# there was no approved treatment on record and to go to their KVK. The same
# question in English, and the same question typed in Hindi without a photo,
# named the products every time. Only the combination failed, and the prompt
# already carried an explicit instruction to give at least one.
#
# So it is the docstring's pattern again with the sign reversed: a positive
# obligation, competing with a long prompt on a small fast model, and losing
# often enough to matter. Refusing a registered dose is not a safe failure - the
# farmer is sent away from an answer the registration authority actually
# provides, which is the one thing this system exists to prevent.
DOSE_HEADING = "Registered for this pest (CIB&RC):"


def _product_skeleton(word: str) -> str:
    # A Latin "c" before e, i or y is said "s" (acephate, cypermethrin), which is
    # how the Indian scripts spell it; place_check's skeleton reads every c as k.
    import place_check
    return place_check.skeleton(re.sub(r"c(?=[eiy])", "s", word.lower()))


def mentions(answer: str, product: str) -> bool:
    """Whether the answer names this product, in any script.

    A Hindi answer writes acephate as एसेफेट. Looking only for the Latin
    spelling took that as "not mentioned" and appended the register's list
    again, in English, under a Hindi answer that had already given the dose -
    and voice mode read the English list aloud.
    """
    if product.lower() in answer.lower():
        return True
    target = _product_skeleton(product)
    if len(target) < 3:
        return False
    import place_check
    return any(_product_skeleton(w).startswith(target) for w in place_check._words(answer))


# --- a dose for a pest the register did not match -----------------------------
#
# When the register has nothing for the pest asked about - or no pest was named
# at all, only a symptom - `approved_uses` still returns what is registered for
# the crop, and `format_uses` hands it over under a WARNING that none of it may
# be recommended. That warning was only a prompt. On production, asked "aloo ke
# patte kaale pad rahe hain" (no disease named, and a week the weather rated
# low for late blight), the model reasoned "black edges, so blight", found
# Chlorothalonil in the list - registered for blight - and quoted its dose per
# hectare. Measured, it was rare (once in seven runs), but a dose for a disease
# nobody established is the one failure this system claims code prevents. So
# it is prevented here: when the pest was not matched, no sentence naming a
# product from that list survives, in any script.

DOSE_FALLBACK = ("No registered treatment is on file for this exact problem, so no "
                 "chemical can be named here. Please show the plant to your Krishi "
                 "Vigyan Kendra or agriculture officer.")

# Shorter heads ("Zinc") are ordinary words and would strip harmless advice.
_MIN_HEAD = 5


def unmatched_products(doses: dict | None) -> list[str]:
    """Active-ingredient names from a crop-level list the pest did not match."""
    if not doses or (doses.get("pest_matched") and doses.get("uses")):
        return []
    heads = []
    for use in doses.get("uses") or []:
        head = re.split(r"[\s\d%(]", (use.get("product") or "").strip())[0]
        if len(head) >= _MIN_HEAD and head.lower() not in (h.lower() for h in heads):
            heads.append(head)
    return heads


def unmatched_figures(doses: dict | None) -> list[str]:
    """The dose amounts of those same rows, as the register writes them.

    A sentence can carry the dose without the product - "875-1250 gram prati
    hectare gholkar chhidkein" after the product was named in the sentence
    before - and that is the same dose for an unestablished disease.
    """
    if not doses or (doses.get("pest_matched") and doses.get("uses")):
        return []
    figures = []
    for use in doses.get("uses") or []:
        amount = (use.get("dose_formulation") or "").strip()
        # A range or a number of three or more digits; "2" or "14" alone would
        # strip ordinary sentences about days and plants.
        if re.fullmatch(r"\d[\d.,]*\s*[-–]\s*\d[\d.,]*|\d{3,}[\d.,]*", amount):
            if amount not in figures:
                figures.append(amount)
    return figures


# Sentences that only make sense beside the dose just removed: "this is a
# registered treatment for blight", "do not harvest for 14 days after spraying".
# Dropped only when they follow a removed sentence in the same paragraph, and
# never when they ask the farmer something.
DOSE_CONTEXT = re.compile(
    r"registered|panjikrit|पंजीकृत|chhidkav|chhidkaav|छिड़काव|छिड़काव|spray|स्प्रे|"
    r"before harvest|harvest|fasal na|katai|kataai|कटाई",
    re.IGNORECASE)


def _follows_dose(sentence: str) -> bool:
    return bool(DOSE_CONTEXT.search(sentence)) and "?" not in sentence


def _norm_range(text: str) -> str:
    return re.sub(r"\s*[-–]\s*", "-", text)


def names_any(text: str, heads: list[str], figures: list[str] = ()) -> bool:
    if any(mentions(text, h) for h in heads):
        return True
    flat = _norm_range(text)
    return any(_norm_range(f) in flat for f in figures)


def strip_unmatched_doses(answer: str, doses: dict | None) -> tuple[str, bool]:
    """Drop every sentence naming a product registered only for other pests.

    Works line by line so a bulleted answer keeps its layout. Returns the
    answer and whether anything was removed.
    """
    heads = unmatched_products(doses)
    figures = unmatched_figures(doses)
    if not answer or not heads:
        return answer, False

    removed = False
    lines_out = []
    for line in answer.split("\n"):
        if not line.strip():
            lines_out.append(line)
            continue
        kept, tainted = [], False
        for s in _sentences(line):
            if names_any(s, heads, figures):
                tainted = removed = True
            elif tainted and _follows_dose(s):
                continue
            else:
                kept.append(s)
        if kept:
            lines_out.append(" ".join(kept))
    if not removed:
        return answer, False

    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines_out)).strip()
    if len(text) < 40:
        return DOSE_FALLBACK, True
    return text, True


def ensure_registered_doses(answer: str, doses: dict | None, pest: str | None) -> tuple[str, bool]:
    """Append the registered uses when they were matched but went unmentioned.

    Only fires when the register actually matched the pest asked about; a
    crop-level list for other pests must still never be offered as a treatment,
    which is what `format_uses` warns the model about and what this respects by
    checking `pest_matched`.

    Returns the answer and whether anything was added.
    """
    if not answer or not doses or not doses.get("pest_matched"):
        return answer, False

    uses = doses.get("uses") or []
    if not uses:
        return answer, False

    # A product is "mentioned" by its active ingredient, which is the first word
    # of the register's name - the answer writes "Carbendazim", the register
    # "Carbendazim 50%WP". Matching the whole string would never hit.
    for use in uses:
        head = (use.get("product") or "").split()[0:1]
        if head and mentions(answer, head[0]):
            return answer, False

    from knowledge import dose_lines  # local: knowledge imports nothing from here

    lines = dose_lines(doses)
    if not lines:
        return answer, False

    label = f" for {pest}" if pest else ""
    block = "\n".join(f"- {line}" for line in lines)
    return (
        f"{answer.rstrip()}\n\n**{DOSE_HEADING}**{label}\n{block}\n\n"
        "_Follow the waiting period before harvest. Confirm with your Krishi "
        "Vigyan Kendra or agriculture officer before spraying._"
    ), True
