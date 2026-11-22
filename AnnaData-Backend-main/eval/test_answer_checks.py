"""
The checks every answer passes before it reaches a farmer, on cases from the
conversation export of 22 November 2026. No model, no network, no database:
the register and support-price table are stubbed.

Run: python eval/test_answer_checks.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GEMINI_API_KEY", "x")

import knowledge  # noqa: E402
import msp  # noqa: E402
import output_guards as g  # noqa: E402

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


MSP = {"wheat": "Minimum Support Price for Wheat in 2026-27: Rs 2,585 per quintal.",
       "rice": "Minimum Support Price for Paddy in 2026-27: Rs 2,369 per quintal."}
msp.for_crop = lambda crop: MSP.get(knowledge.canonical_crop(crop) or "", "")
knowledge.registered_products = lambda: [
    "Acephate 75% SP", "Chlorantraniliprole 18.5% SC", "Chlorothalonil 75% WP",
    "Emamectin benzoate 5% SG", "Sulphur 80% WP"]

print("Market prices nobody reported")
invented = ("क्षमा करें, खड़कपुर मंडी में आज आलू का भाव 2200 रुपये प्रति क्विंटल दर्ज किया गया है। "
            "यह दाम सामान्य किस्म के आलू के लिए है। अगर आप कुछ और पूछना चाहते हैं तो बताएं।")
out, hit = g.scrub(invented, {}, query="लेकिन आलू के भाव क्या है?")
check("'2200 रुपये' with no price data is removed", ("2200" in out, hit), (False, True))

reported = ("पटना की मंडियों से आज आलू की कोई आवक नहीं है। रक्सौल और मधुबनी में आलू का भाव 900 से "
            "1300 रुपये प्रति क्विंटल के आसपास है। क्या आप कुछ और जानना चाहते हैं?")
mandi = "Potato, Bihar, 11/11/2026: Raxaul modal Rs 900, Madhubani modal Rs 1,300 per quintal."
out, hit = g.scrub(reported, {"mandi": mandi})
check("prices that are in the mandi data stay", (out, hit), (reported, False))

dated = "Ghatal mandi mein 4 November 2026 ko aalu ka modal bhav 810 rupaye prati quintal tha."
out, hit = g.scrub(dated, {"mandi": "Ghatal APMC 04/11/2026 Potato modal 810"})
check("a date and a year are not mistaken for prices", hit, False)

frp = ("मुरादाबाद की मंडी में आज गन्ने का भाव उपलब्ध नहीं है। उत्तर प्रदेश में गन्ने के लिए "
       "लाभकारी मूल्य यानी एफआरपी 340 से 350 रुपये प्रति क्विंटल के बीच है। आप चीनी मिल से पूछें।")
out, hit = g.scrub(frp, {"mandi": ""})
check("an invented FRP, in Hindi, is removed", ("340" in out, hit), (False, True))

msp_ok = "Gehu ka MSP Rs 2,585 prati quintal hai, jo sarkari kharid kendra par milta hai."
check("the wheat MSP that was looked up stays", g.scrub(msp_ok, {"msp": MSP["wheat"]})[1], False)

print("\n'No MSP' for a crop that has one")
denial = ("आज आपके इलाके की मंडी में आलू और गेहूं के भाव की जानकारी उपलब्ध नहीं है। "
          "मेरी जानकारी के अनुसार इन फसलों के लिए कोई सरकारी न्यूनतम समर्थन मूल्य भी घोषित नहीं है। "
          "क्या आप बुवाई के बारे में जानना चाहते हैं?")
out, hit = g.scrub(denial, {}, query="आज मेरे इलाके में आलू या गेहूं की बिक्री हुई है?")
check("'these crops have no MSP' about wheat is removed", ("समर्थन मूल्य" in out, hit), (False, True))
true_denial = "Aalu ke liye sarkar ne koi MSP tay nahi kiya hai, isliye mandi ka bhav hi dekhein."
check("'potato has no MSP' stays - it is true",
      g.scrub(true_denial, {}, query="aalu ka msp kitna hai")[1], False)

print("\nDoses")
unmatched = {"uses": [], "pest_matched": False}
chickpea = ("Chane mein pod borer ke liye Chlorantraniliprole 47.85% SC ki 41.66 ml matra prati 500 "
            "liter pani mein gholkar chhidkav karein. Kya sundi phaliyon ko kha rahi hai?")
out, hit = g.scrub(chickpea, {}, doses=unmatched)
check("a register product's dose, pest not matched, is removed", ("41.66" in out, hit), (False, True))
check("too little left, so the farmer is told to ask the KVK instead", out, g.DOSE_FALLBACK)

matched = {"pest_matched": True, "uses": [{"product": "Acephate 75% SP", "dose_formulation": "666-1000",
                                            "dilution": "300-500"}]}
acre = ("धान में तना छेदक के नियंत्रण के लिए आप एसेफेट 75 प्रतिशत एसपी की 666 से 1000 ग्राम मात्रा को "
        "300 से 500 लीटर पानी में मिलाकर प्रति एकड़ छिड़काव कर सकते हैं।")
out, _ = g.scrub(acre, {}, doses=matched)
check("per acre becomes per hectare for a registered dose", ("प्रति हेक्टेयर" in out, "एकड़" in out), (True, False))
check("the registered dose itself stays", "666 से 1000" in out, True)

latin = "Acephate 75% SP 780 gram per acre, 500 litre paani mein spray karein."
out, _ = g.scrub(latin, {}, doses={"pest_matched": True, "uses": [{"product": "Acephate 75% SP",
                                                                   "dose_formulation": "780"}]})
check("and in Latin script", "per hectare" in out, True)

fertiliser = ("Buwai ke samay prati acre 50 kg DAP aur 25 kg urea dalein. "
              "Sulphur ki kami ke liye 10 kg Bentonite Sulphur dalein.")
check("fertiliser amounts are not doses", g.scrub(fertiliser, {}, doses=unmatched)[1], False)
check("no dose rule when the register was not consulted", g.scrub(chickpea, {}, doses=None)[1], False)

print("\nWhile streaming (voice speaks each sentence as it comes)")
guard = g.SentenceGuard({}, None, query="aalu ka bhav")
check("the invented price is never spoken", guard.check(invented.split("।")[0] + "।"), None)
guard = g.SentenceGuard({}, unmatched)
check("the unregistered dose is never spoken", guard.check(chickpea.split("? ")[0]), None)
guard = g.SentenceGuard({}, matched)
check("per acre is corrected before it is spoken", "प्रति हेक्टेयर" in (guard.check(acre) or ""), True)
guard = g.SentenceGuard({}, None, query="आलू और गेहूं का भाव")
check("the false 'no MSP' is never spoken",
      guard.check("इन फसलों के लिए कोई सरकारी न्यूनतम समर्थन मूल्य भी घोषित नहीं है।"), None)

print()
if failures:
    print(f"{len(failures)} failed: {failures}")
    sys.exit(1)
print("all passed")
