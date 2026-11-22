"""
First-impression check: ask the live app what a newcomer asks, and check every
answer for the mistakes already found in real conversations.

    python tools/first_impression.py
    python tools/first_impression.py --base https://annadata-backend-...run.app

Run it after every backend deploy. It asks about 25 fixed questions in the
conditions that went wrong before - no location, a phone in Kharagpur, a new
chat, the middle of a conversation, Hindi, Hinglish and Bengali - and checks
each answer automatically. It prints a summary, writes
first_impression_report.md next to this backend folder, and exits 1 if anything
FAILed, so it can gate a deploy later.

Every check comes from the review of the 22 November conversation export:
a price "not available, go to the APMC" with nothing looked up, invented
prices, "no MSP" for wheat, doses with no registered match, per acre for a
per-hectare dose, goodbyes to real questions, a lecture in reply to "thanks",
the name in the wrong script, internal jargon, and the photo question sent
for a silent voice note.

Standard library only, so it runs anywhere Python 3.9+ does. It asks as three
fixed test guests (TEST_GUESTS below); add them once to ANALYTICS_TEST_USERS
on Cloud Run so these questions never count as farmers:

    guest:5e1f0c3a-7b2d-4c8e-9f10-a1b2c3d4e5f1,guest:5e1f0c3a-7b2d-4c8e-9f10-a1b2c3d4e5f2,guest:5e1f0c3a-7b2d-4c8e-9f10-a1b2c3d4e5f3

Each guest may ask 10 questions an hour, so the questions are spread across
the three; running the check twice within an hour can hit that limit.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import struct
import sys
import time
import urllib.error
import urllib.request
import uuid
import wave
from datetime import datetime
from pathlib import Path

DEFAULT_BASE = "https://annadata-backend-262478589299.asia-south1.run.app"
TEST_GUESTS = [f"5e1f0c3a-7b2d-4c8e-9f10-a1b2c3d4e5f{i}" for i in (1, 2, 3)]
KHARAGPUR = (22.34, 87.30)
REPORT = Path(__file__).resolve().parents[1] / "first_impression_report.md"

# --- what the answers are checked for ---------------------------------------

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
BENGALI = re.compile(r"[ঀ-৿]")

GOODBYE = re.compile(
    r"jab bhi (?:koi )?zaroorat|jab bhi zarurat|phir se (?:message|sampark|pooch)|"
    r"reach out (?:again|whenever)|feel free to reach out|फिर से संपर्क|जब भी .{0,20}ज़रूरत|"
    r"जब भी .{0,20}जरूरत|আবার যোগাযোগ", re.I)
NOT_AVAILABLE = re.compile(r"uplabdh nahi|available nahi|not available|उपलब्ध नहीं|উপলব্ধ নয়|পাওয়া যাচ্ছে না", re.I)
SEND_AWAY = re.compile(r"\bapmc\b|मंडी (?:में )?(?:जाकर|सम्पर्क|संपर्क)|mandi (?:mein )?(?:jakar|sampark)", re.I)
JARGON = re.compile(r"JHULSACAST|threshold|risk level|\bdataset\b|the Context|language model|\bLLM\b", re.I)
NAME_MISSPELT = re.compile(r"अन्नाडेटा|अन्नाडाटा|आन्नाडाटा|আন্নাডাটা|আন্নাডেটা|অন্নাডাটা")
MONEY = re.compile(r"(?:₹|\brs\.?)\s*[\d,]{3,}|[\d,]{3,}\s*(?:rupaye|rupees|रुपये|रुपए|টাকা)", re.I)
CHEMICAL_DOSE = re.compile(
    r"\b\d{1,3}(?:\.\d+)?\s*%\s*(?:EC|SC|WP|SP|WG|SL|GR|CS|SE|OD|FS|WDG|EW|ZC)\b.{0,120}?"
    r"\d[\d.,\s\-–]*\s*(?:ml|gm|gram|g|kg|litre|liter|ग्राम|मिली|किलो|लीटर)", re.I | re.S)
PER_ACRE = re.compile(r"(?:per|prati|प्रति)\s*(?:acre|ekad|एकड़|एकड)", re.I)
MSP_DENIAL = re.compile(r"(?:\bmsp\b|support price|samarthan|समर्थन मूल्य|एमएसपी).{0,80}?"
                        r"(?:\bnahi\b|\bnot\b|\bno\b|नहीं|घोषित नहीं)|"
                        r"(?:\bno\b|koi|कोई).{0,40}?(?:\bmsp\b|support price|समर्थन मूल्य)", re.I | re.S)
PRICE_BLOCK = "(data.gov.in)"


def words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def outside_price_block(answer: str) -> str:
    at = answer.find(PRICE_BLOCK)
    if at < 0:
        return answer
    return answer[:answer.rfind("\n\n", 0, at) if answer.rfind("\n\n", 0, at) >= 0 else at]


def check_answer(case: dict, reply: dict) -> list[tuple[str, str]]:
    """(level, message) for everything wrong with one answer."""
    found = []
    answer = reply.get("answer") or ""
    if not answer.strip():
        return [("FAIL", "no answer at all")]
    tools = reply.get("tools_used") or []
    dose_status = reply.get("dose_status")
    language = case.get("language")

    # The language and script of the reply.
    if language == "hinglish" and (DEVANAGARI.search(answer) or BENGALI.search(answer)):
        other = len(DEVANAGARI.findall(answer)) + len(BENGALI.findall(answer))
        latin = len(re.findall(r"[A-Za-z]", answer))
        if other > latin:
            found.append(("FAIL", "a Hinglish question answered in another script"))
        else:
            stray = re.findall(r"[\u0900-\u097F\u0980-\u09FF]+", answer)
            found.append(("WARN", f"a word in another script inside Hinglish: {' '.join(stray[:3])}"))
    if language == "hinglish" and re.search(r"\b(the|you|your|please|is|are)\b", answer, re.I) \
            and not re.search(r"\b(hai|hain|aap|kya|ke|ki|mein)\b", answer, re.I):
        found.append(("FAIL", "a Hinglish question answered in English"))
    if language == "hindi" and not DEVANAGARI.search(answer):
        found.append(("FAIL", "a Hindi question answered without Devanagari"))
    if language == "bengali" and not BENGALI.search(answer):
        found.append(("FAIL", "a Bengali question answered without Bengali script"))
    if language == "bengali_latin" and (re.search(r"\b(the|you|your|please)\b", answer, re.I)
                                        or DEVANAGARI.search(answer)):
        found.append(("FAIL", "Bengali in Latin letters answered in English or Hindi"))

    # The service's name.
    if NAME_MISSPELT.search(answer):
        found.append(("FAIL", "the name spelt letter by letter"))
    if language in ("hinglish", "english", "bengali_latin") and "অন্নদাতা" in answer:
        found.append(("FAIL", "the name in Bengali letters inside a Latin-script answer"))
    if language == "hindi" and "অন্নদাতা" in answer:
        found.append(("FAIL", "the name in Bengali letters inside a Hindi answer"))

    if JARGON.search(answer):
        found.append(("FAIL", f"internal jargon: {JARGON.search(answer).group(0)!r}"))

    # Prices.
    if "mandi" not in tools and NOT_AVAILABLE.search(answer) and SEND_AWAY.search(answer):
        found.append(("FAIL", "says the price is not available and sends them to the APMC, "
                              "with no market looked up"))
    for match in MSP_DENIAL.finditer(answer):
        if re.search(r"gehu|gehun|wheat|गेहूं|गेहूँ|dhan|dhaan|paddy|धान|chana|चना|sarson|सरसों|"
                     r"bajra|बाजरा|makka|मक्का|kapas|cotton|कपास", answer, re.I):
            found.append(("FAIL", "says there is no MSP, in an answer about a crop that has one"))
            break
    if MONEY.search(outside_price_block(answer)) and not {"msp", "kb"} & set(tools):
        found.append(("WARN", "a rupee amount written in the answer itself, not from the listed data"))

    # Doses.
    if dose_status != "available" and CHEMICAL_DOSE.search(answer):
        found.append(("FAIL", "a chemical and an amount, though nothing was registered for this pest"))
    if CHEMICAL_DOSE.search(answer) and PER_ACRE.search(answer):
        found.append(("FAIL", "a registered dose quoted per acre (the register is per hectare)"))

    # Small talk.
    kind = case.get("kind")
    if kind in ("question", "statement") and GOODBYE.search(answer):
        found.append(("FAIL", "a goodbye in reply to something that was not a goodbye"))
    if kind == "smalltalk" and words(answer) > 45:
        found.append(("FAIL", f"{words(answer)} words in reply to small talk"))
    if kind == "greeting" and words(answer) > 60:
        found.append(("FAIL", f"a {words(answer)}-word greeting"))

    seconds = reply.get("_seconds") or 0
    if seconds > 20:
        found.append(("WARN", f"took {seconds:.0f} seconds"))

    # What this case in particular must do.
    for level, message, test in case.get("expect", []):
        try:
            ok = test(answer, reply)
        except Exception as e:  # noqa: BLE001
            ok, message = False, f"{message} (check failed: {e})"
        if not ok:
            found.append((level, message))
    return found


# --- the questions -------------------------------------------------------------

ASKED = [{"role": "user", "content": "gehu ki buwai kab karein"},
         {"role": "assistant", "content": "November mein karein. Kya aapne beej le liya hai?"}]


def has(pattern):
    return lambda answer, reply: re.search(pattern, answer, re.I) is not None


def lacks(pattern):
    return lambda answer, reply: re.search(pattern, answer, re.I) is None


def tool(name):
    return lambda answer, reply: name in (reply.get("tools_used") or [])


CASES = [
    # Home-screen samples, as a newcomer on a laptop: no location, new chat.
    dict(q="Aaj aalu ka mandi bhav kya hai?", language="hinglish", kind="question",
         title="Home sample: potato price, no location",
         expect=[("FAIL", "asks for the state or mandi", has(r"rajya|state|mandi ka naam|nazdiki mandi"))]),
    dict(q="Gehu ki buwai kab karein?", language="hinglish", kind="question",
         title="Home sample: wheat sowing, no location"),
    dict(q="Kapas me sundi lag gayi hai, kya spray karu?", language="hinglish", kind="question",
         title="Home sample: cotton bollworm",
         expect=[("FAIL", "gives a registered dose", lambda a, r: r.get("dose_status") == "available")]),
    # The same, from a phone in Kharagpur.
    dict(q="Aaj aalu ka mandi bhav kya hai?", language="hinglish", kind="question", at=KHARAGPUR,
         title="Potato price, phone in Kharagpur",
         expect=[("FAIL", "lists the reported prices under the answer", has(re.escape(PRICE_BLOCK)))]),
    dict(q="Gehu ki buwai kab karein?", language="hinglish", kind="question", at=KHARAGPUR,
         title="Wheat sowing, phone in Kharagpur"),
    dict(q="kal barish hogi kya", language="hinglish", kind="question", at=KHARAGPUR,
         title="Weather tomorrow, phone in Kharagpur",
         expect=[("FAIL", "uses the weather data", tool("weather"))]),
    # Support prices.
    dict(q="gehu ka MSP kitna hai", language="hinglish", kind="question",
         title="Wheat MSP", expect=[("FAIL", "gives Rs 2,585", has(r"2,?585"))]),
    dict(q="dhaan ka MSP kitna hai", language="hinglish", kind="question",
         title="Paddy MSP", expect=[("FAIL", "gives Rs 2,369", has(r"2,?369"))]),
    dict(q="Aaj gehu ka mandi bhav kya hai?", language="hinglish", kind="question",
         title="Wheat price, no location (MSP, no APMC send-off)"),
    # Doses.
    dict(q="aloo ke patte kaale pad rahe hain, kya karu?", language="hinglish", kind="question",
         title="Potato, black leaves (no pest named)"),
    dict(q="chane me phali chhedak lag gaya hai kya karu", language="hinglish", kind="question",
         title="Chickpea pod borer"),
    dict(q="धान में तना छेदक लग गया है क्या करूं", language="hindi", kind="question",
         title="Paddy stem borer, in Hindi"),
    dict(q="gehu me peela rog aa gaya hai kya karu", language="hinglish", kind="question",
         title="Wheat yellow rust"),
    # Greetings, new chat.
    dict(q="Hello", language="hinglish", kind="greeting", title="'Hello' opening a chat",
         expect=[("FAIL", "is a greeting", tool("greeting"))]),
    dict(q="नमस्ते", language="hindi", kind="greeting", title="'नमस्ते' opening a chat"),
    dict(q="নমস্কার", language="bengali", kind="greeting", title="'নমস্কার' opening a chat"),
    dict(q="Namaskar, ami Kharagpur e thaki, ekhon ki chash korbo?", language="bengali_latin",
         kind="question", title="Bengali in Latin letters"),
    # Mid-conversation, after the app asked something.
    dict(q="thanks", history=ASKED, language="hinglish", kind="smalltalk",
         title="'thanks' after our question"),
    dict(q="Hello kaise ho tum", history=ASKED, language="hinglish", kind="smalltalk",
         title="'Hello kaise ho' mid-conversation"),
    dict(q="haan", history=ASKED, language="hinglish", kind="question",
         title="'haan' answering our question"),
    dict(q="Main Sitapur Uttar Pradesh mein rehta hoon.", history=ASKED, language="hinglish",
         kind="statement", title="Saying where they live, mid-conversation"),
    dict(q="मौसम कैसा है, समाचार दो", history=ASKED, language="hindi", kind="question",
         title="Weather asked mid-conversation, in Hindi"),
    # Other.
    dict(q="PM-KISAN ke liye kaun apply kar sakta hai?", language="hinglish", kind="question",
         title="Scheme eligibility"),
    dict(q="aaj ka mausam kaisa hai?", language="hinglish", kind="question",
         title="Weather, no location",
         expect=[("FAIL", "asks where they are",
                  lambda a, r: r.get("needs_location") or "location" in (r.get("missing_slots") or [])
                  or re.search(r"kahan|jagah|zila|district|gaon|location", a, re.I))]),
    dict(silent_voice=True, language="hinglish", kind="smalltalk", title="A silent voice note, no photo",
         expect=[("FAIL", "asks them to speak again, not about a photo",
                  lambda a, r: "not_heard" in (r.get("tools_used") or []))]),
]


# --- asking ---------------------------------------------------------------------

def _post(url: str, data: bytes, headers: dict, timeout: int = 120) -> dict:
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        return {"_error": f"HTTP {e.code}: {body}"}
    except Exception as e:  # noqa: BLE001
        return {"_error": f"{type(e).__name__}: {e}"}


def _silent_wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes(struct.pack("<h", 0) * 16000 * 2)
    return buffer.getvalue()


def forget(base: str, guest: str) -> bool:
    """Start the test guest from nothing, so one question cannot shape the next.

    Without it, "Main Sitapur mein rehta hoon" saved Sitapur to the guest and a
    later "aaj ka mausam kaisa hai?" with no location was answered for Sitapur.
    """
    reply = _post(f"{base}/forget", json.dumps({"user_id": f"guest:{guest}"}).encode(),
                  {"X-Guest-Id": guest, "Content-Type": "application/json"}, timeout=30)
    return "_error" not in reply


def ask(base: str, case: dict, guest: str) -> dict:
    headers = {"X-Guest-Id": guest}
    started = time.monotonic()
    if case.get("silent_voice"):
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"audio\"; "
                f"filename=\"voice.wav\"\r\nContent-Type: audio/wav\r\n\r\n").encode() \
            + _silent_wav() + f"\r\n--{boundary}--\r\n".encode()
        reply = _post(f"{base}/agent/media", body,
                      {**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"})
    else:
        payload = {"query": case["q"], "channel": "web", "history": case.get("history", []),
                   "chat_id": str(uuid.uuid4())}
        if case.get("at"):
            payload["latitude"], payload["longitude"] = case["at"]
        reply = _post(f"{base}/agent", json.dumps(payload).encode(),
                      {**headers, "Content-Type": "application/json"})
    reply["_seconds"] = time.monotonic() - started
    return reply


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base", default=DEFAULT_BASE)
    args = parser.parse_args()
    base = args.base.rstrip("/")

    results = []
    can_forget = True
    for i, case in enumerate(CASES):
        guest = TEST_GUESTS[i % len(TEST_GUESTS)]
        if can_forget and not forget(base, guest):
            can_forget = False
            print("  (this backend cannot clear a test guest yet; later questions may "
                  "remember earlier ones)")
        reply = ask(base, case, guest)
        if "_error" in reply:
            problems = [("FAIL", f"request failed: {reply['_error']}")]
        else:
            problems = check_answer(case, reply)
        level = "FAIL" if any(p[0] == "FAIL" for p in problems) else "WARN" if problems else "ok"
        results.append((case, reply, problems, level))
        mark = {"ok": "  ok ", "WARN": " warn", "FAIL": " FAIL"}[level]
        print(f"{mark}  {case['title']}")
        for lvl, message in problems:
            print(f"         {lvl}: {message}")

    failed = sum(1 for r in results if r[3] == "FAIL")
    warned = sum(1 for r in results if r[3] == "WARN")
    summary = f"{len(results) - failed - warned} ok, {warned} warnings, {failed} failed"
    print(f"\n{summary}")

    lines = [f"# First-impression check", "",
             f"{datetime.now():%d %b %Y %H:%M} against `{base}`", "", f"**{summary}**", ""]
    for case, reply, problems, level in results:
        lines.append(f"## {'❌' if level == 'FAIL' else '⚠️' if level == 'WARN' else '✅'} {case['title']}")
        lines.append("")
        lines.append(f"**Asked:** {case.get('q') or '(a silent voice note)'}"
                     + (" — from a phone in Kharagpur" if case.get("at") else "")
                     + (" — mid-conversation" if case.get("history") else ""))
        lines.append("")
        for lvl, message in problems:
            lines.append(f"- **{lvl}:** {message}")
        if problems:
            lines.append("")
        answer = reply.get("answer") or reply.get("_error") or ""
        lines.append("> " + answer.replace("\n", "\n> "))
        lines.append("")
        lines.append(f"<sub>tools: {', '.join(reply.get('tools_used') or []) or '-'} · "
                     f"dose: {reply.get('dose_status') or '-'} · {reply.get('_seconds', 0):.1f}s</sub>")
        lines.append("")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report: {REPORT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
