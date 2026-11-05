"""
The News page's backend: only known places, headlines parsed cleanly, cached.

/news fetches from Google News on the server, so it must not become a way to
run arbitrary searches through it: only a known Indian state (or "India") is
ever put in the query. Checked against a saved feed - no network.

Run: python eval/test_news.py
"""
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

print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)
