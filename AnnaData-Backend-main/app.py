import encoding_setup  # noqa: F401  (must be first)

import json
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import config
import db
import feedback
import lesion_bank
import msp
import profile_store
import startup
import weather_tool
from Agent import run_agent, speech_language
from process_media import process_media, understand_media

app = FastAPI(title="Annadata Agent API")


def _build_origins() -> list[str]:
    origins = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
    ]
    if config.FRONTEND_URL:
        origins.append(config.FRONTEND_URL.rstrip("/"))
    if config.CORS_ORIGINS:
        origins.extend(
            o.strip().rstrip("/") for o in config.CORS_ORIGINS.split(",") if o.strip()
        )
    return sorted(set(origins))


app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    """Warm up optional subsystems without letting a failure block the service."""
    startup.init_earth_engine()
    db.init()
    feedback.init()
    lesion_bank.init()
    msp.init()
    print(f"CORS origins: {_build_origins()}")
    print(f"Features: {config.feature_status()}")


class QueryRequest(BaseModel):
    query: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    history: Optional[List[dict]] = None
    # "sms" produces a short plain-text answer; "web" allows markdown.
    channel: Optional[str] = "web"
    # Stable identity for the farmer - their phone number on SMS. When given,
    # the agent recalls their profile and recent conversation, and remembers
    # whatever it learns from this message.
    user_id: Optional[str] = None
    # Gateway message id, so a redelivered webhook cannot be logged twice.
    message_id: Optional[str] = None


@app.on_event("shutdown")
def on_shutdown():
    db.close()


# HEAD as well as GET. Render serves every response chunked with no
# Content-Length, and monitoring services that cannot bound a response in
# advance reject even a seventy-byte one as "output too large". A HEAD request
# has no body at all, which sidesteps the problem entirely.
@app.api_route("/", methods=["GET", "HEAD"])
def root():
    return {"message": "AnnaData Agent API is running!"}


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    """Readiness plus which integrations are actually configured."""
    return {
        "status": "ok",
        "features": config.feature_status(),
        "earth_engine": startup.status(),
        "database": db.status(),
        # How many labelled photographs the disease check can draw on, per
        # crop. A crop absent here is one the check abstains on rather than
        # guesses at, so this is coverage, not just a count.
        "lesion_bank": lesion_bank.size(),
        "last_weather_error": weather_tool.last_error(),
    }


def _answer(query, *, user_id, channel, latitude, longitude, history,
            message_id=None, vision=None):
    """Answer one message and record what it taught us about the farmer.

    Shared by the text and the media endpoints, so a voice note or a photo gets
    the same profile recall, history, logging and rating bookkeeping that a
    typed question does. When these were separate, media went through a path
    that remembered nothing.
    """
    profile = profile_store.get_profile(user_id) if user_id else None

    # An explicit position in the request wins; otherwise fall back to what we
    # remember, which is what gives SMS access to the location-aware tools.
    if (latitude is None or longitude is None) and profile:
        latitude = profile.get("latitude")
        longitude = profile.get("longitude")

    # The caller may pass history explicitly (the web app does); otherwise
    # rebuild it from what this farmer has sent before.
    if history is None and user_id:
        history = profile_store.recent_history(user_id)

    session_id = feedback.current_session(user_id) if user_id else None
    if user_id:
        profile_store.log_message(user_id, "inbound", query,
                                  gateway_message_id=message_id,
                                  session_id=session_id)

    try:
        result = run_agent(
            query=query,
            latitude=latitude,
            longitude=longitude,
            history=history,
            channel=channel,
            profile=profile,
            vision=vision,
        )
    except Exception as e:
        # Previously this returned 200 with an {"error": ...} body, so callers
        # (the SMS bridge especially) treated failures as successful replies.
        print(f"Error in agent function: {e}")
        raise HTTPException(status_code=502, detail=f"Agent failed: {e}")

    needs_location = False
    if user_id:
        profile_store.remember(
            user_id,
            channel=channel,
            location_text=result.location,
            latitude=result.latitude,
            longitude=result.longitude,
            state=result.state,
            district=result.district,
            location_kind=result.location_kind,
            crop=result.crop,
        )
        profile_store.log_message(
            user_id, "outbound", result.answer,
            meta={"tools": result.tools_used, "channel": channel,
                  "intent": result.intent,
        "message_type": result.message_type, "missing": result.missing_slots},
        )
        # Re-read so the decision reflects anything just learned.
        needs_location = profile_store.should_ask_location(
            profile_store.get_profile(user_id)
        )
        if needs_location:
            profile_store.mark_location_asked(user_id)

    return {
        "answer": result.answer,
        # Which voice should read this aloud. Decided here from the script the
        # answer is actually in, so the browser never has to guess.
        "reply_language": speech_language(result.answer),
        "needs_location": needs_location,
        "tools_used": result.tools_used,
        "intent": result.intent,
        "message_type": result.message_type,
        # Exactly what the farmer has not told us yet, so the caller can ask
        # for that one thing instead of a generic prompt.
        "missing_slots": result.missing_slots,
        "session_id": session_id,
    }


@app.post("/agent")
def run_agent_endpoint(request: QueryRequest):
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    return _answer(
        request.query,
        user_id=(request.user_id or "").strip() or None,
        channel=request.channel or "web",
        latitude=request.latitude,
        longitude=request.longitude,
        history=request.history,
        message_id=request.message_id,
    )


def _parse_history(raw: Optional[str]) -> Optional[List[dict]]:
    """History arrives as a JSON string on a multipart form, not as a list."""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else None
    except (ValueError, TypeError):
        print("Ignoring unparseable history on a media request")
        return None


def _to_float(raw: Optional[str]) -> Optional[float]:
    try:
        return float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None


@app.post("/agent/media")
async def run_agent_media(
    audio: Optional[UploadFile] = File(None, description="Voice note"),
    image: Optional[UploadFile] = File(None, description="Photo of the crop"),
    query: str = Form(""),
    latitude: Optional[str] = Form(None),
    longitude: Optional[str] = Form(None),
    history: Optional[str] = Form(None),
    channel: str = Form("web"),
    user_id: Optional[str] = Form(None),
    message_id: Optional[str] = Form(None),
):
    """A voice note and/or a photo, answered in one round trip.

    The previous design had the browser call a describe endpoint, splice the
    description into the text box as a parenthetical, and then post that string
    to `/agent`. That cost two sequential trips on the one interaction a farmer
    is most likely to be standing in a field for, and it reduced a structured
    reading of the photograph to prose the parser had to recover slots from.

    The transcript becomes the farmer's question, verbatim and in their own
    script, so every language rule downstream sees what they actually said.
    """
    audio_bytes = await audio.read() if audio is not None else None
    image_bytes = await image.read() if image is not None else None

    typed = (query or "").strip()
    if not audio_bytes and not image_bytes and not typed:
        raise HTTPException(status_code=400,
                            detail="send text, an image or an audio file")

    try:
        understood = await understand_media(
            audio_bytes=audio_bytes,
            image_bytes=image_bytes,
            audio_filename=audio.filename if audio else None,
            audio_content_type=audio.content_type if audio else None,
            image_filename=image.filename if image else None,
        )
    except Exception as e:
        print(f"Media understanding failed: {e}")
        raise HTTPException(status_code=502, detail=f"Could not read the media: {e}")

    transcript = understood["transcript"]
    vision = understood["vision"]

    # What the farmer said out loud is the question. Anything they also typed is
    # appended rather than replaced - on a phone the two are usually one thought
    # split across a thumb and a microphone.
    spoken = " ".join(part for part in (transcript, typed) if part).strip()

    # A photo with no words at all still has to reach the agent as a question.
    # Phrased in English deliberately: there is no farmer utterance to match a
    # script against, so the reply follows the language of this fallback until
    # they say something themselves.
    if not spoken:
        spoken = "What is wrong with this crop, and what should I do about it?"

    if audio_bytes and not transcript:
        print("Audio carried no recognisable speech")

    # `_answer` blocks on model calls and database writes. The text endpoint is
    # a plain `def`, so FastAPI already runs it on a worker thread; this one has
    # to be async to read the upload, and so must hand the blocking part over
    # itself rather than holding the event loop for the whole answer.
    response = await run_in_threadpool(
        _answer,
        spoken,
        user_id=(user_id or "").strip() or None,
        channel=channel or "web",
        latitude=_to_float(latitude),
        longitude=_to_float(longitude),
        history=_parse_history(history),
        message_id=message_id,
        vision=vision,
    )

    # Echoed back so the browser can show the farmer what was heard and what was
    # seen. A transcript they can read is also how they catch a misheard word.
    response["transcript"] = transcript
    response["vision"] = vision
    response["query_used"] = spoken
    return response


class UserRequest(BaseModel):
    """Anything addressed at a single farmer by their identifier."""
    user_id: str


class RatingRequest(BaseModel):
    user_id: str
    message: str
    session_id: Optional[int] = None


@app.post("/feedback/rating")
def record_rating(request: RatingRequest):
    """Record a farmer's rating, if their reply contains one.

    Returns whether it was a rating at all, so the caller can fall back to
    answering the message as an ordinary question when it was not.
    """
    user_id = (request.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id must not be empty")

    if not feedback.awaiting_reply(user_id):
        return {"is_rating": False, "reason": "not awaiting a rating"}

    rating = feedback.parse_rating(request.message)
    if rating is None:
        return {"is_rating": False, "reason": "no rating found in the message"}

    session_id = request.session_id or feedback.current_session(user_id)
    stored = feedback.record(user_id, rating, request.message, session_id)
    return {"is_rating": True, "rating": rating, "stored": stored}


@app.get("/feedback/due")
def feedback_due():
    """Farmers whose conversation has ended and who are due to be asked.

    Called on a schedule by the SMS bridge; kept as a query rather than a push
    so the backend never needs to send anything itself.
    """
    return {"due": feedback.due_for_feedback()}


@app.post("/feedback/asked")
def feedback_asked(request: UserRequest):
    """Record that a farmer has been asked, so they are not asked again."""
    feedback.mark_asked((request.user_id or "").strip())
    return {"ok": True}


@app.get("/feedback/summary")
def feedback_summary():
    """Ratings so far, and which kinds of question score worst."""
    return feedback.summary()


@app.post("/forget")
def forget(request: UserRequest):
    """Erase a farmer's profile and message history. Backs the STOP keyword."""
    user_id = (request.user_id or "").strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id must not be empty")
    return {"erased": profile_store.forget(user_id)}


@app.post("/api/chat/describe")
async def chat_describe(
    audio: Optional[UploadFile] = File(None, description="Optional audio file"),
    image: Optional[UploadFile] = File(None, description="Optional image file"),
):
    audio_bytes = await audio.read() if audio is not None else None
    image_bytes = await image.read() if image is not None else None

    if not audio_bytes and not image_bytes:
        return JSONResponse(content={"error": "No file provided"}, status_code=400)

    if audio_bytes and image_bytes:
        prompt_text = (
            "First transcribe the audio into English, then describe the crop "
            "details from the image. Output format: Audio: , Crop Name: , "
            "Crop Type: , Crop Stage: , Pests/Diseases: ."
        )
    elif audio_bytes:
        prompt_text = "Transcribe this audio into English."
    else:
        prompt_text = (
            "Provide the crop name, crop type, crop stage, and any visible pests "
            "or diseases in one line. Output format: Crop Name: , Crop Type: , "
            "Crop Stage: , Pests/Diseases: ."
        )

    try:
        output = await process_media(
            audio_bytes=audio_bytes,
            image_bytes=image_bytes,
            audio_filename=audio.filename if audio else None,
            audio_content_type=audio.content_type if audio else None,
            image_filename=image.filename if image else None,
            extra_prompt=prompt_text,
        )
    except Exception as e:
        print(f"Media processing failed: {e}")
        raise HTTPException(status_code=502, detail=f"Media processing failed: {e}")

    return JSONResponse(content={"Result": (output or "").strip()})
