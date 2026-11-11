"""
The speech comparison's scoring, checked offline: no audio, no network.

compare_stt.py decides between Gemini and Sarvam on these numbers, so they
must mean what they say. Run: python eval/test_stt_scoring.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from compare_stt import cer, normalise, parse_terms, terms_kept, wer

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


print("Normalising")
check("case, punctuation and the danda go", normalise("Gehu ki BUWAI kab karein?।"), "gehu ki buwai kab karein")
check("Devanagari vowel signs survive", normalise("गेहूं की बुवाई"), "गेहूं की बुवाई")
check("chandrabindu and anusvara spell one sound", normalise("क्या करूँ, गेहूँ"), normalise("क्या करूं, गेहूं"))

print("\nError rates")
check("identical is 0", wer("gehu ki buwai kab", "Gehu ki buwai kab?"), 0.0)
check("one word of four wrong", wer("gehu ki buwai kab", "gehu ki bhai kab"), 0.25)
check("a missing word counts", wer("gehu ki buwai kab", "gehu buwai kab"), 0.25)
check("nothing heard is all wrong", wer("gehu ki buwai kab", ""), 1.0)
check("characters, one of four", cer("abcd", "abxd"), 0.25)
check("no reference: no score", wer("", "anything"), None)

print("\nKey terms")
terms = parse_terms("गेहूं/gehu/wheat; sundi/सूंडी; Kharagpur")
check("terms and spellings are split", terms, [["गेहूं", "gehu", "wheat"], ["sundi", "सूंडी"], ["kharagpur"]])
check("any spelling, either script, counts", terms_kept(terms, "Gehu me सूंडी lagi, Kharagpur"), (3, []))
check("a missing term is named", terms_kept(terms, "gehu me keede lage"), (1, ["sundi", "kharagpur"]))
check("part of a longer word is not a match", terms_kept(parse_terms("dhan"), "dhanyavaad"), (0, ["dhan"]))
check("a two-word term is found", terms_kept(parse_terms("brown spot"), "isme brown spot hai"), (1, []))

print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)
