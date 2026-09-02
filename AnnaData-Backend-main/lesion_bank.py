"""
Disease identification by retrieval, against a bank of labelled symptoms.

Why this shape, and not a classifier
------------------------------------
The obvious move is a 29-class CNN over PlantVillage. It is the wrong tool here
for one decisive reason: **a softmax cannot abstain**. It must return one of its
classes for every image it is shown, with a confidence that looks the same
whether the input was a tomato leaf it knows or a rice leaf it has never seen.
This system's whole claim is that it refuses rather than guesses - a dose given
for the wrong disease is the specific harm the register grounding exists to
prevent - so a component that is structurally incapable of saying "I do not
know" cannot be allowed to name the pest.

Nearest-neighbour lookup abstains for free. If nothing in the bank resembles the
photograph, that *is* the answer. The same discipline already governs text
retrieval here, down to the tuned floor.

Three further properties earned it the place:

- **Open set.** Rice, wheat and cotton are absent from PlantVillage and are
  exactly what our farmers grow. A bank grows by inserting rows; twenty real
  field photographs of rice blast make it work for rice blast, with no
  retraining and no redeployment.
- **Explainable.** The five nearest labelled examples can be shown to an
  agronomist, which is a real answer to "how do you know?". A softmax
  probability is not.
- **Reviewable.** The vocabulary below is a symptom ontology of the kind a plant
  pathologist actually uses. Someone qualified can correct it, which is not true
  of a weight matrix.

What is indexed is the *observation*, not the pixels
----------------------------------------------------
PlantVillage images are detached leaves on a uniform grey studio background.
Farmers photograph plants in soil, in sunlight. Pixel-space models trained on
the former collapse on the latter - the single best-documented failure in
agricultural computer vision.

Observations survive that gap. A lab leaf and a field leaf both showing
concentric brown lesions with a yellow halo on lower foliage are read the same
way, however different the two images are. So the photograph is read once into
the controlled vocabulary below, and the *reading* is what gets matched.

Embeddings were tried first, and measured out
---------------------------------------------
The reading was originally rendered as a sentence, embedded with the same
768-dimension model the text store uses, and matched by cosine distance. On 348
reference readings that turned out to carry no signal at all: the nearest
neighbour of a reading had median cosine 1.000 when it shared the disease and
median 1.000 when it did not, and no floor between 0.60 and 0.85 separated the
two populations.

The cause was the sentence. Every reading shares the same scaffolding - "On
tomato; leaf condition: ...; lesion shape: ..." - so the template dominated the
vector and the few varying terms barely moved it. Embedding a fixed template
measures the template.

Counting agreeing fields has none of that problem, needs no API call, is
deterministic, and reports something a distance cannot: *which* observations
agreed, which is what an agronomist would want to see.

What this can and cannot do
---------------------------
It is an **ambiguity detector**, not an identifier, and the distinction is the
whole point. Measured on the reference bank itself, 25% of readings share an
exact description with a different disease *of the same crop* - three tomato
diseases, bacterial spot and early blight and late blight, produce one identical
reading. That is not a defect in the vocabulary so much as a fact about
photographs: a quarter of the time, lab-quality pictures of a single leaf do not
contain enough to tell these diseases apart.

So the bank is trusted to say "these symptoms are consistent with more than one
disease" and never trusted to be the sole reason for naming one. It can lower
confidence; it cannot raise it beyond what the reading already supported.
"""
import json

import db
import knowledge

# The vocabulary. Closed on purpose: free-text descriptions of the same lesion
# vary enough between calls to move the embedding more than the difference
# between two diseases does, which is precisely the noise that would make
# retrieval meaningless. Terms are the ones used in Indian extension practice.
VOCABULARY = {
    "lesion_shape": [
        "circular", "angular", "irregular", "elongated", "spindle-shaped",
        "streaked", "V-shaped from the margin", "pinpoint flecks", "none",
    ],
    "lesion_colour": [
        "brown", "dark brown", "tan", "grey-white centre", "black",
        "yellow", "orange-red", "purple", "reddish-brown", "water-soaked green",
    ],
    "lesion_margin": [
        "sharp dark border", "diffuse edge", "concentric rings inside the lesion",
        "yellow halo around the lesion", "water-soaked edge", "no distinct margin",
    ],
    "distribution": [
        "scattered across the blade", "concentrated along the veins",
        "starting at the leaf margin", "starting at the leaf tip",
        "on the lower leaves first", "on the upper leaves first",
        "covering most of the leaf", "along the midrib",
    ],
    "surface": [
        "powdery white coating", "raised rust-coloured pustules",
        "downy growth on the underside", "sunken dry tissue",
        "no surface growth", "sticky or sooty film",
    ],
    "leaf_condition": [
        "chlorosis (yellowing)", "necrosis (dead tissue)", "curling or cupping",
        "wilting", "stunted or distorted growth", "mosaic or mottled pattern",
        "healthy",
    ],
}

SCHEMA = f"""
-- Labelled symptom descriptions, embedded for nearest-neighbour lookup.
-- One row per reference photograph.
CREATE TABLE IF NOT EXISTS lesion_examples (
    id          BIGSERIAL PRIMARY KEY,
    crop        TEXT NOT NULL,      -- English common name, lowercase
    disease     TEXT NOT NULL,      -- as an extension officer would write it
    healthy     BOOLEAN NOT NULL DEFAULT false,
    description TEXT NOT NULL,      -- the controlled-vocabulary sentence
    features    JSONB,              -- the same reading, field by field
    source      TEXT NOT NULL,      -- which corpus, and which file
    embedding   vector({knowledge.EMBED_DIM}),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source)
);

CREATE INDEX IF NOT EXISTS lesion_embedding
    ON lesion_examples USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS lesion_crop
    ON lesion_examples (lower(crop));
"""

# The share of symptom fields a reference must agree on before it may vote.
# Four of six: three is common enough between genuinely different diseases to be
# noise, and five demands agreement on fields a photograph often cannot show.
DEFAULT_FLOOR = 4 / 6

# How many neighbours vote. Odd, and small enough that one stray row cannot
# carry a decision on its own.
NEIGHBOURS = 5


def init() -> bool:
    """Create the lesion table. Safe to call repeatedly."""
    if not db.is_available():
        return False
    try:
        with db.connection() as conn:
            conn.execute(SCHEMA)
        return True
    except Exception as e:
        print(f"Lesion bank unavailable: {e}")
        return False


def vocabulary_prompt() -> str:
    """The controlled vocabulary, as instructions for reading one photograph."""
    lines = [
        "Describe ONLY what is visible in this photograph of a plant, using the "
        "controlled vocabulary below. Choose the closest term for each field. "
        "Do not diagnose, do not name a disease, and do not guess at anything "
        "the image does not show.",
        "",
    ]
    for field, terms in VOCABULARY.items():
        lines.append(f"{field}: one of {', '.join(repr(t) for t in terms)}")
    lines += [
        "",
        "Also report:",
        "crop: the crop, English common name, lowercase, or 'unknown'.",
        "usable: true if this photograph actually shows plant tissue clearly "
        "enough to read symptoms from; false if it is blurred, too distant, too "
        "dark, or shows no plant.",
        "",
        "Return one JSON object with exactly these keys: lesion_shape, "
        "lesion_colour, lesion_margin, distribution, surface, leaf_condition, "
        "crop, usable.",
    ]
    return "\n".join(lines)


READING_SCHEMA = {
    "type": "object",
    "properties": {
        **{field: {"type": "string"} for field in VOCABULARY},
        "crop": {"type": "string"},
        "usable": {"type": "boolean"},
    },
}


def sentence(features: dict, crop: str | None = None) -> str:
    """The controlled reading as one sentence, which is what gets embedded.

    Written in a fixed order with fixed connectives so that two readings of the
    same symptom differ only where the symptom differs. Any variation in phrasing
    is variation in the vector, and would be indistinguishable from a difference
    in the disease.
    """
    parts = []
    if crop and crop != "unknown":
        parts.append(f"On {crop}")
    for field in ("leaf_condition", "lesion_shape", "lesion_colour",
                  "lesion_margin", "distribution", "surface"):
        value = (features.get(field) or "").strip()
        if value and value.lower() not in ("unknown", "none", ""):
            parts.append(f"{field.replace('_', ' ')}: {value}")
    return "; ".join(parts) if parts else "no readable symptoms"


def add_example(crop: str, disease: str, features: dict, source: str,
                healthy: bool = False) -> bool:
    """Store one labelled reference reading with its embedding."""
    if not db.is_available():
        return False
    text = sentence(features, crop)
    vector = knowledge.embed(text)
    if vector is None:
        return False
    try:
        with db.connection() as conn:
            conn.execute(
                """
                INSERT INTO lesion_examples
                       (crop, disease, healthy, description, features, source, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                ON CONFLICT (source) DO NOTHING
                """,
                (crop.lower(), disease.lower(), healthy, text,
                 json.dumps(features), source, str(vector)),
            )
        return True
    except Exception as e:
        print(f"Could not store lesion example {source}: {e}")
        return False


def size() -> dict:
    """How many examples the bank holds, per crop. Empty when unavailable."""
    if not db.is_available():
        return {}
    try:
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT crop, count(*) FROM lesion_examples GROUP BY crop ORDER BY 2 DESC"
            ).fetchall()
        return {crop: n for crop, n in rows}
    except Exception:
        return {}


# Matching is on the fields themselves, not on an embedding of them. That was
# measured, not assumed: with 348 reference readings, the cosine similarity
# between a pair of readings of the SAME disease had median 1.000, and between
# a pair of DIFFERENT diseases also 1.000. No threshold anywhere between 0.60
# and 0.85 separated them.
#
# The cause is the sentence itself. Every description shares the same
# scaffolding - "On tomato; leaf condition: ...; lesion shape: ..." - so the
# template dominates the vector and the handful of varying terms barely move it.
# Embedding a fixed template measures the template.
#
# Counting agreeing fields has none of that problem, costs no API call, is
# deterministic, and says something a distance cannot: *which* observations
# agreed. "Four of six symptom fields match" can be shown to an agronomist.
MATCH_FIELDS = tuple(VOCABULARY)

# Below this many agreeing fields the reference is not describing the same thing
# and must not vote.
MIN_FIELDS = 3


def _score(a: dict, b: dict) -> int:
    """How many symptom fields two readings agree on."""
    return sum(
        1 for f in MATCH_FIELDS
        if (a.get(f) or "").strip().lower()
        and (a.get(f) or "").strip().lower() == (b.get(f) or "").strip().lower()
    )


def nearest(features: dict, crop: str | None = None, limit: int = NEIGHBOURS) -> list[dict]:
    """The labelled readings that agree with this one on the most fields.

    Narrowed to the crop when one is known. A tomato lesion that resembles a
    grape lesion is a coincidence, not evidence, and letting it vote is how a
    farmer gets told their tomatoes have a grape disease.
    """
    if not db.is_available():
        return []
    try:
        with db.connection() as conn:
            if crop and crop != "unknown":
                rows = conn.execute(
                    "SELECT crop, disease, healthy, description, source, features"
                    "  FROM lesion_examples WHERE lower(crop) = %s",
                    (crop.lower(),),
                ).fetchall()
            else:
                # No crop means no safe comparison. Symptom vocabulary is shared
                # across crops, so the nearest reading would be arbitrary.
                return []
    except Exception as e:
        print(f"Lesion lookup failed: {e}")
        return []

    scored = []
    for crop_, disease, healthy, description, source, stored in rows:
        stored = stored if isinstance(stored, dict) else json.loads(stored or "{}")
        score = _score(features, stored)
        if score >= MIN_FIELDS:
            scored.append({
                "crop": crop_, "disease": disease, "healthy": healthy,
                "description": description, "source": source,
                "fields_matched": score,
                # Kept on the same 0-1 scale the rest of the system reports
                # similarity on, so callers and logs do not need a special case.
                "similarity": score / len(MATCH_FIELDS),
            })
    scored.sort(key=lambda r: -r["fields_matched"])
    return scored[:limit]


def consult(features: dict, crop: str | None, proposed: str | None,
            floor: float = DEFAULT_FLOOR) -> dict:
    """Weigh the model's proposed disease against the labelled bank.

    Returns a verdict the caller can act on::

        {"verdict": "confirmed" | "disputed" | "uncovered" | "unavailable",
         "disease": what to act on, or None,
         "alternatives": other diseases the neighbours suggest,
         "neighbours": the rows themselves, for showing a person,
         "similarity": how close the nearest one was}

    "uncovered" is the important one and is not a failure. The bank holds nine
    crops from a lab corpus; a farmer photographing cotton will land here, and
    the honest response is to say the picture was not enough rather than to
    borrow a verdict from a crop it does not resemble.
    """
    neighbours = nearest(features, crop)
    if not neighbours:
        return {"verdict": "unavailable" if not db.is_available() else "uncovered",
                "disease": None, "alternatives": [], "neighbours": [],
                "similarity": 0.0}

    top = neighbours[0]["similarity"]
    if top < floor:
        return {"verdict": "uncovered", "disease": None, "alternatives": [],
                "neighbours": neighbours, "similarity": top}

    # Only neighbours above the floor get a vote.
    voting = [n for n in neighbours if n["similarity"] >= floor]
    tally = {}
    for n in voting:
        label = "healthy" if n["healthy"] else n["disease"]
        tally[label] = tally.get(label, 0) + 1
    ranked = sorted(tally.items(), key=lambda kv: -kv[1])
    winner, votes = ranked[0]

    proposed_l = (proposed or "").strip().lower()
    # Substring either way: the register writes "leaf blast", the model may say
    # "blast", and these are the same disease.
    agrees = bool(proposed_l) and any(
        proposed_l in label or label in proposed_l for label, _ in ranked
    )

    if agrees and votes >= 2:
        return {"verdict": "confirmed", "disease": proposed or winner,
                "alternatives": [l for l, _ in ranked[1:]],
                "neighbours": voting, "similarity": top}

    # The bank is confident and the model said something else, or the bank
    # itself is split. Either way the farmer is owed both names and a question,
    # not one of them asserted.
    return {"verdict": "disputed", "disease": None,
            "alternatives": [l for l, _ in ranked] + ([proposed] if proposed_l else []),
            "neighbours": voting, "similarity": top}
