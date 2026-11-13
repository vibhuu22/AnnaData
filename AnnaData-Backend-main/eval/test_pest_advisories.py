"""
The DPPQ&S pest advisories reach a farmer with no chemical and no dose in them.

The advisories are loaded for symptoms, the weather a pest likes, when to act
and what to do without a chemical. Doses come only from the CIB&RC register.
This checks, without a model or a database, that the loader removes what it
must (a formulation, a rate, a registered or banned chemical - phorate among
them) and keeps what it should (traps, thresholds, field practice, weather),
and that the agent only asks for advisories on pest questions.

Run: python eval/test_pest_advisories.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import knowledge
import planner
from tools import ingest_advisories as ia

failures = []


def check(name: str, got, want):
    ok = got == want
    print(f"  {'pass' if ok else 'FAIL'}   {name}"
          + ("" if ok else f"\n           got  {got!r}\n           want {want!r}"))
    if not ok:
        failures.append(name)


NAMES = {"imidacloprid", "flonicamid", "thiodicarb", "emamectin", "mancozeb"}


def removed(sentence):
    return ia.chemical_reason(sentence, NAMES) is not None


print("Chemicals and doses are removed")
check("formulation", removed("Spray Azadirachtin 0.03% WSP against whitefly."), True)
check("OCR'd formulation", removed("Pseudomonas fluorescens 1.5%o WP may be used."), True)
check("rate per litre", removed("Use 2 ml per litre of water."), True)
check("rate after @", removed("Apply @ 5 ml/litre at weekly intervals."), True)
check("OCR'd rate", removed("Spray 5gllit of water @ Ikglha after transplanting."), True)
check("register name", removed("Swab the stem with Flonicamid diluted 1:20."), True)
check("register name split by OCR", removed("Use Thiod icarb in the poison bait."), True)
check("phorate, withdrawn by corrigendum", removed("Apply Phorate granules in the furrow."), True)
check("chemical by its shape", removed("Spray lambda-cyhalothrin on the crop."), True)
check("botanical strength", removed("In severe cases spray only neem oil 0.5%."), True)

print("Practices, thresholds and weather are kept")
check("trap density", removed("Install pheromone traps @ 5/acre for monitoring."), False)
check("biological release", removed("Release Trichogramma cards @ 1 lakh adults/ha."), False)
check("threshold", removed("Act if 10% of whorls are freshly damaged."), False)
check("weather", removed("Blast is favoured by humidity above 95% and 22-28 C."), False)
check("field sanitation", removed("Remove and destroy rosette flowers whenever seen."), False)
check("pointer to the register", removed(
    "Chemical control: use CIB&RC-approved insecticides only on crossing ETL."), False)

print("Letter boilerplate is dropped")
kept, _ = ia.strip_chemicals([
    "It is requested to disseminate this advisory amongst field functionaries.",
    "Install yellow sticky traps from the seedling stage to monitor whitefly.",
], NAMES)
check("admin request dropped, practice kept", kept,
      ["Install yellow sticky traps from the seedling stage to monitor whitefly."])
check("legacy-font Hindi is not readable", ia.readable("Tfr qd fugrfi if,.qlur dTltqi"), False)
check("English is readable", ia.readable("Undertake deep summer ploughing and field sanitation"), True)

print("Crop tags match how the farmer's crop is written")
check("paddy is rice", ia.crop_for("Advisory on Gall midge infesting Paddy crop", "gall_midge"), "rice")
check("bollworm file without a subject", ia.crop_for("", "advisory_pbw_white_fly"), "cotton")
check("several crops is none", ia.crop_for(
    "Yellow Mosaic Virus on Green gram and Black gram", "ymav_1"), None)
check("tag equals canonical_crop", ia.crop_for("Bacterial leaf blight of rice", "x"),
      knowledge.canonical_crop("dhaan"))

print("Older copies of the same text are skipped")
a = ia.shingles("Install pheromone traps at five per acre to monitor moths in the field "
                "and destroy rosette flowers whenever they are seen")
b = ia.shingles("Install pheromone traps at five per acre to monitor moths in the field "
                "and destroy rosette flowers whenever they are seen on plants")
check("near-identical chunk is a repeat", ia.repeats(b, [a]), True)
check("different chunk is not", ia.repeats(ia.shingles(
    "Rice blast is favoured by cool nights and long leaf wetness"), [a]), False)

print("The prompt section")
close = [{"content": "Remove infected stubble after harvest.", "source": "DPPQ&S advisory 2022",
          "similarity": 0.81}]
far = [{"content": "Coconut whitefly on oil palm.", "source": "DPPQ&S advisory 2019",
        "similarity": 0.52}]
text = knowledge.format_advisories(close, min_similarity=0.7)
check("close passage is shown", "Remove infected stubble" in text, True)
check("says doses come only from the register", "ONLY from" in text and
      "APPROVED PESTICIDE USES" in text, True)
check("nothing close enough leaves the section out",
      knowledge.format_advisories(far, min_similarity=0.7), "")

print("Only pest questions ask for advisories")
tools = planner.plan_tools("disease_pest", has_coords=False, state=None, kb_available=False,
                           crop="rice", advisories_available=True)
check("pest question with advisories loaded", "advisory" in tools, True)
check("not when none are loaded", "advisory" in planner.plan_tools(
    "disease_pest", has_coords=False, state=None, kb_available=False, crop="rice"), False)
check("not for a scheme question", "advisory" in planner.plan_tools(
    "scheme_subsidy", has_coords=False, state=None, kb_available=True,
    advisories_available=True), False)

print(f"\n{'All passed' if not failures else f'{len(failures)} FAILED'}")
sys.exit(1 if failures else 0)
