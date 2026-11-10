"""
Registered doses: per hectare, said so, and recognised in any script.

Live, a Hindi voice answer quoted acephate's registered 666-1000 g for rice
stem borer as "प्रति एकड़" - per acre, two and a half times the dose - because
the register's rows reached the model as "dose 666-1000" with no unit or area.
The same answer named the product as एसेफेट, which the dose check did not
recognise, so the register's list was appended again in English and read aloud.

No model calls. Run: python eval/test_dose_units.py
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GEMINI_API_KEY", "x")

import knowledge  # noqa: E402
import output_guards  # noqa: E402

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


USES = {"pest_matched": True, "uses": [{
    "product": "Acephate 75% SP", "crop": "Rice", "pest": "Stem borer",
    "dose_formulation": "666-1000", "dilution": "500", "waiting_period": "15",
    "source": "CIB&RC"}]}

print("What the model is given")
told = knowledge.format_uses(USES, "stem borer")
check("the dose is per hectare", "dose 666-1000 per hectare" in told, True)
check("the water too", "litres of water per hectare" in told, True)
check("and it is told never to call it per acre", "never write a per-hectare number as per acre" in told, True)
check("the appended lines say per hectare", "per hectare" in knowledge.dose_lines(USES)[0], True)

print("\nA product named in any script counts as named")
hindi = "धान में तना छेदक के लिए एसेफेट 75 प्रतिशत एसपी की 666 से 1000 ग्राम मात्रा प्रति हेक्टेयर डालें।"
check("Hindi: nothing appended", output_guards.ensure_registered_doses(hindi, USES, "stem borer")[1], False)
bengali = "ধানে কাণ্ড ছিদ্রকারী পোকার জন্য অ্যাসিফেট ৭৫% এসপি দিন।"
check("Bengali: nothing appended", output_guards.ensure_registered_doses(bengali, USES, "stem borer")[1], False)
check("Latin: nothing appended",
      output_guards.ensure_registered_doses("Acephate 75% SP spray karein.", USES, "stem borer")[1], False)
check("an answer that names no registered product still gets the list",
      output_guards.ensure_registered_doses("Khet saaf rakhein.", USES, "stem borer")[1], True)
check("another product is not this one", output_guards.mentions("Use Mancozeb only", "Acephate"), False)

print()
if failures:
    print(f"{len(failures)} failed: {failures}")
    sys.exit(1)
print("all passed")
