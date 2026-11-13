"""
Load the DPPQ&S pest and disease advisories into the pgvector store - with every
chemical and every dose taken out first.

The advisories (ppqs.gov.in/advisories-section) are the Government of India's
own notes on a pest outbreak: what it looks like, the weather that favours it,
the threshold at which it is worth acting, and the practices that need no
chemical. That is what they are loaded for. Doses already come from the CIB&RC
register, matched on crop and pest in code (knowledge.approved_uses), and a
second source of chemical advice would only be a second way to be wrong. Some
of these advisories are years old and name products that have since been
banned - the white grub advisory recommended phorate, and a later corrigendum
withdrew it. So no sentence naming a chemical or stating a dose is stored.

What is removed, sentence by sentence:
  * a formulation           "Azadirachtin 0.03% WSP", "Fipronil 5 SC"
  * a rate                  "@ 5 ml/litre", "2 g per kg seed", "500 l/ha", "a.i."
  * a chemical by name      every active ingredient in the CIB&RC chemical
                            registers (insecticides, fungicides, herbicides,
                            growth regulators), plus those banned in India
  * a chemical by its shape "-thrin", "-phos", "-cloprid", "-conazole" ...
Biological agents named without a dose ("conserve Trichogramma", "Trichoderma
enriched FYM") are kept: they are practices, not prescriptions.

Also removed: the Hindi letterhead, which was typed in a legacy font and
extracts as noise ("TR qd fugrfi"); the address, signature and copy-to blocks;
and any chunk that repeats one already kept - yellow rust has seven advisories
and pink bollworm eight, so the newest is loaded first and older copies of the
same text are skipped.

    python tools/ingest_advisories.py --dry-run                  # parse, report, store nothing
    python tools/ingest_advisories.py --dry-run --report out.md  # and write what was kept and cut
    python tools/ingest_advisories.py                            # store (needs DATABASE_URL)
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
import knowledge  # noqa: E402
from tools.ingest_docs import chunk, read_pdf  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "data" / "pest_advisories"
CIBRC_DIR = ROOT / "data" / "cibrc"
SOURCE_URL = "https://ppqs.gov.in/advisories-section"

# Downloaded with the advisories but not advisories: the website's STQC
# certificate, an export rule for betel leaves, and the corrigendum withdrawing
# phorate (its point is already enforced by removing every chemical name).
EXCLUDE = {"STQC_0", "issuance_of_psc_0", "corrigendum_on_advisory"}

# Share of five-word runs two chunks must have in common for the older one to
# count as a repeat of the newer.
SIMILAR = 0.6

# --- chemicals --------------------------------------------------------------

# Chemicals that old advisories name and the current register may not: banned,
# withdrawn, restricted or proposed for a ban in India. The register alone
# cannot catch a name it no longer carries, which is how phorate would have
# reached a farmer. Not a legal list - only a list of names to remove.
BANNED = {
    "phorate", "monocrotophos", "endosulfan", "methyl parathion", "parathion",
    "ddt", "aldrin", "dieldrin", "chlordane", "heptachlor", "lindane", "bhc",
    "carbofuran", "triazophos", "dichlorvos", "phosphamidon", "methomyl",
    "fenitrothion", "fenthion", "trichlorfon", "benomyl", "carbaryl",
    "diazinon", "thiometon", "tridemorph", "alachlor", "trifluralin",
    "linuron", "dicofol", "dinocap", "methoxy ethyl mercury", "paraquat",
    "chlorpyriphos", "chlorpyrifos", "quinalphos", "dimethoate",
}

# The register's chemical categories. The bio ones are left out on purpose:
# "Trichoderma" or "Pseudomonas" in a sentence with no dose is a practice.
CHEMICAL_REGISTERS = ("insecticide", "fungicide", "herbicide", "pgr")

# Words a product name carries that are not the chemical.
NAME_NOISE = {
    "granules", "granule", "dust", "liquid", "technical", "tablet", "tablets",
    "powder", "solution", "emulsion", "suspension", "concentrate", "capsule",
    "soluble", "wettable", "water", "dispersible", "flowable", "paste",
    "mixture", "spray", "seed", "treatment", "oil", "acid", "sulphur", "sulfur",
    "copper", "zinc", "sodium", "potassium", "calcium", "ammonium", "salt",
    "methyl", "ethyl", "dimethyl", "plus", "with", "extract", "neem",
}

SHAPE = re.compile(
    r"\b[a-z]{3,}(?:thrin|phos|fos|cloprid|conazole|mectin|niliprole|"
    r"thoxam|carb|zeb|fenuron|sulfuron|valerate|oxystrobin|strobin|"
    r"dazim|mancozeb|thiram|captan)\b", re.I)

# A percent sign as OCR reads it: "5%", "5%o", "5Yo", "5o/o", "20%io".
PCT = r"(?:%\s*i?o?|o/o|Yo)"

FORMULATION = re.compile(
    rf"\d+(?:\.\d+)?\s*{PCT}?\s*(?:EC|WP|SC|SL|WG|WDG|GR|DP|CS|EW|OD|SG|FS|LF|ME|ZC|SP|"
    r"WS|WSP|DS|SE|CG|TB|W/W|W/V)\b"
    rf"|\d+(?:\.\d+)?\s*{PCT}\s*(?:w/w|w/v|a\.?i)"
    # A strength beside a spray material is a dose, botanical or not: "neem
    # oil 0.5%", "NSKE 5%". A percent beside anything else - "10% plants
    # infested", "humidity above 90%" - is a threshold or the weather, and stays.
    rf"|(?:neem|nske|extract|oil|soap|solution|kernel|dasagavya|herbal|"
    rf"formulation)\W+(?:\w+\W+){{0,3}}?\d+(?:\.\d+)?\s*{PCT}"
    rf"|\d+(?:\.\d+)?\s*{PCT}\s*(?:\w+\W+){{0,2}}?(?:neem|nske|extract|oil|soap|"
    rf"solution|dasagavya|herbal)", re.I)

# A quantity of a product. "@" alone is not one: "pheromone traps @ 5 per
# hectare" and "Trichogramma cards @ 1 lakh adults/ha" are practices, and a
# farmer needs the number to carry them out.
RATE = re.compile(
    r"@\s*[\d.,\-– ]+\s*(?:ml|mi|g|gm|gms|gram|grams|kg|l|lit|litre|liter|mg|%)\b"
    r"|\d\s*(?:ml|mi|g|gm|gms|gram|grams|kg|l|lit|litre|litres|liter|liters|mg)"
    r"\s*(?:/|per|\bl\b|1)\s*(?:l\b|lit|litre|liter|ha\b|hectare|acre|kg|plant|tree|m2|sq|"
    r"100\s*l|water)"
    r"|\ba\.?\s?i\.?\b|\bppm\b|\bcfu\b|\d\s*g\s*a\.i"
    # The same, as OCR writes it: "/" read as l or 1, and 1 read as I or l -
    # "5gllit of water @ Ikglha" is 5 g per litre at 1 kg per hectare.
    r"|\d\s*(?:ml|g|gm|kg|l)\s*[/l|1I]\s*(?:lit|litre|liter|l\b|ha\b|acre|kg)"
    r"|@\s*[Il1]?\s*(?:kg|g|gm|ml|l|lit)\s*[/l|1I]\s*(?:ha|acre|lit|l\b|kg)"
    r"|\b(?:g|gm|ml|kg)\s*/\s*(?:l|lit|litre|ha|kg)\b", re.I)


def register_names() -> set[str]:
    """Active-ingredient words from the CIB&RC chemical registers.

    Read from the loaded table when there is a database, otherwise parsed from
    the register PDFs in data/cibrc - so a dry run removes exactly what a real
    run would.
    """
    products = []
    if db.is_available():
        try:
            with db.connection() as conn:
                products = [r[0] for r in conn.execute(
                    "SELECT DISTINCT product FROM pesticide_uses "
                    "WHERE category = ANY(%s)", (list(CHEMICAL_REGISTERS),)).fetchall()]
        except Exception as e:
            print(f"Register lookup failed, reading the PDFs instead: {e}")
    if not products:
        from tools.load_cibrc import parse_pdf
        for category in CHEMICAL_REGISTERS:
            path = CIBRC_DIR / f"{category}.pdf"
            if path.exists():
                products += [u["product"] for u in parse_pdf(path, category)]

    # Only the part of each ingredient before its strength names the chemical:
    # "Chlorantraniliprole 9.3% + Lambda cyhalothrin 4.6% ZC" gives two. Words
    # after the strength are formulation and register prose, and taking those
    # put "control" on the list and cut every sentence about pest control.
    names = set()
    for product in products:
        for part in product.split("+"):
            head = re.split(r"\d", part, maxsplit=1)[0]
            for word in re.findall(r"[A-Za-z][A-Za-z\-]{4,}", head):
                word = word.lower().strip("-")
                if word not in NAME_NOISE and len(word) >= 5:
                    names.add(word)
    return names


# The advisories are letters to state departments. Their requests to
# disseminate, report and coordinate say nothing to a farmer and, retrieved,
# would crowd out the passages that do.
ADMIN = re.compile(
    r"\b(?:it is requested|you are requested|may be requested|kind(?:ly)? notice|"
    r"bring to your|honou?r to|this directorate|disseminat|necessary action|"
    r"action taken|extension functionar|field functionar|rcipmc|cipmc|"
    r"officer[s]? in-?charge|state nodal|e-?mail|further necessary|"
    r"for information|needful action|as you are aware|timely supply|"
    r"training programme|pesticide dealer|annexure|annecxure|list of|"
    r"label claim|registration committee|insecticides act|insecticides rules|"
    r"plant protection adviser|members agreed|looking forward|"
    r"ministry of agriculture|farmers welfare|dated\s*:)", re.I)


def chemical_reason(sentence: str, names: set[str]) -> str | None:
    """Why this sentence must not be stored, or None if it may be."""
    low = sentence.lower()
    for word in BANNED:
        if re.search(r"\b" + re.escape(word) + r"\b", low):
            return f"off-register: {word}"
    if FORMULATION.search(sentence):
        return "formulation"
    if RATE.search(sentence):
        return "rate"
    words = re.findall(r"[a-z][a-z\-]*", low)
    for word in words:
        if len(word) >= 5 and word.strip("-") in names:
            return f"register: {word}"
    # OCR splits a long name in two - "Thiod icarb" - so each adjacent pair is
    # also tried joined.
    for a, b in zip(words, words[1:]):
        if (a + b).strip("-") in names:
            return f"register: {a}{b}"
    if SHAPE.search(sentence):
        return "chemical name"
    return None


# --- text -------------------------------------------------------------------

BULLET = re.compile(r"^\s*(?:['\"•●▪➢>*\-–o.]|\d{1,2}[.)]|[a-z][.)]|[ivx]+[.)])\s+")
SUBJECT = re.compile(r"\b(?:sub(?:ject)?\s*[.:\-]+|sub\s*:)\s*", re.I)
SIGN_OFF = re.compile(r"yours\s+(?:faithfully|sincerely)|copy\s+(?:to|for)\b", re.I)
ANNEXURE = re.compile(r"^\s*annex(?:ure)?\b", re.I | re.M)


def plausible(token: str) -> bool:
    """Whether a token could be an English word, a number or a Latin name."""
    core = token.strip("'\"()[],.;:!?-–/")
    if not core:
        return True
    if re.fullmatch(r"[\d.,/%\-–]+", core):
        return True
    if not re.fullmatch(r"[A-Za-z][a-z]*(?:[-'][A-Za-z]+)*|[A-Z]{2,6}s?", core):
        return False
    low = core.lower()
    if not re.search(r"[aeiouy]", low) and len(low) > 3:
        return False
    if re.search(r"q(?!u)", low):
        return False
    return True


def readable(line: str) -> bool:
    """A line of real text, not the legacy-font Hindi letterhead."""
    tokens = line.split()
    if not tokens:
        return False
    if re.search(r"[{}€™©|]|ffi|ﬁ|ﬀ", line):
        return False
    return sum(plausible(t) for t in tokens) / len(tokens) >= 0.75


def body(text: str) -> str:
    """The advisory itself: from the subject line, minus the signature block."""
    match = SUBJECT.search(text)
    if match:
        text = text[match.start():]
    sign = SIGN_OFF.search(text)
    if sign:
        annex = ANNEXURE.search(text, sign.end())
        text = text[:sign.start()] + ("\n\n" + text[annex.start():] if annex else "")
    return text


def subject(text: str) -> str:
    match = SUBJECT.search(text)
    if not match:
        return ""
    line = text[match.end():match.end() + 260].replace("\n", " ")
    line = re.split(r"\s(?:-\s*)?reg(?:arding)?\b|\bsir\b|\bmadam\b", line, flags=re.I)[0]
    return re.sub(r"\s+", " ", line).strip(" .:-'")


def year(text: str) -> int:
    """The advisory's year, from its file number or date. 0 when unreadable."""
    head = text[:1500]
    years = [int(y) for y in re.findall(r"(?<!\d)(20[12]\d)(?!\d)", head)
             if 2015 <= int(y) <= 2030]
    return max(years) if years else 0


def paragraphs(text: str) -> list[str]:
    """Readable lines, re-joined into bullets and paragraphs."""
    out, current = [], ""
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            if current:
                out.append(current)
                current = ""
            continue
        if not readable(line):
            continue
        if re.search(r"e-?mail|phone|tele?\s*:|fax|@nic\.in|@gov\.in|krishi bhawan|"
                     r"\bto,?$|^dear sir|^sir,?$|^madam", line, re.I):
            continue
        if BULLET.match(line) and current:
            out.append(current)
            current = BULLET.sub("", line)
        else:
            current = f"{current} {BULLET.sub('', line) if not current else line}".strip()
    if current:
        out.append(current)
    return out


def sentences(paragraph: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;!?])\s+(?=[A-Z(])", paragraph) if s.strip()]


def strip_chemicals(paras: list[str], names: set[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Paragraphs with every chemical sentence removed, and what was removed."""
    kept, removed = [], []
    for para in paras:
        survivors = []
        for s in sentences(para):
            reason = chemical_reason(s, names)
            if reason:
                removed.append((reason, s))
            elif not ADMIN.search(s):
                survivors.append(s)
        text = " ".join(survivors).strip()
        if len(text) >= 25:
            kept.append(text)
    return kept, removed


# --- which crop -------------------------------------------------------------

# Stored canonical, the way knowledge.canonical_crop writes the farmer's crop,
# so the crop filter in knowledge.search matches without translation.
CROP_WORDS = [
    ("cotton", "cotton"), ("paddy", "rice"), ("rice", "rice"),
    ("wheat", "wheat"), ("maize", "maize"), ("corn", "maize"),
    ("sorghum", "sorghum"), ("sugarcane", "sugarcane"), ("sugar cane", "sugarcane"),
    ("chickpea", "chickpea"), ("chick pea", "chickpea"), ("gram (", "chickpea"),
    ("soybean", "soybean"), ("soyabean", "soybean"), ("groundnut", "groundnut"),
    ("mustard", "mustard"), ("potato", "potato"), ("chilli", "chilli"),
    ("brinjal", "brinjal"), ("tomato", "tomato"), ("coconut", "coconut"),
    ("banana", "banana"), ("mango", "mango"), ("apple", "apple"),
    ("citrus", "citrus"), ("papaya", "papaya"), ("cassava", "cassava"),
    ("tea ", "tea"),
    # Pests that name their crop, for files whose subject line did not survive
    # extraction and whose name is all there is.
    ("pbw", "cotton"), ("pink boll", "cotton"), ("faw", "maize"),
    ("fall army", "maize"),
]
# Advisories naming several crops of equal standing are stored for none in
# particular, so they are found by similarity alone.
MULTI_CROP = re.compile(r"green\s*gram.*black\s*gram|locust|monitoring of pests|"
                        r"sub-standard|paclobutrazol", re.I)


def crop_for(subject_line: str, name: str) -> str | None:
    text = f"{subject_line} {name.replace('_', ' ')}".lower() + " "
    if MULTI_CROP.search(text):
        return None
    for word, crop in CROP_WORDS:
        if word in text:
            return crop
    return None


# --- repeats ----------------------------------------------------------------

def shingles(text: str, n: int = 5) -> set:
    words = re.findall(r"[a-z]+", text.lower())
    return {" ".join(words[i:i + n]) for i in range(max(len(words) - n + 1, 1))}


def repeats(candidate: set, seen: list[set]) -> bool:
    for other in seen:
        union = len(candidate | other)
        if union and len(candidate & other) / union >= SIMILAR:
            return True
    return False


# --- the run ----------------------------------------------------------------

def prepare(path: Path, names: set[str]) -> dict:
    raw = read_pdf(path).replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", raw).replace("\r", "\n")
    sub = subject(text)
    paras = paragraphs(body(text))
    kept, removed = strip_chemicals(paras, names)
    return {
        "file": path.name, "stem": path.stem, "chars": len(text.strip()),
        "subject": sub, "year": year(text), "crop": crop_for(sub, path.stem),
        "chunks": chunk("\n\n".join(kept)), "removed": removed,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", help="write what was kept and removed to this file")
    ap.add_argument("--replace", action="store_true",
                    help="delete previously loaded advisories first")
    args = ap.parse_args()

    db.init()
    if not args.dry_run:
        if not db.is_available():
            print("No database. Set DATABASE_URL.")
            return 1
        knowledge.init()

    names = register_names()
    print(f"{len(names)} chemical names from the register, "
          f"{len(BANNED)} banned or off-register")

    files = sorted(Path(args.dir).glob("*.pdf"))
    docs, skipped = [], []
    for f in files:
        if f.stem in EXCLUDE:
            skipped.append((f.name, "not an advisory"))
            continue
        doc = prepare(f, names)
        if doc["chars"] < 200:
            skipped.append((f.name, "scanned image, no text"))
            continue
        docs.append(doc)

    # Newest first, so the repeat check keeps the current version of a text.
    docs.sort(key=lambda d: d["year"], reverse=True)
    seen, stored, total = [], 0, 0
    for doc in docs:
        doc["kept"], doc["dupes"] = [], 0
        for c in doc["chunks"]:
            sh = shingles(c)
            if repeats(sh, seen):
                doc["dupes"] += 1
                continue
            seen.append(sh)
            doc["kept"].append(c)
        if not doc["kept"]:
            skipped.append((doc["file"], "repeats a newer advisory"))
            continue
        total += len(doc["kept"])

    if not args.dry_run:
        if args.replace:
            with db.connection() as conn:
                conn.execute("DELETE FROM documents WHERE kind = %s", (knowledge.PEST_ADVISORY,))
        for doc in docs:
            label = doc["subject"] or doc["stem"].replace("_", " ")
            source = f"DPPQ&S advisory{' ' + str(doc['year']) if doc['year'] else ''}: {label}"
            for i, c in enumerate(doc["kept"]):
                if knowledge.add_document(source=source[:300], content=c, title=doc["stem"],
                                          url=SOURCE_URL, chunk_index=i, tier="official",
                                          kind=knowledge.PEST_ADVISORY, crop=doc["crop"]):
                    stored += 1
            print(f"  stored {stored}/{total}")

    loaded = [d for d in docs if d["kept"]]
    removed = sum(len(d["removed"]) for d in docs)
    print(f"\n{len(files)} files: {len(loaded)} loaded, {len(skipped)} skipped")
    print(f"{total} chunks {'would be stored' if args.dry_run else 'to store'}, "
          f"{removed} chemical sentences removed")
    for name, why in skipped:
        print(f"  skipped {name}: {why}")

    if args.report:
        write_report(Path(args.report), loaded, skipped)
        print(f"report: {args.report}")
    if not args.dry_run:
        print("knowledge store:", knowledge.counts())
    db.close()
    return 0


def write_report(path: Path, docs: list[dict], skipped: list) -> None:
    lines = ["# Pest advisories: what would be loaded", ""]
    for d in sorted(docs, key=lambda d: (d["crop"] or "~", -d["year"])):
        lines += [f"## {d['file']}", "",
                  f"- crop: {d['crop'] or '(any)'} · year: {d['year'] or '?'} · "
                  f"chunks kept: {len(d['kept'])} · repeats skipped: {d['dupes']}",
                  f"- subject: {d['subject'] or '(none found)'}", ""]
        for c in d["kept"]:
            lines += ["> " + c.replace("\n", "\n> "), ""]
        if d["removed"]:
            lines += ["Removed:", ""]
            lines += [f"- [{why}] {s}" for why, s in d["removed"]]
            lines.append("")
    lines += ["## Skipped", ""] + [f"- {n}: {why}" for n, why in skipped]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
