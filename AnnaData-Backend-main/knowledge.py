"""
Grounded knowledge: approved pesticide doses, and retrieved reference text.

Two stores, because the two problems are not alike.

`pesticide_uses` is a structured table looked up on crop and pest. A dose is a
precise fact with a right answer, and semantic similarity is the wrong tool for
it - retrieving prose that mentions a chemical does not tell you the approved
rate for this crop and this pest. Matching on the pair does, and it also lets
the agent do the thing that matters most: say nothing when the pair is not
registered, rather than produce a plausible number.

`documents` is a pgvector store for the open-ended material - schemes,
subsidies, storage, general practice - where there is no single right answer and
similarity is exactly right.

Both live in the Postgres already provisioned for farmer profiles, so this adds
no infrastructure and no cost.
"""
import json
import urllib.request

import db
from config import GEMINI_API_KEY

EMBED_MODEL = "gemini-embedding-001"
EMBED_DIM = 768

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;

-- Approved pesticide uses. One row per product/crop/pest combination, taken
-- from the registration authority rather than from a model.
CREATE TABLE IF NOT EXISTS pesticide_uses (
    id            BIGSERIAL PRIMARY KEY,
    category      TEXT,           -- insecticide, fungicide, herbicide, bio-*
    product       TEXT NOT NULL,  -- e.g. 'Emamectin Benzoate 5% SG'
    crop          TEXT NOT NULL,
    pest          TEXT NOT NULL,
    dose_formulation TEXT,        -- rate of the product as sold
    dose_ai       TEXT,           -- rate of active ingredient
    dilution      TEXT,           -- water volume
    waiting_period TEXT,          -- days between spraying and harvest
    source        TEXT NOT NULL,  -- which document, and as of when
    source_url    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (product, crop, pest)
);

CREATE INDEX IF NOT EXISTS pesticide_crop_pest
    ON pesticide_uses (lower(crop), lower(pest));

-- Reference text for open-ended questions.
CREATE TABLE IF NOT EXISTS documents (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT NOT NULL,
    title       TEXT,
    url         TEXT,
    chunk_index INTEGER NOT NULL DEFAULT 0,
    content     TEXT NOT NULL,
    embedding   vector({EMBED_DIM}),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS documents_embedding
    ON documents USING hnsw (embedding vector_cosine_ops);
"""


def init() -> bool:
    """Create the knowledge tables. Safe to call repeatedly."""
    if not db.is_available():
        return False
    try:
        with db.connection() as conn:
            conn.execute(SCHEMA)
        return True
    except Exception as e:
        print(f"Knowledge store unavailable: {e}")
        return False


def embed(text: str, dim: int = EMBED_DIM) -> list[float] | None:
    """Embed one piece of text, or None if the call fails."""
    if not GEMINI_API_KEY or not text:
        return None
    body = json.dumps({
        "model": f"models/{EMBED_MODEL}",
        "content": {"parts": [{"text": text}]},
        "outputDimensionality": dim,
    }).encode()
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{EMBED_MODEL}:embedContent?key={GEMINI_API_KEY}")
    try:
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)["embedding"]["values"]
    except Exception as e:
        print(f"Embedding failed: {e}")
        return None


# --- approved doses ---------------------------------------------------------

def approved_uses(crop: str | None, pest: str | None = None, limit: int = 8) -> dict:
    """Registered product uses for a crop, optionally narrowed to a pest.

    Matching is deliberately loose on the pest - farmers say "sundi" and
    "bollworm" and "इल्ली" for the same insect - but never loose enough to
    return a use for a different crop.
    """
    if not crop or not db.is_available():
        return {"uses": [], "pest_matched": False}
    try:
        with db.connection() as conn:
            if pest:
                rows = conn.execute(
                    """
                    SELECT product, crop, pest, dose_formulation, dose_ai,
                           dilution, waiting_period, source
                      FROM pesticide_uses
                     WHERE lower(crop) = lower(%s)
                       AND (lower(pest) LIKE lower(%s) OR lower(%s) LIKE '%%' || lower(pest) || '%%')
                     LIMIT %s
                    """,
                    (crop, f"%{pest}%", pest, limit),
                ).fetchall()
                if rows:
                    return {"uses": _rows_to_dicts(rows), "pest_matched": True}
            rows = conn.execute(
                """
                SELECT product, crop, pest, dose_formulation, dose_ai,
                       dilution, waiting_period, source
                  FROM pesticide_uses
                 WHERE lower(crop) = lower(%s)
                 LIMIT %s
                """,
                (crop, limit),
            ).fetchall()
            # Nothing registered for this pest. What is registered for the crop
            # is still worth showing, but it must never be presented as an
            # answer for the pest asked about - a bollworm product offered for
            # locusts is exactly the error this table exists to prevent.
            return {"uses": _rows_to_dicts(rows), "pest_matched": False}
    except Exception as e:
        print(f"Approved use lookup failed for crop={crop!r}: {e}")
        return {"uses": [], "pest_matched": False}


def _rows_to_dicts(rows) -> list[dict]:
    keys = ("product", "crop", "pest", "dose_formulation", "dose_ai",
            "dilution", "waiting_period", "source")
    return [dict(zip(keys, r)) for r in rows]


def format_uses(result: dict, pest: str | None = None) -> str:
    """Render approved uses for the prompt, or say plainly that none are known."""
    uses = result.get("uses") or []
    if not uses:
        return ("No registered pesticide use is on file for this crop and pest. "
                "Do NOT state any product name or dose. Tell the farmer you "
                "cannot recommend a specific chemical and refer them to their "
                "local Krishi Vigyan Kendra or agriculture officer.")

    if not result.get("pest_matched"):
        target = f"'{pest}'" if pest else "the pest asked about"
        lines = [
            f"WARNING: nothing is registered for {target} on this crop. "
            "The uses below are registered for DIFFERENT pests and must NOT be "
            "recommended for the one asked about. Say plainly that you have no "
            "approved treatment for this pest and refer the farmer to their "
            "Krishi Vigyan Kendra. The list is context only:",
        ]
    else:
        lines = ["Registered pesticide uses (these are the ONLY doses you may quote):"]
    for u in uses:
        bits = [f"{u['product']} for {u['pest']} on {u['crop']}"]
        if u.get("dose_formulation"):
            bits.append(f"dose {u['dose_formulation']}")
        if u.get("dilution"):
            bits.append(f"in {u['dilution']}")
        if u.get("waiting_period"):
            bits.append(f"wait {u['waiting_period']} before harvest")
        lines.append(f"- {', '.join(bits)} [{u['source']}]")
    return "\n".join(lines)


# --- reference text ---------------------------------------------------------

def search(query: str, limit: int = 5) -> list[dict]:
    """Passages most similar to the query, with their sources."""
    if not query or not db.is_available():
        return []
    vector = embed(query)
    if vector is None:
        return []
    try:
        with db.connection() as conn:
            rows = conn.execute(
                """
                SELECT content, source, title, url,
                       1 - (embedding <=> %s::vector) AS similarity
                  FROM documents
                 WHERE embedding IS NOT NULL
              ORDER BY embedding <=> %s::vector
                 LIMIT %s
                """,
                (str(vector), str(vector), limit),
            ).fetchall()
        return [
            {"content": c, "source": s, "title": t, "url": u, "similarity": sim}
            for c, s, t, u, sim in rows
        ]
    except Exception as e:
        print(f"Knowledge search failed: {e}")
        return []


def add_document(source: str, content: str, title: str = None,
                 url: str = None, chunk_index: int = 0) -> bool:
    """Store one passage with its embedding."""
    if not db.is_available() or not content.strip():
        return False
    vector = embed(content)
    if vector is None:
        return False
    try:
        with db.connection() as conn:
            conn.execute(
                """
                INSERT INTO documents (source, title, url, chunk_index, content, embedding)
                VALUES (%s, %s, %s, %s, %s, %s::vector)
                """,
                (source, title, url, chunk_index, content, str(vector)),
            )
        return True
    except Exception as e:
        print(f"Could not store document: {e}")
        return False


def counts() -> dict:
    """How much grounded knowledge is actually loaded."""
    if not db.is_available():
        return {"pesticide_uses": 0, "documents": 0}
    try:
        with db.connection() as conn:
            uses = conn.execute("SELECT count(*) FROM pesticide_uses").fetchone()[0]
            docs = conn.execute("SELECT count(*) FROM documents").fetchone()[0]
        return {"pesticide_uses": uses, "documents": docs}
    except Exception:
        return {"pesticide_uses": 0, "documents": 0}
