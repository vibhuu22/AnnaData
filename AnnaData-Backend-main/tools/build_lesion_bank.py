"""
Read labelled photographs into the lesion bank.

    python tools/build_lesion_bank.py --root "../Plant Village Dataset" --per-class 12
    python tools/build_lesion_bank.py --root ... --per-class 12 --dry-run

Two things this script refuses to do quietly.

**It will not use an augmented copy.** The PlantVillage split shipped here has
been pre-augmented with horizontal and vertical flips, and the same source image
appears in more than one split: 905 of the Test split's 1,338 source images are
also in Train. Treating those as independent would inflate every number measured
afterwards. Only files whose name carries no `_flip*` suffix are eligible, and a
source id is used at most once across the whole bank.

**It will not silently invent a crop name.** The directory names are the labels,
mapped explicitly below. A folder the map does not know is skipped and reported,
rather than being lowercased into something the register has never heard of.
"""
import argparse
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import encoding_setup  # noqa: F401,E402

import db  # noqa: E402
import knowledge  # noqa: E402
import lesion_bank  # noqa: E402
from config import MEDIA_MODEL  # noqa: E402
from utils import get_client  # noqa: E402
from google.genai import types  # noqa: E402

# Folder name -> (crop as the register writes it, disease as an extension
# officer writes it, healthy). Crop names are chosen to match what
# knowledge.canonical_crop expects, because a reading that cannot be looked up
# in the register is a reading that cannot produce a dose.
LABELS = {
    "Apple - Apple Scab":                  ("apple", "scab", False),
    "Apple - Black Rot":                   ("apple", "black rot", False),
    "Apple - Cedar Apple Rust":            ("apple", "rust", False),
    "Apple - Healthy":                     ("apple", "healthy", True),
    "Bell Pepper - Bacterial Spot":        ("capsicum", "bacterial spot", False),
    "Bell Pepper - Healthy":               ("capsicum", "healthy", True),
    "Cherry - Healthy":                    ("cherry", "healthy", True),
    "Cherry - Powdery Mildew":             ("cherry", "powdery mildew", False),
    "Corn (Maize) - Cercospora Leaf Spot": ("maize", "grey leaf spot", False),
    "Corn (Maize) - Common Rust":          ("maize", "rust", False),
    "Corn (Maize) - Healthy":              ("maize", "healthy", True),
    "Corn (Maize) - Northern Leaf Blight": ("maize", "leaf blight", False),
    "Grape - Black Rot":                   ("grapes", "black rot", False),
    "Grape - Esca (Black Measles)":        ("grapes", "esca", False),
    "Grape - Healthy":                     ("grapes", "healthy", True),
    "Grape - Leaf Blight":                 ("grapes", "leaf blight", False),
    "Peach - Bacterial Spot":              ("peach", "bacterial spot", False),
    "Peach - Healthy":                     ("peach", "healthy", True),
    "Potato - Early Blight":               ("potato", "early blight", False),
    "Potato - Healthy":                    ("potato", "healthy", True),
    "Potato - Late Blight":                ("potato", "late blight", False),
    "Strawberry - Healthy":                ("strawberry", "healthy", True),
    "Strawberry - Leaf Scorch":            ("strawberry", "leaf scorch", False),
    "Tomato - Bacterial Spot":             ("tomato", "bacterial spot", False),
    "Tomato - Early Blight":               ("tomato", "early blight", False),
    "Tomato - Healthy":                    ("tomato", "healthy", True),
    "Tomato - Late Blight":                ("tomato", "late blight", False),
    "Tomato - Septoria Leaf Spot":         ("tomato", "septoria leaf spot", False),
    "Tomato - Yellow Leaf Curl Virus":     ("tomato", "leaf curl virus", False),
}

AUGMENTED = re.compile(r"_flip(LR|TB)", re.I)
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}

# The free tier allows 15 generateContent requests per minute, per model, per
# project (quota id GenerateRequestsPerMinutePerProjectPerModel-FreeTier). Six
# workers pushed roughly double that and 233 of 348 images came back 429, which
# looked like failure and was only pacing. Requests are metered here instead,
# with a margin, because a bank half-built from whichever calls happened to get
# through is not a sample of anything.
FREE_TIER_RPM = 15
PACED_RPM = 12


class RateLimiter:
    """Let through at most `per_minute` calls, blocking callers that arrive early."""

    def __init__(self, per_minute: int):
        self._interval = 60.0 / max(1, per_minute)
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            due = max(now, self._next)
            self._next = due + self._interval
        delay = due - time.monotonic()
        if delay > 0:
            time.sleep(delay)


RETRY_AFTER = re.compile(r"retry in ([\d.]+)s", re.I)


def with_retry(fn, attempts: int = 4):
    """Run `fn`, honouring the delay the server asks for on a 429.

    The API states how long to wait; guessing an exponential backoff instead
    either wastes time or trips the limit again immediately.
    """
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as e:
            text = str(e)
            if "429" not in text and "RESOURCE_EXHAUSTED" not in text:
                raise
            if attempt == attempts - 1:
                raise
            match = RETRY_AFTER.search(text)
            time.sleep(float(match.group(1)) + 1.0 if match else 20.0)
    return None


def source_id(filename: str) -> str:
    """The original photograph a file derives from, ignoring augmentation."""
    return filename.split("___")[0]


def eligible_files(class_dir: Path) -> list[Path]:
    """Unaugmented images in one class folder, one per source photograph."""
    seen, out = set(), []
    for path in sorted(class_dir.iterdir()):
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if AUGMENTED.search(path.name):
            continue
        sid = source_id(path.name)
        if sid in seen:
            continue
        seen.add(sid)
        out.append(path)
    return out


def read_image(client, path: Path, limiter=None) -> dict | None:
    """One photograph, read into the controlled vocabulary."""
    try:
        uploaded = client.files.upload(file=str(path))
        if limiter:
            limiter.wait()
        result = with_retry(lambda: client.models.generate_content(
            model=MEDIA_MODEL,
            contents=[lesion_bank.vocabulary_prompt(), uploaded],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=lesion_bank.READING_SCHEMA,
            ),
        ))
        import json
        text = (getattr(result, "text", "") or "").strip()
        data = json.loads(re.sub(r"^```(?:json)?|```$", "", text).strip())
        return data if isinstance(data, dict) else None
    except Exception as e:
        print(f"  ! {path.name}: {e}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="dataset root holding Train/Val/Test")
    ap.add_argument("--split", default="Train", help="which split to draw references from")
    ap.add_argument("--per-class", type=int, default=12)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--rpm", type=int, default=PACED_RPM,
                    help=f"requests per minute; free tier allows {FREE_TIER_RPM}")
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be read, make no API calls")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    split_dir = root / args.split
    if not split_dir.is_dir():
        sys.exit(f"No such split: {split_dir}")

    random.seed(args.seed)

    if not args.dry_run:
        db.init()
        knowledge.init()
        if not lesion_bank.init():
            sys.exit("Lesion bank could not be created - is the database reachable?")

    # Reference images are drawn from one split only. Anything measured later
    # must come from a split this bank never saw, and the source ids recorded
    # here are what makes that checkable.
    chosen: list[tuple[Path, tuple]] = []
    unknown = []
    for class_dir in sorted(split_dir.iterdir()):
        if not class_dir.is_dir():
            continue
        label = LABELS.get(class_dir.name)
        if label is None:
            unknown.append(class_dir.name)
            continue
        files = eligible_files(class_dir)
        picked = random.sample(files, min(args.per_class, len(files)))
        chosen.extend((p, label) for p in picked)
        print(f"{class_dir.name:38} {len(files):>5} unaugmented -> {len(picked)} chosen")

    if unknown:
        print("\nSkipped, no label mapping:")
        for name in unknown:
            print(f"  {name}")

    print(f"\n{len(chosen)} images to read"
          f"{' (dry run, nothing sent)' if args.dry_run else ''}")
    if args.dry_run:
        return

    with db.connection() as conn:
        already = {r[0] for r in conn.execute(
            'SELECT source FROM lesion_examples').fetchall()}
    before = len(chosen)
    chosen = [(p, l) for (p, l) in chosen
              if f'plantvillage/{args.split}/{p.parent.name}/{p.name}' not in already]
    if before != len(chosen):
        print(f'{before - len(chosen)} already in the bank, {len(chosen)} left to read')

    client = get_client()
    limiter = RateLimiter(args.rpm)
    stored = failed = unusable = 0

    def work(item):
        path, (crop, disease, healthy) = item
        features = read_image(client, path, limiter)
        if not features:
            return "failed"
        if features.get("usable") is False:
            return "unusable"
        # The label is the truth. What the model thought the crop was is not
        # recorded as the crop - it is a reference row, and its provenance is
        # the folder it came from.
        ok = lesion_bank.add_example(
            crop=crop, disease=disease, features=features,
            source=f"plantvillage/{args.split}/{path.parent.name}/{path.name}",
            healthy=healthy,
        )
        return "stored" if ok else "failed"

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(work, item): item for item in chosen}
        for i, future in enumerate(as_completed(futures), 1):
            outcome = future.result()
            stored += outcome == "stored"
            failed += outcome == "failed"
            unusable += outcome == "unusable"
            if i % 25 == 0 or i == len(chosen):
                print(f"  {i}/{len(chosen)}  stored={stored} unusable={unusable} failed={failed}")

    print(f"\nStored {stored}, unusable {unusable}, failed {failed}")
    print("Bank now holds:", lesion_bank.size())


if __name__ == "__main__":
    main()
