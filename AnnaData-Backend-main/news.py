"""
Farming news for the farmer's own state, from Google News.

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
"""
from __future__ import annotations

import html
import re
import threading
import time
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

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

FEEDS = {
    "hi": "hl=hi&gl=IN&ceid=IN:hi",
    "en": "hl=en-IN&gl=IN&ceid=IN:en",
}
TOPIC = {
    "hi": "(kisan OR किसान OR खेती OR मंडी OR फसल)",
    "en": "(farmers OR agriculture OR mandi OR crop)",
}
CACHE_SECONDS = 1800
MAX_ITEMS = 20

_cache: dict[tuple, tuple[float, list]] = {}
_lock = threading.Lock()


def place(raw: str | None) -> str:
    """A known state, matched without regard to case, or 'India'."""
    return _BY_LOWER.get((raw or "").strip().lower(), "India")


def _parse(xml: str, lang: str) -> list[dict]:
    items = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
        def field(tag):
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
            return html.unescape(m.group(1)).strip() if m else ""
        title, link, source = field("title"), field("link"), field("source")
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
    where = "" if state == "India" else f' "{state}"'
    # "Punjab" is also a province of Pakistan, and its farm news ranks well.
    query = quote_plus(f"{TOPIC[lang]}{where} -Pakistan when:7d")
    url = f"https://news.google.com/rss/search?q={query}&{FEEDS[lang]}"
    response = requests.get(url, timeout=10, headers={"User-Agent": "AnnaData news"})
    response.raise_for_status()
    return _parse(response.text, lang)


def headlines(state: str | None, langs=("hi", "en")) -> dict:
    """The week's farming headlines for this state, newest first."""
    where = place(state)
    key = (where, tuple(langs))
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return {"place": where, "items": hit[1], "cached": True}

    items, seen = [], set()
    for lang in langs:
        try:
            fetched = _fetch(where, lang)
        except Exception as e:  # noqa: BLE001
            print(f"News fetch failed for {where} ({lang}): {type(e).__name__}: {e}")
            continue
        for item in fetched:
            mark = re.sub(r"\W+", "", item["title"].lower())[:60]
            if mark not in seen:
                seen.add(mark)
                items.append(item)
    items.sort(key=lambda i: i["published"] or "", reverse=True)
    items = items[:MAX_ITEMS]
    if items:
        with _lock:
            _cache[key] = (now, items)
    return {"place": where, "items": items, "cached": False}
