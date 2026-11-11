"""
Gemini or Sarvam: which one hears a farmer better?

Runs every clip in eval/stt_clips/ through both, and scores each transcript
against what the farmer actually said. Gemini is called through the very
function production uses (process_media._understand, same prompt, same model),
so this measures the app as it is, not a hand-tuned rival.

THE SCORE THAT DECIDES. A transcript can get many small words wrong and still
lead to the right answer, or get one word wrong - the pest, the crop, the
district - and lead to the wrong one. So the main score is key terms kept: of
the words a clip lists as essential, how many came through. Word and character
error rates are shown too, but only compare like with like: Sarvam may write
Hinglish in Devanagari where the reference is in Latin letters, which inflates
them without anything being misheard. Key terms accept every spelling listed.

THE CLIPS ARE FARMERS' OWN VOICES. They stay on this computer: stt_clips/ and
stt_results/ are gitignored. Sending them to Sarvam sends them to a company
whose data terms should be read first; to Gemini, on the free tier, Google may
use what is sent to improve its products.

Setup
  1. Put audio files in eval/stt_clips/ (.webm .ogg .m4a .mp3 .wav .aac .flac),
     each under 30 seconds - Sarvam's synchronous limit.
  2. List them in eval/stt_clips/clips.csv (copy clips.example.csv):
       file       the audio file's name
       language   hi / bn / pa / en / hinglish ... (for the report only)
       reference  exactly what was said, typed by someone who listened
       key_terms  essential words, ";" between terms, "/" between spellings:
                  "गेहूं/gehu/gehun/wheat; sundi/सूंडी/bollworm; Kharagpur/खड़गपुर"
  3. SARVAM_API_KEY in AnnaData-Backend-main/.env (or the environment).
     GEMINI_API_KEY is already there for the app.

Run (from AnnaData-Backend-main, with the backend's virtualenv)
  python eval/compare_stt.py                       both, Sarvam model saarika:v2.5
  python eval/compare_stt.py --sarvam-model saaras:v3
  python eval/compare_stt.py --only sarvam         one side only
  python eval/compare_stt.py --dry-run             check the CSV and files, no calls

Each run writes a CSV of every transcript and score to eval/stt_results/.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import statistics
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

CLIPS = HERE / "stt_clips"
RESULTS = HERE / "stt_results"
SARVAM_URL = "https://api.sarvam.ai/speech-to-text"
AUDIO = {".webm", ".ogg", ".m4a", ".mp3", ".wav", ".aac", ".flac"}
SARVAM_TYPES = {".webm": "audio/webm", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".mp3": "audio/mpeg",
                ".wav": "audio/wav", ".aac": "audio/aac", ".flac": "audio/flac"}


# ---------------------------------------------------------------- scoring --

def normalise(text: str) -> str:
    """Lower case, one form of each character, no punctuation, single spaces."""
    text = unicodedata.normalize("NFC", text or "").lower()
    # Devanagari danda and every other punctuation mark; keep letters, marks, digits.
    text = "".join(ch if unicodedata.category(ch)[0] in "LMN" else " " for ch in text)
    return re.sub(r"\s+", " ", text).strip()


def _edits(a: list, b: list) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str) -> float | None:
    ref = normalise(reference).split()
    return None if not ref else _edits(ref, normalise(hypothesis).split()) / len(ref)


def cer(reference: str, hypothesis: str) -> float | None:
    ref = normalise(reference).replace(" ", "")
    return None if not ref else _edits(list(ref), list(normalise(hypothesis).replace(" ", ""))) / len(ref)


def parse_terms(raw: str) -> list[list[str]]:
    """'गेहूं/gehu; sundi/सूंडी' -> [['गेहूं', 'gehu'], ['sundi', 'सूंडी']]."""
    terms = []
    for term in (raw or "").split(";"):
        spellings = [normalise(s) for s in term.split("/") if normalise(s)]
        if spellings:
            terms.append(spellings)
    return terms


def terms_kept(terms: list[list[str]], hypothesis: str) -> tuple[int, list[str]]:
    """How many terms appear in any listed spelling, and the first spelling of each missed."""
    said = f" {normalise(hypothesis)} "
    missed = [spellings[0] for spellings in terms
              if not any(f" {s} " in said or (" " in s and s in said) for s in spellings)]
    return len(terms) - len(missed), missed


# ---------------------------------------------------------------- engines --

def gemini(path: Path) -> str:
    """The production path, unchanged."""
    import process_media
    return process_media._understand(audio_bytes=path.read_bytes(),
                                     audio_filename=path.name)["transcript"]


def sarvam(path: Path, key: str, model: str) -> str:
    import requests
    with path.open("rb") as f:
        response = requests.post(
            SARVAM_URL,
            headers={"api-subscription-key": key},
            data={"model": model, "language_code": "unknown"},
            files={"file": (path.name, f, SARVAM_TYPES[path.suffix.lower()])},
            timeout=60,
        )
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code}: {response.text[:200]}")
    body = response.json()
    return body.get("transcript", "")


# ---------------------------------------------------------------- running --

def load_clips() -> list[dict]:
    sheet = CLIPS / "clips.csv"
    if not sheet.exists():
        sys.exit(f"No {sheet}. Copy clips.example.csv to clips.csv and list your clips in it.")
    with sheet.open(encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("file") or "").strip()]
    # A sheet filled in ahead of the recordings is normal: rows whose file is
    # not there yet are skipped and counted, so a first handful can be tested.
    # A row that is wrong, not merely early, still stops the run.
    problems, ready, waiting = [], [], []
    for r in rows:
        path = CLIPS / r["file"].strip()
        if path.suffix.lower() not in AUDIO:
            problems.append(f"{r['file']}: not an audio type this test sends ({', '.join(sorted(AUDIO))})")
            continue
        if not (r.get("reference") or "").strip():
            problems.append(f"{r['file']}: no reference text - nothing to score against")
            continue
        if not path.exists():
            waiting.append(r["file"])
            continue
        r["path"] = path
        r["terms"] = parse_terms(r.get("key_terms", ""))
        ready.append(r)
    if problems:
        sys.exit("Fix clips.csv first:\n  " + "\n  ".join(problems))
    if not rows:
        sys.exit("clips.csv lists no clips.")
    if waiting:
        shown = ", ".join(waiting[:6]) + (f" and {len(waiting) - 6} more" if len(waiting) > 6 else "")
        print(f"Not recorded yet, skipped ({len(waiting)} of {len(rows)}): {shown}")
    if not ready:
        sys.exit(f"None of the {len(rows)} listed recordings is in {CLIPS} yet. "
                 "Save voice notes there under the names in clips.csv.")
    return ready


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", choices=["gemini", "sarvam"])
    ap.add_argument("--sarvam-model", default=os.environ.get("SARVAM_STT_MODEL", "saarika:v2.5"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        import config  # noqa: F401  loads AnnaData-Backend-main/.env
    except Exception:  # noqa: BLE001
        pass
    clips = load_clips()
    engines = ["gemini", "sarvam"] if not args.only else [args.only]
    key = os.environ.get("SARVAM_API_KEY", "")
    if "sarvam" in engines and not key and not args.dry_run:
        sys.exit("SARVAM_API_KEY is not set. Add it to AnnaData-Backend-main/.env, or run --only gemini.")
    terms_total = sum(len(c["terms"]) for c in clips)
    print(f"Testing {len(clips)} recording(s), {terms_total} key term(s); engines: {', '.join(engines)}"
          + (f" (Sarvam model {args.sarvam_model})" if "sarvam" in engines else ""))
    if args.dry_run:
        print("Dry run: the sheet is fine and these recordings are ready. No audio was sent.")
        return

    rows, summary = [], {e: {"wer": [], "cer": [], "kept": 0, "seconds": [], "errors": 0} for e in engines}
    for clip in clips:
        print(f"\n{clip['file']}  [{clip.get('language', '')}]")
        print(f"  said    {clip['reference']}")
        for engine in engines:
            started = time.perf_counter()
            try:
                text = gemini(clip["path"]) if engine == "gemini" else sarvam(clip["path"], key, args.sarvam_model)
                error = ""
            except Exception as e:  # noqa: BLE001
                text, error = "", f"{type(e).__name__}: {e}"
            seconds = time.perf_counter() - started
            kept, missed = terms_kept(clip["terms"], text)
            w, c = wer(clip["reference"], text), cer(clip["reference"], text)
            s = summary[engine]
            if error:
                s["errors"] += 1
            else:
                s["seconds"].append(seconds)
                s["wer"].append(w)
                s["cer"].append(c)
            s["kept"] += kept
            shown = error or text
            print(f"  {engine:<7} {shown}")
            print(f"          terms {kept}/{len(clip['terms'])}"
                  + (f" (missed: {', '.join(missed)})" if missed else "")
                  + (f"  WER {w:.0%}  CER {c:.0%}" if not error else "") + f"  {seconds:.1f}s")
            rows.append({"file": clip["file"], "language": clip.get("language", ""), "engine": engine,
                         "model": args.sarvam_model if engine == "sarvam" else "production MEDIA_MODEL",
                         "reference": clip["reference"], "transcript": text, "error": error,
                         "terms_kept": kept, "terms_total": len(clip["terms"]), "missed": "; ".join(missed),
                         "wer": "" if w is None or error else round(w, 3),
                         "cer": "" if c is None or error else round(c, 3), "seconds": round(seconds, 2)})

    print("\n" + "=" * 72)
    print(f"{'engine':<8} {'key terms kept':>15} {'WER':>6} {'CER':>6} {'median s':>9} {'errors':>7}")
    for engine, s in summary.items():
        kept = f"{s['kept']}/{terms_total}" + (f" {s['kept'] / terms_total:.0%}" if terms_total else "")
        mean = lambda xs: f"{statistics.mean(xs):.0%}" if xs else "-"  # noqa: E731
        med = f"{statistics.median(s['seconds']):.1f}" if s["seconds"] else "-"
        print(f"{engine:<8} {kept:>15} {mean(s['wer']):>6} {mean(s['cer']):>6} {med:>9} {s['errors']:>7}")
    print("Key terms decide it; WER/CER compare fairly only where both wrote the same script.")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"stt-{datetime.now():%Y%m%d-%H%M%S}.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Every transcript: {out}")


if __name__ == "__main__":
    main()
