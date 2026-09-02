"""
Audio and image understanding, on the way in to the agent.

Two things this module is careful about, both learned from what the previous
version did wrong.

**Audio is transcribed verbatim, in the language and script the farmer spoke.**
The old prompt said "Transcribe this audio into English", which quietly
defeated the entire multilingual path. The agent decides its reply script in
code from the query text (`Agent.script_of`), so a farmer speaking Hindi had
their words turned into English before the agent ever saw them, and was
answered in English. Transcription is not the place to translate.

**The image is read for observations, not for advice.** It reports the crop and
what is visible on the plant, and it is allowed to say it cannot tell. What to
spray is decided afterwards from the registered-use table, never from the
photograph - the same discipline every other dose in this system follows. A
model looking at a leaf is a plausible guess about a symptom, not an authority
on what may legally be sprayed on it.

Both come back as structured fields rather than one prose blob, because the
caller puts them in different places: the transcript becomes the farmer's
question, the visual findings become context alongside soil and weather.
"""
import asyncio
import json
import os
import re
import tempfile

from google.genai import types

import lesion_bank
from config import MEDIA_MODEL
from utils import get_client

AUDIO_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/aac": ".aac",
    "audio/flac": ".flac",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}

UNKNOWN = "unknown"


def _audio_extension(filename: str | None, content_type: str | None) -> str:
    """Gemini infers MIME type from the filename, so the extension must be real.

    The browser records WebM (MediaRecorder's default) and the previous version
    always wrote a .mp3 temp file, so WebM bytes were uploaded labelled as MP3.
    """
    if content_type:
        base = content_type.split(";")[0].strip().lower()
        if base in AUDIO_EXTENSIONS:
            return AUDIO_EXTENSIONS[base]
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext in set(AUDIO_EXTENSIONS.values()):
            return ext
    return ".webm"  # MediaRecorder's default in Chrome and Firefox


def _image_extension(filename: str | None) -> str:
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            return ext
    return ".jpg"


# The instruction not to translate is stated twice on purpose. Said once it
# loses to the model's habit of being helpful: asked to write down Hindi speech
# it offers English unless told plainly, more than once, not to.
TRANSCRIBE_PROMPT = """
You are transcribing a voice message from an Indian farmer.

Write down EXACTLY what they said, word for word, in THEIR OWN LANGUAGE and in
the script that language is normally written in. Hindi speech is written in
Devanagari, Punjabi in Gurmukhi, Bengali in Bengali, Marathi in Devanagari,
Telugu in Telugu, English in the Latin alphabet.

DO NOT translate. DO NOT summarise. DO NOT answer the question or add advice of
your own. If they mix English words into an Indian language, keep the mixture
exactly as spoken.

If the audio is silent, or is noise with no speech in it, return an empty
string for the transcript.
"""

# What the photograph shows, and nothing beyond it. The refusal path matters as
# much as the identification: a confident wrong disease name sends a farmer to
# buy the wrong chemical, and the registered-use lookup downstream is only as
# good as the pest name handed to it.
IMAGE_PROMPT = """
You are an agricultural scientist looking at a photograph from an Indian
farmer's field.

Report only what you can actually SEE. You are identifying a plant and a
symptom, not prescribing a treatment.

- crop: the crop in the photo, English common name, lowercase - rice, wheat,
  cotton, tomato, brinjal, chilli, sugarcane. "unknown" if you cannot tell.
- pest: the pest, insect or disease responsible, as its ENGLISH COMMON NAME as
  an Indian agricultural extension officer would write it - bollworm, stem
  borer, blast, brown spot, leaf rust, aphid, whitefly, powdery mildew, late
  blight. One name only. "unknown" if the photo does not show enough to say, or
  if what you see could equally be several different things.
- stage: crop growth stage if visible - seedling, vegetative, tillering,
  flowering, fruiting, maturity. "unknown" if you cannot tell.
- symptoms: one short factual sentence describing the visible damage - what
  colour, what shape, where on the plant. Describe, do not diagnose.
- severity: "mild", "moderate", "severe" or "unknown", from how much of the
  visible tissue is affected.
- confidence: "high", "medium" or "low" - how sure you are of the pest name.

Guessing is worse than admitting uncertainty here: the name you give is used to
look up which chemicals are legally registered against that pest, so a wrong
name returns a wrong treatment. When the photo is blurred, too far away, shows
no plant, or shows damage that several causes share, set pest to "unknown" and
say so in symptoms.
"""

_MEDIA_SCHEMA = {
    "type": "object",
    "properties": {
        "transcript": {"type": "string"},
        "crop": {"type": "string"},
        "pest": {"type": "string"},
        "stage": {"type": "string"},
        "symptoms": {"type": "string"},
        "severity": {"type": "string"},
        "confidence": {"type": "string"},
        # The same photograph read a second way, into a closed vocabulary, so
        # the reading can be matched against labelled examples. Collected on the
        # same call: a second round trip to the Files API would double the wait
        # for a farmer already standing in a field.
        **{field: {"type": "string"} for field in lesion_bank.VOCABULARY},
        "usable": {"type": "boolean"},
    },
}

_JSON_KEYS_INSTRUCTION = (
    "Return a single JSON object with the keys: transcript, crop, pest, stage, "
    "symptoms, severity, confidence. Use the string unknown for anything you "
    "cannot determine, and an empty string for transcript when there is no audio."
)

# Appended to the image instruction. The free-text reading above is the model's
# own opinion; this one is a structured observation that can be looked up
# against labelled photographs, and the two are cross-checked afterwards.
def _controlled_reading_instruction() -> str:
    return (
        "SEPARATELY from your own reading above, and without letting it "
        "influence you, describe the SAME photograph using this closed "
        "vocabulary. Add these keys to the same JSON object.\n\n"
        + lesion_bank.vocabulary_prompt()
    )

_BOTH_INSTRUCTION = (
    "The audio and the photograph are from the same farmer about the same "
    "problem. Transcribe the audio AND report the photograph; the farmer's "
    "words may name the crop the photo does not show clearly."
)


def _upload(client, data: bytes, suffix: str):
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return client.files.upload(file=tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _parse_json(text: str) -> dict:
    """Read the model's JSON, tolerating a markdown fence around it.

    `response_mime_type` makes bare JSON the normal case, but a fallback model
    in the chain need not honour it and a fenced block is the usual way that
    fails. Anything unparseable yields an empty dict rather than raising: a
    farmer who attached a photo should still get their question answered.
    """
    if not text:
        return {}
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", text.strip())
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        print(f"Media output was not JSON: {text[:200]!r}")
        return {}


def _clean(value, default: str = UNKNOWN) -> str:
    """Normalise one field, treating the model's ways of saying nothing as unknown."""
    text = value.strip() if isinstance(value, str) else ""
    if not text or text.lower() in {"unknown", "none", "n/a", "na", "null", "-"}:
        return default
    return text


def _understand(
    audio_bytes: bytes | None = None,
    image_bytes: bytes | None = None,
    audio_filename: str | None = None,
    audio_content_type: str | None = None,
    image_filename: str | None = None,
) -> dict:
    """The blocking body of `understand_media`. Runs on a worker thread."""
    if not audio_bytes and not image_bytes:
        return {"transcript": "", "vision": None}

    client = get_client()

    instructions = []
    if audio_bytes:
        instructions.append(TRANSCRIBE_PROMPT)
    if image_bytes:
        instructions.append(IMAGE_PROMPT)
        instructions.append(_controlled_reading_instruction())
    if audio_bytes and image_bytes:
        instructions.append(_BOTH_INSTRUCTION)
    instructions.append(_JSON_KEYS_INSTRUCTION)

    parts: list = ["\n\n".join(instructions)]
    if audio_bytes:
        parts.append(_upload(client, audio_bytes,
                             _audio_extension(audio_filename, audio_content_type)))
    if image_bytes:
        parts.append(_upload(client, image_bytes, _image_extension(image_filename)))

    result = client.models.generate_content(
        model=MEDIA_MODEL,
        contents=parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_MEDIA_SCHEMA,
        ),
    )
    data = _parse_json(getattr(result, "text", "") or "")

    transcript = _clean(data.get("transcript"), default="") if audio_bytes else ""

    vision = None
    if image_bytes:
        vision = {
            "crop": _clean(data.get("crop")),
            "pest": _clean(data.get("pest")),
            "stage": _clean(data.get("stage")),
            "symptoms": _clean(data.get("symptoms")),
            "severity": _clean(data.get("severity")),
            "confidence": _clean(data.get("confidence"), default="low"),
            # The closed-vocabulary reading, kept separate from the model's own
            # opinion so the two can disagree without one quietly overwriting
            # the other.
            "features": {f: _clean(data.get(f), default="")
                         for f in lesion_bank.VOCABULARY},
            "usable": data.get("usable", True) is not False,
        }

    print(f"Media understood: transcript={transcript[:80]!r} vision={vision}")
    return {"transcript": transcript, "vision": vision}


async def understand_media(**kwargs) -> dict:
    """Turn a voice note and/or a photo into fields the agent can act on.

    Returns::

        {"transcript": what the farmer said, in their own script ("" if none),
         "vision": {crop, pest, stage, symptoms, severity, confidence} or None}

    One model call handles both. Uploading to the Files API and waiting on a
    generation is the expensive part, and doing it twice doubles the wait on the
    one interaction where the farmer is already standing in a field holding up a
    phone.

    The upload and the generation are both blocking calls, so they run on a
    worker thread. Awaited directly on the event loop they stall every other
    request for the seconds a photo takes - including `/health`, which is what
    the keep-warm ping and the SMS bridge use to decide the service is alive.
    """
    return await asyncio.to_thread(_understand, **kwargs)


def describe_vision(vision: dict | None) -> str:
    """The photograph's findings as one line for the advisory prompt.

    Written as observation with its confidence attached, so the model composing
    the answer can hedge an uncertain identification rather than repeating it
    back to the farmer as established fact.
    """
    if not vision:
        return ""
    bits = []
    if vision.get("crop", UNKNOWN) != UNKNOWN:
        bits.append(f"crop appears to be {vision['crop']}")
    if vision.get("stage", UNKNOWN) != UNKNOWN:
        bits.append(f"stage {vision['stage']}")
    if vision.get("symptoms", UNKNOWN) != UNKNOWN:
        bits.append(f"visible: {vision['symptoms']}")
    if vision.get("pest", UNKNOWN) != UNKNOWN:
        bits.append(f"likely {vision['pest']} "
                    f"({vision.get('confidence', 'low')} confidence from the photo alone)")
    if vision.get("severity", UNKNOWN) != UNKNOWN:
        bits.append(f"severity {vision['severity']}")

    # What the labelled bank made of the same picture. Stated as corroboration
    # or as conflict, never merged into the reading above - the point of keeping
    # two independent opinions is lost the moment they are written as one.
    corr = vision.get("corroboration") or {}
    verdict = corr.get("verdict")
    if verdict == "confirmed":
        near = corr.get("neighbours") or []
        bits.append(
            f"CORROBORATED: {len(near)} labelled photographs of this crop showing "
            f"the same symptoms are all {corr.get('disease')} "
            f"(closest match {corr.get('similarity', 0):.2f})"
        )
    elif verdict == "disputed":
        others = ", ".join(dict.fromkeys(a for a in corr.get("alternatives") or [] if a))
        bits.append(
            f"NOT CONFIRMED: labelled photographs of this crop with these symptoms "
            f"point to more than one thing ({others}). The picture alone cannot "
            f"separate them"
        )
    elif verdict == "uncovered":
        bits.append(
            "no labelled photographs of this crop are held, so the reading above "
            "is the model's own and is uncorroborated"
        )

    if not bits:
        return "a photo was sent, but nothing in it could be identified"
    return "; ".join(bits)


async def process_media(
    audio_bytes=None,
    image_bytes=None,
    extra_prompt=None,
    audio_filename=None,
    audio_content_type=None,
    image_filename=None,
):
    """Backwards-compatible prose form, still backing /api/chat/describe.

    `extra_prompt` is accepted and ignored: the prompts now live in this module
    so that a transcript keeps the farmer's own script, which is precisely what
    the caller-supplied prompt used to override.
    """
    understood = await understand_media(
        audio_bytes=audio_bytes,
        image_bytes=image_bytes,
        audio_filename=audio_filename,
        audio_content_type=audio_content_type,
        image_filename=image_filename,
    )
    pieces = []
    if understood["transcript"]:
        pieces.append(f"Audio: {understood['transcript']}")
    if understood["vision"]:
        v = understood["vision"]
        pieces.append(f"Crop Name: {v['crop']}, Crop Stage: {v['stage']}, "
                      f"Pests/Diseases: {v['pest']}, Symptoms: {v['symptoms']}")
    return " | ".join(pieces)
