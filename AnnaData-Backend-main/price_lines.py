"""
Reported mandi prices, written by code under the answer - never by the model.

Left to write prices itself, the model rounded ("about Rs 800" for a reported
810), averaged several markets into one figure, or, with no data at all,
invented one ("2200 रुपये", 11 November). output_guards removes such
sentences, but the farmer then gets no price at all. The exact figures are
already in the mandi data, so they are copied from it here, in the language
the answer is written in, and the model is told to describe them in words
without writing any amount.

Every figure in the block is a field of a published data.gov.in row: market,
commodity, arrival date, modal, minimum and maximum price per quintal.
"""
from __future__ import annotations

import re

# The marker that ends every heading, whatever the language: voice mode finds
# the block by it to read it after the streamed answer.
SOURCE = "(data.gov.in)"
MAX_LINES = 3

_ROW = re.compile(
    r"Market:\s*(?P<market>[^|]+?)\s*\|\s*Commodity:\s*(?P<commodity>[^|(]+?)\s*"
    r"(?:\((?P<variety>[^)]*)\))?\s*\|.*?Arrival Date:\s*(?P<date>[^|]+?)\s*\|\s*"
    r"Min Price:\s*Rs\s*(?P<min>[\d.,]+)\s*\|\s*Max Price:\s*Rs\s*(?P<max>[\d.,]+)\s*\|\s*"
    r"Modal Price:\s*Rs\s*(?P<modal>[\d.,]+)")

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")

_HINGLISH = re.compile(
    r"\b(hai|hain|ka|ki|ke|mein|aap|aapke|aapka|kya|nahi|karein|kare|bhav|kripya|aur|ko|"
    r"liye|tha|thi|raha|rahe|abhi|apne|yeh|ye)\b", re.I)

TEMPLATES = {
    "en": ("Reported mandi prices", "{market}, {date}: Rs {modal} per quintal (Rs {low}-{high})"),
    "hinglish": ("Mandi bhav", "{market}, {date}: Rs {modal} prati quintal (Rs {low}-{high})"),
    "hi": ("मंडी भाव", "{market}, {date}: ₹{modal} प्रति क्विंटल (₹{low}–{high})"),
    "bn": ("মান্ডির দাম", "{market}, {date}: ₹{modal} প্রতি কুইন্টাল (₹{low}–{high})"),
    "bn_latin": ("Mandir dam", "{market}, {date}: Rs {modal} proti quintal (Rs {low}-{high})"),
}


def rows(mandi_text: str | None) -> list[dict]:
    """The published rows in the mandi tool's text, in its order."""
    out = []
    for match in _ROW.finditer(mandi_text or ""):
        row = {k: (v or "").strip() for k, v in match.groupdict().items()}
        out.append(row)
    return out


def _amount(value: str) -> str:
    try:
        number = float(value.replace(",", ""))
    except ValueError:
        return value
    return f"{number:,.0f}" if number.is_integer() else f"{number:,.2f}"


def _date(value: str) -> str:
    match = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", value.strip())
    if not match:
        return value
    day, month, year = int(match[1]), int(match[2]), match[3]
    if not 1 <= month <= 12:
        return value
    return f"{day} {MONTHS[month - 1]} {year}"


def language_of(answer: str) -> str:
    """Which template matches the answer the block sits under."""
    from Agent import latin_bengali, script_of  # local: Agent imports this module
    script = script_of(answer or "")
    if script == "Devanagari":
        return "hi"
    if script == "Bengali":
        return "bn"
    if latin_bengali(answer or ""):
        return "bn_latin"
    return "hinglish" if len(set(w.lower() for w in _HINGLISH.findall(answer or ""))) >= 2 else "en"


def block(mandi_text: str | None, answer: str) -> str:
    """The price lines for this answer, or "" when the data holds no rows."""
    found = rows(mandi_text)
    if not found:
        return ""
    heading, line = TEMPLATES[language_of(answer)]
    lines = []
    for row in found[:MAX_LINES]:
        market = row["market"]
        commodity = row["commodity"]
        if row.get("variety") and row["variety"].lower() not in ("other", "n/a", commodity.lower()):
            commodity = f"{commodity} ({row['variety']})"
        lines.append("- " + line.format(market=f"{market} - {commodity}", date=_date(row["date"]),
                                        modal=_amount(row["modal"]), low=_amount(row["min"]),
                                        high=_amount(row["max"])))
    return f"**{heading} {SOURCE}:**\n" + "\n".join(lines)


def append(answer: str, mandi_text: str | None) -> tuple[str, bool]:
    """The answer with the reported prices under it."""
    text = block(mandi_text, answer)
    if not text or SOURCE in (answer or ""):
        return answer, False
    return f"{(answer or '').rstrip()}\n\n{text}", True


# Told to the model beside the mandi data, so it describes the prices instead
# of writing amounts the guard would then have to remove.
INSTRUCTION = (
    "(The exact reported prices from these rows are shown to the farmer under "
    "your answer by the system. Do NOT write any rupee amount from them yourself. "
    "Say in words which markets reported and how recent the data is, whether the "
    "prices look high or low, and what it means for selling; the figures are listed "
    "below your answer.)"
)
