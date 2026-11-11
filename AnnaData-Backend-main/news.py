"""
Farming news for the farmer's own state, from Google News, else Bing News.

The web app's News page. Headlines only - title, source, time, link - each
opening the publisher's own article. AnnaData does not check, summarise or
rewrite them, and the page says so: a headline is not advice, and the system's
grounding rules (doses from the register, prices from data.gov.in) do not reach
a newspaper.

Google News' public RSS search is asked for the past week's farming stories
naming the state, in Hindi and in English, merged and deduplicated. Only a
known Indian state or "India" is accepted as the place, so this cannot be
turned into a way to fetch arbitrary searches, and each answer is kept for half
an hour so a page of farmers opening News costs Google one request.

WHY THERE IS A SECOND SOURCE. Google News answers HTTP 503 to every request
from Cloud Run's addresses (seen in the logs on 11 November 2026 for every state
and both languages), while the same search from a home connection returns a
full feed. Google blocks data-centre traffic to this endpoint; nothing in the
query is wrong. So when Google fails, or finds nothing, the same language is
asked of Bing News' RSS search. Bing matches loosely - "mandi" also finds Mandi
town in Himachal - so its headlines are kept only if they name farming and are
from the past week, and its links are unwrapped to the publisher's own address.

WHEN EVERY SOURCE FAILS the last good answer for that place is shown for up to
a day, marked stale, and failing that the reply says `unavailable` - so the app
can say the news could not be fetched, rather than that there was no news.
"""
from __future__ import annotations

import html
import re
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, quote_plus, urlparse

import requests

STATES = {
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh", "Goa",
    "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka", "Kerala",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland",
    "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
    "Uttar Pradesh", "Uttarakhand", "West Bengal", "Jammu and Kashmir", "Ladakh",
    "Delhi", "Puducherry",
}
_BY_LOWER = {s.lower(): s for s in STATES}

# Bing's Hindi search needs the state's Hindi name; Google is given the English.
HINDI_NAMES = {
    "Andhra Pradesh": "आंध्र प्रदेश", "Arunachal Pradesh": "अरुणाचल प्रदेश", "Assam": "असम",
    "Bihar": "बिहार", "Chhattisgarh": "छत्तीसगढ़", "Goa": "गोवा", "Gujarat": "गुजरात",
    "Haryana": "हरियाणा", "Himachal Pradesh": "हिमाचल प्रदेश", "Jharkhand": "झारखंड",
    "Karnataka": "कर्नाटक", "Kerala": "केरल", "Madhya Pradesh": "मध्य प्रदेश",
    "Maharashtra": "महाराष्ट्र", "Manipur": "मणिपुर", "Meghalaya": "मेघालय", "Mizoram": "मिजोरम",
    "Nagaland": "नागालैंड", "Odisha": "ओडिशा", "Punjab": "पंजाब", "Rajasthan": "राजस्थान",
    "Sikkim": "सिक्किम", "Tamil Nadu": "तमिलनाडु", "Telangana": "तेलंगाना", "Tripura": "त्रिपुरा",
    "Uttar Pradesh": "उत्तर प्रदेश", "Uttarakhand": "उत्तराखंड", "West Bengal": "पश्चिम बंगाल",
    "Jammu and Kashmir": "जम्मू-कश्मीर", "Ladakh": "लद्दाख", "Delhi": "दिल्ली", "Puducherry": "पुडुचेरी",
}

FEEDS = {
    "hi": "hl=hi&gl=IN&ceid=IN:hi",
    "en": "hl=en-IN&gl=IN&ceid=IN:en",
}
TOPIC = {
    "hi": "(kisan OR किसान OR खेती OR मंडी OR फसल)",
    "en": "(farmers OR agriculture OR mandi OR crop)",
}
BING_MARKETS = {"hi": "hi-IN", "en": "en-IN"}

# A Bing headline is kept only if it names farming. Google's search already
# requires such words; Bing treats them as hints.
FARMING = re.compile(
    r"farmer|farming|agricultur|\bcrops?\b|harvest|sowing|paddy|wheat|\brice\b|kharif|\brabi\b|"
    r"\bmsp\b|fertili[sz]er|\burea\b|pesticide|irrigation|monsoon|procure|cultivat|kisan|"
    r"किसान|खेती|कृषि|फसल|बुवाई|धान|गेहूं|गेहूँ|खाद|सिंचाई|मंडी भाव|एमएसपी|उर्वरक|पैदावार",
    re.I,
)

CACHE_SECONDS = 1800
STALE_SECONDS = 24 * 3600
WEEK_SECONDS = 7 * 24 * 3600
MAX_ITEMS = 20
USER_AGENT = "Mozilla/5.0 (compatible; AnnaData news/1.0)"

_cache: dict[tuple, tuple[float, list]] = {}
_lock = threading.Lock()


def place(raw: str | None) -> str:
    """A known state, matched without regard to case, or 'India'."""
    return _BY_LOWER.get((raw or "").strip().lower(), "India")


def _publisher_link(link: str) -> str:
    """Bing wraps each article in a click-counting redirect; open the article."""
    if "bing.com/news/apiclick" in link:
        target = parse_qs(urlparse(link).query).get("url", [""])[0]
        return target if target.startswith("https://") else ""
    return link


def _parse(xml: str, lang: str) -> list[dict]:
    items = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
        def field(tag):
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
            return html.unescape(m.group(1)).strip() if m else ""
        title, link = field("title"), _publisher_link(field("link"))
        # Google's <source>; Bing's <News:Source>.
        source = field("source") or field("News:Source")
        # Google appends " - Publisher" to every title; the source is shown apart.
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3].strip()
        try:
            published = parsedate_to_datetime(field("pubDate")).isoformat()
        except Exception:  # noqa: BLE001
            published = None
        if "pakistan" in source.lower():
            continue
        if title and link.startswith("https://"):
            items.append({"title": title, "link": link, "source": source,
                          "published": published, "lang": lang})
    return items


def _fetch(state: str, lang: str) -> list[dict]:
    """Google News: the week's farming stories naming the state."""
    where = "" if state == "India" else f' "{state}"'
    # "Punjab" is also a province of Pakistan, and its farm news ranks well.
    query = quote_plus(f"{TOPIC[lang]}{where} -Pakistan when:7d")
    url = f"https://news.google.com/rss/search?q={query}&{FEEDS[lang]}"
    response = requests.get(url, timeout=10, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return _parse(response.text, lang)


def _bing_filter(items: list[dict], now: float | None = None) -> list[dict]:
    """Bing's results that name farming and are from the past week."""
    cutoff = (now or time.time()) - WEEK_SECONDS
    kept = []
    for item in items:
        if not FARMING.search(item["title"]):
            continue
        if item["published"]:
            try:
                if datetime.fromisoformat(item["published"]).timestamp() < cutoff:
                    continue
            except ValueError:
                pass
        kept.append(item)
    return kept


def _fetch_bing(state: str, lang: str) -> list[dict]:
    """Bing News: the same week, kept only where the headline names farming."""
    if lang == "hi":
        query = "किसान खेती" if state == "India" else f"किसान {HINDI_NAMES.get(state, state)}"
    else:
        query = "farmers agriculture India" if state == "India" else f'farmers "{state}"'
    url = (f"https://www.bing.com/news/search?q={quote_plus(query)}"
           f"&format=rss&mkt={BING_MARKETS[lang]}")
    response = requests.get(url, timeout=10, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return _bing_filter(_parse(response.text, lang))


def headlines(state: str | None, langs=("hi", "en")) -> dict:
    """The week's farming headlines for this state, newest first.

    Each language is asked of Google first, and of Bing when Google fails or
    finds nothing. `stale` marks an earlier answer shown because every source
    failed now; `unavailable` means every source failed and there was no
    earlier answer to show.
    """
    where = place(state)
    key = (where, tuple(langs))
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return {"place": where, "items": hit[1], "cached": True}

    items, seen = [], set()
    answered = False  # did any source reply at all, even with nothing?
    for lang in langs:
        for name, fetch in (("Google", _fetch), ("Bing", _fetch_bing)):
            try:
                fetched = fetch(where, lang)
            except Exception as e:  # noqa: BLE001
                print(f"News fetch failed for {where} ({lang}, {name}): {type(e).__name__}: {e}")
                continue
            answered = True
            if not fetched:
                continue
            for item in fetched:
                mark = re.sub(r"\W+", "", item["title"].lower())[:60]
                if mark not in seen:
                    seen.add(mark)
                    items.append(item)
            break
    items.sort(key=lambda i: i["published"] or "", reverse=True)
    items = items[:MAX_ITEMS]
    if items:
        with _lock:
            _cache[key] = (now, items)
        return {"place": where, "items": items, "cached": False}
    if not answered:
        with _lock:
            hit = _cache.get(key)
        if hit and now - hit[0] < STALE_SECONDS:
            return {"place": where, "items": hit[1], "cached": True, "stale": True}
        return {"place": where, "items": [], "cached": False, "unavailable": True}
    return {"place": where, "items": [], "cached": False}
