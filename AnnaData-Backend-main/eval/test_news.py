"""
The News page's backend: only known places, headlines parsed cleanly, cached.

/news fetches from Google News on the server, so it must not become a way to
run arbitrary searches through it: only a known Indian state (or "India") is
ever put in the query. Checked against a saved feed - no network.

Run: python eval/test_news.py
"""
import os
import time
from datetime import datetime, timezone
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import news

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


print("Which places may be searched")
check("a state, any case", news.place("haryana"), "Haryana")
check("a two-word state", news.place("West Bengal"), "West Bengal")
check("anything else is India", news.place('" OR site:evil.example'), "India")
check("nothing is India", news.place(None), "India")

FEED = """<rss><channel>
<item><title>हरियाणा के बासमती से किसानों की बल्ले-बल्ले - ETV Bharat</title><link>https://news.google.com/rss/articles/abc</link>
<pubDate>Thu, 05 Nov 2026 03:50:47 GMT</pubDate><source url="https://www.etvbharat.com">ETV Bharat</source></item>
<item><title>Not a link we open - X</title><link>javascript:alert(1)</link><pubDate>Thu, 05 Nov 2026 03:50:47 GMT</pubDate><source url="x">X</source></item>
<item><title>Sugarcane price raised &amp; protests planned - ChiniMandi</title><link>https://news.google.com/rss/articles/def</link>
<pubDate>Fri, 30 Oct 2026 05:01:40 GMT</pubDate><source url="https://www.chinimandi.com">ChiniMandi</source></item>
</channel></rss>"""

print("\nReading a feed")
items = news._parse(FEED, "hi")
check("only https links are kept", [i["link"] for i in items],
      ["https://news.google.com/rss/articles/abc", "https://news.google.com/rss/articles/def"])
check("the publisher is taken off the title", items[0]["title"], "हरियाणा के बासमती से किसानों की बल्ले-बल्ले")
check("and kept as the source", items[0]["source"], "ETV Bharat")
check("entities are decoded", items[1]["title"], "Sugarcane price raised & protests planned")
check("the date is read", items[0]["published"][:10], "2026-11-05")

print("\nMerged, deduplicated, cached")
calls = []


def fake_fetch(state, lang):
    calls.append((state, lang))
    return news._parse(FEED, lang)


news._fetch = fake_fetch
news._cache.clear()
first = news.headlines("Haryana")
check("Hindi and English are both asked", calls, [("Haryana", "hi"), ("Haryana", "en")])
check("the same story twice is shown once", len(first["items"]), 2)
check("newest first", first["items"][0]["published"] > first["items"][1]["published"], True)
second = news.headlines("haryana")
check("asked again within the half hour: from the cache", (second["cached"], len(calls)), (True, 2))

print("\nBing, when Google is blocked")
BING = """<rss><channel>
<item><title>Bengal farmers get power subsidy</title>
<link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;aid=&amp;url=https%3a%2f%2feconomictimes.example%2fstory&amp;c=1</link>
<pubDate>Tue, 10 Nov 2026 09:57:00 GMT</pubDate><News:Source>The Economic Times</News:Source></item>
<item><title>Class 9 student gets a BMW</title>
<link>http://www.bing.com/news/apiclick.aspx?url=https%3a%2f%2fx.example%2fbmw</link>
<pubDate>Tue, 10 Nov 2026 09:57:00 GMT</pubDate><News:Source>X</News:Source></item>
<item><title>Paddy procurement begins</title>
<link>http://www.bing.com/news/apiclick.aspx?url=https%3a%2f%2fold.example%2fpaddy</link>
<pubDate>Mon, 01 Jun 2026 09:57:00 GMT</pubDate><News:Source>Old</News:Source></item>
<item><title>Wheat sowing advice</title>
<link>http://www.bing.com/news/apiclick.aspx?url=javascript%3aalert(1)</link>
<pubDate>Tue, 10 Nov 2026 09:57:00 GMT</pubDate><News:Source>Y</News:Source></item>
</channel></rss>"""
parsed = news._parse(BING, "en")
check("Bing's redirect is unwrapped to the publisher", parsed[0]["link"], "https://economictimes.example/story")
check("Bing's source is read", parsed[0]["source"], "The Economic Times")
check("a redirect to a non-https address is dropped", [i["title"] for i in parsed if "Wheat" in i["title"]], [])
now_nov = datetime(2026, 11, 11, tzinfo=timezone.utc).timestamp()
check("only farming headlines from the past week are kept",
      [i["title"] for i in news._bing_filter(parsed, now_nov)], ["Bengal farmers get power subsidy"])


def blocked(state, lang):
    raise RuntimeError("503 Server Error: Service Unavailable")


bing_calls = []
news._fetch = blocked
news._fetch_bing = lambda state, lang: bing_calls.append(lang) or [
    {"title": f"Kisan story {lang}", "link": f"https://e.example/{lang}", "source": "E",
     "published": "2026-11-10T00:00:00+00:00", "lang": lang}]
news._cache.clear()
r = news.headlines("West Bengal")
check("Google blocked: each language comes from Bing", (bing_calls, len(r["items"])), (["hi", "en"], 2))
check("and is not marked unavailable", r.get("unavailable"), None)

news._fetch_bing = blocked
news._cache[("West Bengal", ("hi", "en"))] = (time.time() - 3 * 3600, r["items"])
r = news.headlines("West Bengal")
check("every source failing: the last answer, marked stale", (len(r["items"]), r.get("stale")), (2, True))
news._cache.clear()
r = news.headlines("West Bengal")
check("every source failing and nothing earlier: unavailable, not 'no news'",
      (r["items"], r.get("unavailable")), ([], True))
news._fetch = lambda state, lang: []
news._fetch_bing = lambda state, lang: []
r = news.headlines("Sikkim")
check("sources that answer with nothing: an honest empty week", (r["items"], r.get("unavailable")), ([], None))

print("\nThe state the phone is in")
try:
    os.environ.setdefault("GEMINI_API_KEY", "x")
    from fastapi.testclient import TestClient
    import app as appmod
    from Address_Convertor import Place
except Exception as e:
    print(f"  FastAPI not installed here ({type(e).__name__}); skipping")
    appmod = None
if appmod:
    asked = []
    appmod.news.headlines = lambda state: asked.append(state) or {
        "place": news.place(state), "items": [], "cached": False}
    appmod.reverse = lambda lat, lon: (Place(lat, lon, state="West Bengal") if lat > 0
                                       else Place(lat, lon))
    web = TestClient(appmod.app)
    r = web.get("/news", params={"state": "Haryana", "latitude": 22.34, "longitude": 87.30}).json()
    check("coordinates in West Bengal win over the state sent", (asked[-1], r["state"], r["from"]),
          ("West Bengal", "West Bengal", "location"))
    r = web.get("/news", params={"state": "Haryana", "latitude": -1, "longitude": -1}).json()
    check("a position with no known state falls back to the state sent", (asked[-1], r["from"]),
          ("Haryana", "chosen"))
    r = web.get("/news", params={"state": "Punjab"}).json()
    check("a chosen state, with no position, is used", (r["state"], r["from"]), ("Punjab", "chosen"))
    r = web.get("/news").json()
    check("nothing at all: all India", (r["place"], r["state"], r["from"]), ("India", "", None))

print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)
