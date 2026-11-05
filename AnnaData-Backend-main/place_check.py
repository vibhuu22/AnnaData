"""Whether a place the parser returned was actually said by the farmer.

The parser reads a place out of every message, and when the message names none
it sometimes supplies one anyway, from what it associates with the crop. "aloo
me jhulsa rog lag gaya hai" - potato blight, no place - came back as
Jalandhar; a potato question from a browser in Kharagpur came back as Shimla,
home of the potato research institute. The invented place was then geocoded,
used for weather and soil instead of the phone's own position, stored on the
profile, and greeted back: "Hello from your fields in Shimla!"

So a place is kept only if it appears in what the farmer wrote - this message
or an earlier one of theirs, never our own replies, which repeat the profile
and would vouch for a wrong place forever. Farmers write place names in Latin,
Devanagari, Bengali and Gurmukhi script and spell them freely, so the
comparison is between consonant skeletons: Shimla, shimla and शिमला are all
"sml"; Kharagpur and खड़गपुर are both "krgpr". The match is deliberately
loose. A real place dropped costs one "which district?"; an invented one kept
silently moves the farm.

Also here: whether the farmer is denying a place ("i am not in shimla"), and
whether two positions are far enough apart that a stored place name no longer
describes where the request came from.
"""
from __future__ import annotations

import math
import re
import unicodedata
from difflib import SequenceMatcher

_VOWELS = set("aeiou")
# Indic letters whose Unicode name would give the wrong sound.
_SPECIAL = {"DDDHA": "r", "RHA": "r", "RRA": "r", "KHANDA TA": "t"}
_INDIC = ("DEVANAGARI", "BENGALI", "GURMUKHI")
_NASAL_SIGNS = ("SIGN ANUSVARA", "TIPPI", "SIGN BINDI")

NEGATIONS = {
    "not", "no", "nahi", "nahin", "nai", "nhi", "nahi.", "na", "isnt", "isn't", "dont", "don't",
    "नहीं", "नही", "ना", "না", "নয়", "নই", "ਨਹੀਂ", "ਨਹੀ",
}
# Short forms farmers use for a state; "up" and "mp" are words too, which
# only means a state is kept that might not have been meant - the old default.
_STATE_SHORT = {
    "uttar pradesh": {"up"}, "madhya pradesh": {"mp"}, "himachal pradesh": {"hp"},
    "andhra pradesh": {"ap"}, "jammu and kashmir": {"jk", "j&k"}, "tamil nadu": {"tn"},
    "west bengal": {"wb"},
}


def _romanise(ch: str) -> str:
    """One character as rough Latin letters; vowels and marks come out empty."""
    if ch.isascii():
        return ch.lower() if ch.isalpha() else ""
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return ""
    if not name.startswith(_INDIC):
        return ""
    if any(sign in name for sign in _NASAL_SIGNS):
        return "n"
    if " LETTER " not in name:
        return ""
    letter = name.split(" LETTER ", 1)[1]
    if letter in _SPECIAL:
        return _SPECIAL[letter]
    if letter.endswith("A") and len(letter) > 1 and not set(letter[:-1].lower()) & _VOWELS:
        return letter[:-1].lower()
    return ""   # an independent vowel


# A consonant followed by a separate nukta, as most keyboards type ड़, is the
# same letter as the precomposed one.
_NUKTA = {"\u0921\u093c": "\u095c", "\u0922\u093c": "\u095d",
          "\u09a1\u09bc": "\u09dc", "\u09a2\u09bc": "\u09dd"}

# Crops named after a place. "shimla mirch" is capsicum, not a farm in Shimla.
_CROP_NAMES = re.compile(r"shimla\s*mirch\w*|शिमला\s*मिर्च\w*|ਸ਼ਿਮਲਾ\s*ਮਿਰਚ\w*", re.I)


def skeleton(text: str) -> str:
    """The consonants of a word, normalised across scripts and spellings."""
    text = str(text or "")
    for pair, single in _NUKTA.items():
        text = text.replace(pair, single)
    latin = "".join(_romanise(ch) for ch in text)
    for old, new in (("x", "ks"), ("q", "k"), ("c", "k"), ("z", "j"), ("f", "p"),
                     ("w", "b"), ("v", "b")):
        latin = latin.replace(old, new)
    latin = "".join(ch for ch in latin if ch not in _VOWELS and ch not in "hy")
    return re.sub(r"(.)\1+", r"\1", latin)


def _words(text: str) -> list[str]:
    return [w for w in re.split(r"[\s,.;:!?()/\-–—'\"]+", str(text or "")) if w]


def _matches(place_skel: str, word_skel: str) -> bool:
    if not place_skel or not word_skel:
        return False
    if word_skel.startswith(place_skel):          # shimla-me, शिमलामें
        return True
    if len(place_skel) <= 3:
        return False
    return SequenceMatcher(None, place_skel, word_skel).ratio() >= 0.8


def _place_words(place: str) -> list[str]:
    # "Paschim Medinipur", "Kharagpur, West Bengal": any significant word will do.
    ignore = {"district", "zila", "jila", "tehsil", "block", "village", "gaon", "city", "india"}
    return [skeleton(w) for w in _words(place) if w.lower() not in ignore and len(skeleton(w)) >= 2]


def _positions(place: str, text: str) -> list[int]:
    """Indexes of the words in `text` that are this place (one word or two joined)."""
    words = _words(_CROP_NAMES.sub(" ", str(text or "")))
    skels = [skeleton(w) for w in words]
    targets = _place_words(place)
    whole = "".join(targets)
    hits = []
    for i, s in enumerate(skels):
        pair = s + (skels[i + 1] if i + 1 < len(skels) else "")
        if any(_matches(t, s) for t in targets) or (len(targets) > 1 and _matches(whole, pair)):
            hits.append(i)
    return hits


def said(place: str | None, texts) -> bool:
    """Whether the farmer wrote this place in any of `texts`."""
    if not place:
        return False
    if not _place_words(place):
        # Too short to compare as a skeleton ("Ooty"): fall back to plain text.
        low = place.strip().lower()
        return any(low and low in str(t or "").lower() for t in texts)
    short = _STATE_SHORT.get(place.strip().lower(), set())
    for text in texts:
        if _positions(place, text):
            return True
        if short and short & {w.lower() for w in _words(text)}:
            return True
    return False


def denied(place: str | None, text: str) -> bool:
    """Whether `text` says the farmer is NOT at this place - "not in shimla",
    "shimla me nahi hoon", "शिमला में नहीं"."""
    if not place:
        return False
    words = [w.lower() for w in _words(_CROP_NAMES.sub(" ", str(text or "")))]
    for i in _positions(place, text):
        window = words[max(0, i - 3): i] + words[i + 1: i + 4]
        if NEGATIONS & set(window):
            return True
    return False


def same_place(a: str | None, b: str | None) -> bool:
    return bool(a and b) and said(a, [b])


def km_apart(lat1, lon1, lat2, lon2) -> float | None:
    if None in (lat1, lon1, lat2, lon2):
        return None
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))
