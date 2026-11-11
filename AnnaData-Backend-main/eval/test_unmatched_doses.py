"""
No dose for a pest the register did not match, enforced in code.

When the pest asked about matches nothing - or the farmer named no pest at all,
only a symptom - the prompt is handed what is registered for the crop under a
warning that none of it may be recommended. On production the model ignored
that warning once: asked about blackening potato leaves, it quoted
Chlorothalonil's dose for blight. output_guards.strip_unmatched_doses (whole
answers) and SentenceGuard (streamed answers) now remove any sentence naming
such a product. Checked here against that production answer, without a model.

Run: python eval/test_unmatched_doses.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import output_guards as og

failures = []


def check(name: str, got, want):
    ok = got == want
    print(f"  {'pass' if ok else 'FAIL'}   {name}"
          + ("" if ok else f"\n           got  {got!r}\n           want {want!r}"))
    if not ok:
        failures.append(name)


def use(product, pest="Late blight, Early blight"):
    return {"product": product, "crop": "Potato", "pest": pest, "dose_formulation": "875-1250",
            "dilution": "600-800", "waiting_period": "14 days", "source": "CIB&RC"}


CROP_LEVEL = {"pest_matched": False, "uses": [
    use("Chlorothalonil 75% WP"), use("Azoxystrobin 23% SC"),
    use("Copper Oxychloride 50% WP"), use("Captan 50% WP"), use("Zineb 75% WP")]}
MATCHED = {"pest_matched": True, "uses": CROP_LEVEL["uses"]}

# The SMS answer production sent, word for word.
PRODUCTION = ("Agar patte kinare se kaale pad rahe hain, toh ye blight ho sakta hai. "
              "Aap Chlorothalonil 75% WP ki 875-1250 gram matra prati hectare, 600-800 "
              "litre pani mein gholkar chhidkav kar sakte hain. Ye late aur early blight "
              "ke liye registered upchar hai. Chhidkav ke baad 14 din tak fasal na todein. "
              "Kya ye dhabbe patte ke kinaron se shuru ho rahe hain ya beech mein?")


def main() -> int:
    print("Whole answers")
    text, removed = og.strip_unmatched_doses(PRODUCTION, CROP_LEVEL)
    check("the production answer loses its Chlorothalonil sentence", removed, True)
    check("no product survives", "chlorothalonil" in text.lower(), False)
    check("the question to the farmer survives",
          text.endswith("Kya ye dhabbe patte ke kinaron se shuru ho rahe hain ya beech mein?"), True)
    check("what only made sense beside the dose goes with it "
          "('registered upchar hai', 'chhidkav ke baad 14 din')", text,
          "Agar patte kinare se kaale pad rahe hain, toh ye blight ho sakta hai. "
          "Kya ye dhabbe patte ke kinaron se shuru ho rahe hain ya beech mein?")

    figures_only = ("Copper Oxychloride ka upyog karein. 875-1250 gram prati hectare "
                    "gholkar daalein. Khet saaf rakhein aur prabhavit patte hata dein.")
    check("a sentence carrying only the dose figure goes too",
          og.strip_unmatched_doses(figures_only, CROP_LEVEL)[0],
          "Khet saaf rakhein aur prabhavit patte hata dein.")

    later = ("Neem ka chhidkav bhi kar sakte hain. Captan 50% WP ka upyog karein.\n\n"
             "Khet mein pani na jamne dein.")
    check("spray advice BEFORE the dose sentence, and other paragraphs, are kept",
          og.strip_unmatched_doses(later, CROP_LEVEL)[0],
          "Neem ka chhidkav bhi kar sakte hain.\n\nKhet mein pani na jamne dein.")

    import knowledge
    prompt_text = knowledge.format_uses(CROP_LEVEL, None)
    check("the prompt no longer lists the crop's products when the pest is unmatched",
          any(p in prompt_text for p in ("Chlorothalonil", "Azoxystrobin", "Captan")), False)
    check("and still tells the model to name no product",
          "Do NOT state any product name or dose" in prompt_text, True)
    check("a matched pest still gets its products in the prompt",
          "Chlorothalonil" in knowledge.format_uses(MATCHED, "late blight"), True)

    check("a matched pest's dose is left alone",
          og.strip_unmatched_doses(PRODUCTION, MATCHED), (PRODUCTION, False))
    check("no dose lookup at all: left alone",
          og.strip_unmatched_doses(PRODUCTION, None), (PRODUCTION, False))
    plain = "Prabhavit patton ko hata dein. Khet mein pani na jamne dein."
    check("an answer naming no product is left alone",
          og.strip_unmatched_doses(plain, CROP_LEVEL), (plain, False))

    hindi = ("पत्तियों को हटा दें। क्लोरोथालोनिल का छिड़काव करें। "
             "अपने कृषि विज्ञान केंद्र से संपर्क करें।")
    text, removed = og.strip_unmatched_doses(hindi, CROP_LEVEL)
    check("a product written in Devanagari is caught too", removed, True)
    check("and only that sentence goes", text,
          "पत्तियों को हटा दें। अपने कृषि विज्ञान केंद्र से संपर्क करें।")

    bullets = ("Ye kadam uthayein:\n"
               "*   Prabhavit patton ko hata dein.\n"
               "*   Azoxystrobin 23% SC ka chhidkav karein.\n"
               "*   Khet mein pani na jamne dein.")
    text, _ = og.strip_unmatched_doses(bullets, CROP_LEVEL)
    check("a bulleted answer keeps its layout, minus the product line", text,
          "Ye kadam uthayein:\n*   Prabhavit patton ko hata dein.\n"
          "*   Khet mein pani na jamne dein.")

    only = "Captan 50% WP 2 kg prati hectare chhidkein."
    check("an answer that was nothing but the dose becomes the referral",
          og.strip_unmatched_doses(only, CROP_LEVEL), (og.DOSE_FALLBACK, True))

    check("five-letter names like Zineb are matched",
          "Zineb" in og.unmatched_products(CROP_LEVEL), True)
    check("but a four-letter word would be skipped",
          og.unmatched_products({"pest_matched": False, "uses": [use("Zinc 12%")]}), [])

    print("\nStreamed answers")
    guard = og.SentenceGuard({}, CROP_LEVEL)
    sent = [s for s in (guard.check(p) for p in (
        "Agar patte kinare se kaale pad rahe hain, toh ye blight ho sakta hai. ",
        "Aap Chlorothalonil 75% WP ki 875-1250 gram matra prati hectare chhidkein. ",
        "Kya ye dhabbe patte ke kinaron se shuru ho rahe hain? ")) if s is not None]
    check("the dose sentence is never sent", len(sent), 2)

    guard = og.SentenceGuard({}, CROP_LEVEL)
    sent = [s for s in (guard.check(p) for p in (
        "Aap Chlorothalonil 75% WP chhidkein. ",
        "Ye blight ke liye registered upchar hai. ",
        "Chhidkav ke baad 14 din tak fasal na todein.\n\n",
        "Khet mein spray karne se pehle KVK se poochein.")) if s is not None]
    check("streamed: the follow-on sentences go, until the paragraph ends",
          sent, ["Khet mein spray karne se pehle KVK se poochein."])
    check("enough survived that no fallback is added", guard.closing(), None)

    guard = og.SentenceGuard({}, CROP_LEVEL)
    guard.check("Captan 50% WP 2 kg prati hectare chhidkein.")
    check("when nothing survives, the referral closes the answer",
          guard.closing(), og.DOSE_FALLBACK)

    guard = og.SentenceGuard({}, MATCHED)
    check("a matched pest's dose streams through",
          guard.check("Aap Chlorothalonil 75% WP chhidkein. "),
          "Aap Chlorothalonil 75% WP chhidkein. ")

    print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
