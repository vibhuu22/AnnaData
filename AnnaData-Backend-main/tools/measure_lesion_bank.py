"""
Measure disease identification against labelled photographs the bank never saw.

    python tools/measure_lesion_bank.py --root "../Plant Village Dataset" --per-class 4

What is being measured, and why these four outcomes
---------------------------------------------------
Accuracy alone is the wrong headline for this system. A farmer acting on a
confident wrong disease name buys the wrong chemical and loses the crop anyway;
a farmer told "the picture is not enough, here is what to do meanwhile and take
it to your KVK" loses nothing. Those two failures are not equivalent and must
not be summed into one number.

So each image lands in exactly one of:

    correct    - named the labelled disease
    abstained  - said it could not tell (the safe failure)
    disputed   - the model and the bank disagreed, so both were offered
    wrong      - named a different disease, confidently (the harmful failure)

**wrong** is the number that governs whether this ships. Everything else is
cost; that one is risk.

Honesty about what this can and cannot show
-------------------------------------------
- Test images are drawn from a split the bank was not built from, and every
  source id is checked against the bank's own rows, so an augmented copy of a
  reference image cannot be scored as a test case.
- These are laboratory photographs: one detached leaf, uniform background. Any
  figure here is an **upper bound** on field performance, and must be reported
  as one.
- The nine crops here are not the crops most of our farmers grow. This measures
  general competence, not competence on rice.
"""
import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
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
from process_media import IMAGE_PROMPT  # noqa: E402
from tools.build_lesion_bank import (  # noqa: E402
    LABELS, PACED_RPM, RateLimiter, eligible_files, source_id, with_retry,
)

# One call reads the photograph twice over: the free-text diagnosis the shipped
# system already makes, and the controlled reading the bank is indexed on. Two
# calls would double both cost and wall time for no additional signal.
COMBINED_SCHEMA = {
    "type": "object",
    "properties": {
        **{f: {"type": "string"} for f in lesion_bank.VOCABULARY},
        "crop": {"type": "string"},
        "usable": {"type": "boolean"},
        "pest": {"type": "string"},
        "confidence": {"type": "string"},
    },
}


def read(client, path: Path, limiter=None) -> dict | None:
    prompt = (
        lesion_bank.vocabulary_prompt()
        + "\n\nSEPARATELY, and only after the fields above, give your own reading:\n"
        + IMAGE_PROMPT
        + "\nAdd two more keys to the same JSON object: 'pest' (the English "
          "common name of the disease, or 'unknown') and 'confidence' "
          "('high', 'medium' or 'low')."
    )
    try:
        uploaded = client.files.upload(file=str(path))
        if limiter:
            limiter.wait()
        result = with_retry(lambda: client.models.generate_content(
            model=MEDIA_MODEL,
            contents=[prompt, uploaded],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=COMBINED_SCHEMA,
            ),
        ))
        text = (getattr(result, "text", "") or "").strip()
        data = json.loads(re.sub(r"^```(?:json)?|```$", "", text).strip())
        return data if isinstance(data, dict) else None
    except Exception as e:
        print(f"  ! {path.name}: {e}")
        return None


def same_disease(a: str, b: str) -> bool:
    """Whether two disease names refer to the same thing.

    Deliberately generous in one direction only: 'blast' and 'leaf blast' are
    the same disease written two ways, and scoring them as a miss would measure
    vocabulary rather than sight. 'early blight' and 'late blight' share a word
    and are different diseases, so a bare substring test is not enough.
    """
    a, b = (a or "").strip().lower(), (b or "").strip().lower()
    if not a or not b:
        return False
    if a == b:
        return True
    qualifiers = {"early", "late", "northern", "southern", "common", "cedar"}
    if (set(a.split()) & qualifiers) != (set(b.split()) & qualifiers):
        return False
    return a in b or b in a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--split", default="Test")
    ap.add_argument("--per-class", type=int, default=4)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--rpm", type=int, default=PACED_RPM)
    ap.add_argument("--seed", type=int, default=91)
    ap.add_argument("--floor", type=float, default=lesion_bank.DEFAULT_FLOOR)
    ap.add_argument("--out", default="eval/lesion_results.json")
    args = ap.parse_args()

    db.init()
    knowledge.init()
    lesion_bank.init()

    held = lesion_bank.size()
    if not held:
        sys.exit("The lesion bank is empty - run tools/build_lesion_bank.py first.")
    print(f"Bank holds {sum(held.values())} examples across {len(held)} crops\n")

    # Every source id already in the bank, so a reference image can never be
    # scored as a test case.
    with db.connection() as conn:
        used = {source_id(Path(r[0]).name)
                for r in conn.execute("SELECT source FROM lesion_examples").fetchall()}

    random.seed(args.seed)
    cases = []
    for class_dir in sorted((Path(args.root).expanduser().resolve() / args.split).iterdir()):
        if not class_dir.is_dir():
            continue
        label = LABELS.get(class_dir.name)
        if label is None:
            continue
        files = [p for p in eligible_files(class_dir) if source_id(p.name) not in used]
        cases.extend((p, label) for p in random.sample(files, min(args.per_class, len(files))))

    print(f"{len(cases)} held-out images to score\n")

    client = get_client()
    limiter = RateLimiter(args.rpm)
    outcomes = Counter()
    per_class = defaultdict(Counter)
    records = []

    def work(item):
        path, (crop, disease, healthy) = item
        reading = read(client, path, limiter)
        if not reading:
            return None
        truth = "healthy" if healthy else disease
        proposed = (reading.get("pest") or "unknown").strip().lower()
        if healthy and proposed in ("none", "healthy", ""):
            proposed = "healthy"

        features = {f: reading.get(f, "") for f in lesion_bank.VOCABULARY}
        verdict = lesion_bank.consult(features, crop, proposed, floor=args.floor)

        if not reading.get("usable", True):
            outcome = "abstained"
        elif verdict["verdict"] in ("uncovered", "unavailable"):
            outcome = "abstained"
        elif verdict["verdict"] == "disputed":
            outcome = "disputed"
        elif same_disease(verdict["disease"] or "", truth):
            outcome = "correct"
        else:
            outcome = "wrong"

        return {
            "file": str(path.relative_to(Path(args.root).expanduser().resolve())),
            "crop": crop, "truth": truth,
            "model_said": proposed,
            "bank_said": verdict["disease"],
            "alternatives": verdict["alternatives"],
            "similarity": round(verdict["similarity"], 4),
            "verdict": verdict["verdict"],
            "outcome": outcome,
        }

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, c) for c in cases]
        for i, future in enumerate(as_completed(futures), 1):
            rec = future.result()
            if rec is None:
                outcomes["error"] += 1
                continue
            records.append(rec)
            outcomes[rec["outcome"]] += 1
            per_class[f"{rec['crop']} - {rec['truth']}"][rec["outcome"]] += 1
            if i % 20 == 0 or i == len(cases):
                print(f"  {i}/{len(cases)}  {dict(outcomes)}")

    total = sum(outcomes[k] for k in ("correct", "abstained", "disputed", "wrong"))
    print("\n" + "=" * 62)
    print(f"{'outcome':<12}{'n':>6}{'share':>10}")
    print("-" * 62)
    for key in ("correct", "disputed", "abstained", "wrong"):
        n = outcomes[key]
        print(f"{key:<12}{n:>6}{(n / total * 100 if total else 0):>9.1f}%")
    print("-" * 62)
    print(f"{'scored':<12}{total:>6}")
    if outcomes["error"]:
        print(f"{'errors':<12}{outcomes['error']:>6}")

    print("\nHarmful failures (confidently wrong), by class:")
    any_wrong = False
    for name, counts in sorted(per_class.items(), key=lambda kv: -kv[1]["wrong"]):
        if counts["wrong"]:
            any_wrong = True
            print(f"  {name:<34} {counts['wrong']}/{sum(counts.values())}")
    if not any_wrong:
        print("  none")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "floor": args.floor,
        "bank_size": sum(held.values()),
        "summary": dict(outcomes),
        "records": records,
    }, indent=2), encoding="utf-8")
    print(f"\nPer-image results written to {out}")


if __name__ == "__main__":
    main()
