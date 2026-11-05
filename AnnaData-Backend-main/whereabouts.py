"""Which place an answer is for, and the few fixed things said about it.

Decided in this order:

  a. a place named in this message
  b. a place the farmer named earlier in this chat - their messages only,
     never our replies, which repeat the profile and would vouch for it forever
  c. the phone's position, when the request carries one
  d. the stored farm - when the request has no position (SMS), or when the
     farm is within FARM_NEAR_KM of the phone, where it is the better name for
     the same ground: a farmer at the mandi in the next town is still farming
     their own village
  e. nothing, and only then is the farmer asked for a village or district

The phone's position is used, never stored. It becomes the farm only when the
farmer says yes to "Is your farm near Kharagpur?", asked at most once a place.

Everything here is decided from facts already in hand, so it costs no model
call and is tested without one (eval/test_whereabouts.py).
"""
from __future__ import annotations

import re
from typing import NamedTuple

import place_check

FARM_NEAR_KM = 50

MESSAGE, CHAT, PHONE, PROFILE = "message", "chat", "phone", "profile"


class Where(NamedTuple):
    source: str | None              # message | chat | phone | profile | None
    name: str | None = None
    state: str | None = None
    district: str | None = None
    kind: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @property
    def known(self) -> bool:
        """Enough to answer for: a name, or at least a position."""
        return bool(self.name) or (self.latitude is not None and self.longitude is not None)

    @property
    def named(self) -> bool:
        """The farmer named it - the only kind of place that may be stored."""
        return self.source in (MESSAGE, CHAT)


def _profile_has_place(profile) -> bool:
    return bool(profile) and bool(profile.get("location_text") or profile.get("latitude") is not None)


def choose(*, named=None, named_in_message=True, geocoded=None, phone=None, profile=None) -> Where:
    """The place to answer for.

    named      - the place name the parser read, already checked as said by
                 the farmer (place_check), or None
    geocoded   - Address_Convertor.Place for `named`, or None
    phone      - Address_Convertor.Place from reverse(), or None when the
                 request carried no coordinates
    profile    - the stored profile, with any denied place already removed
    """
    phone_at = phone if phone is not None and phone.latitude is not None else None

    if named:
        geo = geocoded if geocoded is not None and geocoded.latitude is not None else None
        if geo:
            lat, lon = geo.latitude, geo.longitude
        elif phone_at:
            lat, lon = phone_at.latitude, phone_at.longitude
        else:
            lat, lon = (profile or {}).get("latitude"), (profile or {}).get("longitude")
        return Where(MESSAGE if named_in_message else CHAT, named,
                     state=geo.state if geo else None, district=geo.district if geo else None,
                     kind=geo.kind if geo else None, latitude=lat, longitude=lon)

    if _profile_has_place(profile):
        apart = place_check.km_apart(profile.get("latitude"), profile.get("longitude"),
                                     phone_at.latitude if phone_at else None,
                                     phone_at.longitude if phone_at else None)
        if phone_at is None or (apart is not None and apart <= FARM_NEAR_KM):
            return Where(PROFILE, profile.get("location_text"), state=profile.get("state"),
                         district=profile.get("district"),
                         latitude=profile.get("latitude"), longitude=profile.get("longitude"))

    if phone_at:
        return Where(PHONE, phone_at.name, state=phone_at.state, district=phone_at.district,
                     kind=phone_at.kind, latitude=phone_at.latitude, longitude=phone_at.longitude)
    return Where(None)


def profile_view(profile, where: Where):
    """The profile as this answer should see it: its place is the chosen one.

    A stored Shimla, with the phone in Kharagpur, must not reach the greeting
    or the advice prompt - "Hello from your fields in Shimla!" is exactly what
    this replaces. The phone's position is left out of the place facts too, so
    a first-time guest is not greeted as someone we already know.
    """
    view = dict(profile or {})
    for key in ("location_text", "district", "state", "latitude", "longitude"):
        view.pop(key, None)
    if where.source in (MESSAGE, CHAT, PROFILE):
        view.update(location_text=where.name, state=where.state, district=where.district,
                    latitude=where.latitude, longitude=where.longitude)
    return view


# --- Language -----------------------------------------------------------------
# The same rule as the frontend's asks.js, so a sentence written here and an
# ask shown there come out in the same language for the same answer.

_HINGLISH = re.compile(
    r"\b(hai|hain|karein|kijiye|mein|me|aap|aapke|aapki|ke|ki|ka|nahi|nahin|ya|aur|"
    r"fasal|dawa|hoon|hun|hu|main|mera|meri|mujhe|kya|haan|kahan)\b", re.I)


def language_of(text: str) -> str:
    value = str(text or "")
    if re.search(r"[ঀ-৿]", value):
        return "bn"
    if re.search(r"[਀-੿]", value):
        return "pa"
    if re.search(r"[ऀ-ॿ]", re.sub(r"[।॥]", "", value)):
        return "hi"
    return "hinglish" if len(_HINGLISH.findall(value)) >= 2 else "en"


# --- What is said -------------------------------------------------------------

_USING_PHONE = {
    "en": "Got it, I'll use {place}, where your phone is.",
    "hinglish": "Theek hai, main {place} ke hisaab se bataunga, jahan aapka phone hai.",
    "hi": "ठीक है, मैं {place} के हिसाब से बताऊँगा, जहाँ आपका फ़ोन है।",
    "bn": "ঠিক আছে, আপনার ফোন যেখানে আছে, সেই {place} অনুযায়ী বলব।",
    "pa": "ਠੀਕ ਹੈ, ਮੈਂ {place} ਮੁਤਾਬਕ ਦੱਸਾਂਗਾ, ਜਿੱਥੇ ਤੁਹਾਡਾ ਫ਼ੋਨ ਹੈ।",
}
_USING_PHONE_UNNAMED = {
    "en": "Got it, I'll use where your phone is.",
    "hinglish": "Theek hai, main wahan ke hisaab se bataunga jahan aapka phone hai.",
    "hi": "ठीक है, मैं वहाँ के हिसाब से बताऊँगा जहाँ आपका फ़ोन है।",
    "bn": "ঠিক আছে, আপনার ফোন যেখানে আছে সেই অনুযায়ী বলব।",
    "pa": "ਠੀਕ ਹੈ, ਮੈਂ ਉੱਥੇ ਮੁਤਾਬਕ ਦੱਸਾਂਗਾ ਜਿੱਥੇ ਤੁਹਾਡਾ ਫ਼ੋਨ ਹੈ।",
}
_USING_NAMED = {
    "en": "Got it, I'll use {place}.",
    "hinglish": "Theek hai, main {place} ke hisaab se bataunga.",
    "hi": "ठीक है, मैं {place} के हिसाब से बताऊँगा।",
    "bn": "ঠিক আছে, {place} অনুযায়ী বলব।",
    "pa": "ਠੀਕ ਹੈ, ਮੈਂ {place} ਮੁਤਾਬਕ ਦੱਸਾਂਗਾ।",
}
_DROPPED = {
    "en": "Got it, I won't use {place} any more.",
    "hinglish": "Theek hai, ab main {place} ke hisaab se nahi bataunga.",
    "hi": "ठीक है, अब मैं {place} के हिसाब से नहीं बताऊँगा।",
    "bn": "ঠিক আছে, আর {place} অনুযায়ী বলব না।",
    "pa": "ਠੀਕ ਹੈ, ਹੁਣ ਮੈਂ {place} ਮੁਤਾਬਕ ਨਹੀਂ ਦੱਸਾਂਗਾ।",
}
_FARM_SAVED = {
    "en": "Saved: your farm is near {place}. I'll use it for your advice.",
    "hinglish": "Save kar liya: aapka khet {place} ke paas hai. Ab salah isi ke hisaab se milegi.",
    "hi": "सेव कर लिया: आपका खेत {place} के पास है। अब सलाह इसी के हिसाब से मिलेगी।",
    "bn": "সেভ করা হল: আপনার খেত {place}-এর কাছে। এখন থেকে পরামর্শ এই অনুযায়ী হবে।",
    "pa": "ਸੇਵ ਕਰ ਲਿਆ: ਤੁਹਾਡਾ ਖੇਤ {place} ਦੇ ਨੇੜੇ ਹੈ। ਹੁਣ ਸਲਾਹ ਇਸੇ ਮੁਤਾਬਕ ਮਿਲੇਗੀ।",
}
_FARM_DECLINED = {
    "en": "Okay. I'll answer for where your phone is until you tell me your village or district.",
    "hinglish": "Theek hai. Jab tak aap apna gaon ya zila nahi batate, main aapke phone ki jagah ke hisaab se bataunga.",
    "hi": "ठीक है। जब तक आप अपना गाँव या ज़िला नहीं बताते, मैं आपके फ़ोन की जगह के हिसाब से बताऊँगा।",
    "bn": "ঠিক আছে। আপনি গ্রাম বা জেলার নাম না বলা পর্যন্ত, আপনার ফোনের জায়গা অনুযায়ী বলব।",
    "pa": "ਠੀਕ ਹੈ। ਜਦੋਂ ਤੱਕ ਤੁਸੀਂ ਆਪਣਾ ਪਿੰਡ ਜਾਂ ਜ਼ਿਲ੍ਹਾ ਨਹੀਂ ਦੱਸਦੇ, ਮੈਂ ਤੁਹਾਡੇ ਫ਼ੋਨ ਦੀ ਥਾਂ ਮੁਤਾਬਕ ਦੱਸਾਂਗਾ।",
}


def _say(table, language, **values):
    return table.get(language, table["en"]).format(**values)


def denial_reply(denied: str, where: Where, query: str) -> str:
    """The reply to "i am not in shimla" - the place that will be used instead."""
    language = language_of(query)
    if where.source == PHONE:
        if where.name:
            return _say(_USING_PHONE, language, place=where.name)
        return _say(_USING_PHONE_UNNAMED, language)
    if where.known and where.name:
        return _say(_USING_NAMED, language, place=where.name)
    return _say(_DROPPED, language, place=denied)


def farm_saved(place: str, language: str) -> str:
    return _say(_FARM_SAVED, language, place=place)


def farm_declined(language: str) -> str:
    return _say(_FARM_DECLINED, language)


# --- Yes and no -----------------------------------------------------------------

_YES = {"yes", "yeah", "yep", "yup", "haan", "han", "ha", "haa", "haanji", "hanji", "ji", "jee",
        "sahi", "correct", "right", "ok", "okay", "theek", "thik", "bilkul",
        "हाँ", "हां", "हा", "जी", "हाँजी", "हांजी", "सही", "बिल्कुल",
        "হ্যাঁ", "হাঁ", "হ্যা", "জি", "ঠিক", "ਹਾਂ", "ਹਾਂਜੀ", "ਜੀ", "ਸਹੀ"}
_NO = {"no", "nope", "nahi", "nahin", "nai", "nhi", "na", "naa", "galat", "wrong",
       "नहीं", "नही", "ना", "गलत", "না", "নয়", "ਨਹੀਂ", "ਨਹੀ", "ਨਾ", "ਗਲਤ"}
_HONORIFIC = {"ji", "jee", "जी", "ਜੀ", "জি"}
_FILLER = {"ji", "sir", "bhai", "bhaiya", "hai", "है", "हैं", "ਹੈ", "জি", "है।", "it", "is", "that's", "thats"}


def yes_or_no(text: str) -> bool | None:
    """True for a bare yes, False for a bare no, None for anything else."""
    words = [w for w in re.split(r"[\s,.!?।]+", str(text or "").strip().lower()) if w]
    if not words or len(words) > 4:
        return None
    rest = [w for w in words if w not in _YES and w not in _NO and w not in _FILLER]
    if rest:
        return None
    said_no = any(w in _NO for w in words)
    # "ji" is respect, not assent, when it comes with a no: "ji nahi".
    said_yes = any(w in _YES - _HONORIFIC for w in words)
    if said_no and not said_yes:
        return False
    if said_yes and not said_no:
        return True
    if not said_no and any(w in _HONORIFIC for w in words):
        return True                       # a bare "ji"
    return None


def asked_key(place: str) -> str:
    """How a place is remembered as already asked about."""
    return place_check.skeleton(place) or str(place).strip().lower()
