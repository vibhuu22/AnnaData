import encoding_setup  # noqa: F401  (must be first)

import asyncio
import json
import queue
import re
import threading
import secrets
import time
from uuid import UUID
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

import auth
import config
import db
import farmer_account
import feedback
import guest_access
import msg91
import whereabouts
import lesion_bank
import msp
import news
import profile_store
import sms_out
import startup
import tts
import weather_tool
import metrics_store
import admin_api
from Agent import AgentResult, run_agent, speech_language
from Address_Convertor import reverse
from process_media import process_media, understand_media

app = FastAPI(title="Annadata Agent API")
app.include_router(admin_api.router)
app.mount('/admin/assets', StaticFiles(directory=Path(__file__).parent/'admin_web'), name='admin-assets')


@app.middleware('http')
async def protect_admin_responses(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith('/admin'):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
    return response


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
    # Read by the browser: the sample rate of streamed speech, and how long to
    # wait after a 429.
    expose_headers=["X-Sample-Rate", "Retry-After"],
)


@app.on_event("startup")
def on_startup():
    """Warm up optional subsystems without letting a failure block the service."""
    startup.init_earth_engine()
    db.init()
    feedback.init()
    metrics_store.init()
    lesion_bank.init()
    msp.init()
    print(f"CORS origins: {_build_origins()}")
    print(f"Features: {config.feature_status()}")


class DeliveryEvent(BaseModel):
    request_id: UUID
    status: str
    sms_segments: Optional[int] = None


@app.post('/telemetry/delivery')
def record_delivery(event: DeliveryEvent, x_bridge_token: Optional[str] = Header(None)):
    _require_bridge(x_bridge_token, 'delivery telemetry')
    if event.status not in {'gateway_accepted', 'send_failed'}:
        raise HTTPException(422, 'Unsupported delivery status')
    if event.sms_segments is not None and not 0 <= event.sms_segments <= 100:
        raise HTTPException(422, 'Invalid segment count')
    if not metrics_store.delivery(str(event.request_id), event.status, event.sms_segments):
        raise HTTPException(503, 'Telemetry unavailable')
    return {'recorded': True}


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
    # Which of the farmer's chats this belongs to, made by the browser. Stored
    # with both messages so the web app can show conversations as separate
    # chats; SMS has none, and its messages are grouped by session instead.
    chat_id: Optional[str] = None
    request_id: Optional[UUID] = None


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
        # Whether sign-in is actually protecting anything, stated rather than
        # assumed. An ephemeral secret signs everyone out on restart, and an
        # unset bridge token leaves the operational endpoints open - both are
        # deployment mistakes that are otherwise invisible until they bite.
        "auth": {
            "required": config.AUTH_REQUIRED,
            "secret": "ephemeral" if config.AUTH_SECRET_IS_EPHEMERAL else "configured",
            "bridge_token": "configured" if config.BRIDGE_TOKEN else "not set",
            "code_transport": sms_out.transport(),
            # Questions before sign-in, and the bounds on them. Stated here
            # because an open endpoint that spends model quota is exactly the
            # kind of setting that should never be a guess.
            "guest_questions": (
                {"enabled": True, "per_hour": config.GUEST_PER_HOUR,
                 "per_address_per_hour": config.GUEST_IP_PER_HOUR,
                 "daily_cap": config.GUEST_DAILY_CAP}
                if config.GUEST_ASK_ENABLED else {"enabled": False}
            ),
        },
        # Which models will speak answers, so a silent Listen button can be
        # told apart from a misconfigured one without reading the logs.
        "speech": {"models": config.TTS_MODELS, "voice": config.TTS_VOICE},
    }


_CHAT_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def _chat(chat_id):
    """A browser-made chat id, or None if it is not a plain short token."""
    value = (chat_id or "").strip()
    return value if _CHAT_ID.match(value) else None


def _answer(query, *, user_id, channel, latitude, longitude, history,
            message_id=None, vision=None, on_text=None, chat_id=None, request_id=None):
    """Answer one message and record what it taught us about the farmer.

    Shared by the text and the media endpoints, so a voice note or a photo gets
    the same profile recall, history, logging and rating bookkeeping that a
    typed question does. When these were separate, media went through a path
    that remembered nothing.
    """
    started = time.monotonic()
    # The web sends the open chat's own turns as history; SMS sends none and
    # its context comes from the database. Kept before that lookup fills it in.
    chat_history_sent = history is not None and channel != "sms"
    profile = profile_store.get_profile(user_id) if user_id else None

    # latitude/longitude stay the request's own - the phone's. The agent
    # decides between them and the stored farm (whereabouts.choose), which is
    # also what still gives SMS, which sends none, the stored place.

    # The web app sends the turns on screen, which after opening an old
    # conversation can be fifty of them. SMS gets the last CONTEXT_MESSAGES from
    # the database; the web gets the same window, so both channels answer from
    # the same amount of context - and a long thread cannot swell the prompt.
    if history:
        history = history[-config.CONTEXT_MESSAGES:]
    # The caller may pass history explicitly (the web app does); otherwise
    # rebuild it from what this farmer has sent before.
    if history is None and user_id:
        history = profile_store.recent_history(user_id)

    session_id = feedback.current_session(user_id) if user_id else None
    request_id = metrics_store.begin(user_id, session_id, channel, str(request_id) if request_id else None)
    # Asked before the inbound message is logged, so the newest row is still
    # the previous turn. A greeting belongs at the start of a conversation and
    # nowhere else; inside one it reads as the service having forgotten you.
    #
    # On the web the conversation is the chat. A "hii" in a new chat is an
    # arrival, even if the same farmer was talking in another chat a minute
    # ago - judged by the session instead, it was taken for a goodbye and
    # answered "You're very welcome". So the chat's own turns decide there; the
    # time-based session still decides for SMS, which has no chats.
    if chat_history_sent:
        continuing_session = bool(history)
    else:
        continuing_session = feedback.in_live_session(user_id) if user_id else False
    if user_id:
        chat = _chat(chat_id)
        profile_store.log_message(user_id, "inbound", query,
                                  gateway_message_id=message_id,
                                  session_id=session_id,
                                  meta={"request_id": request_id, "channel": channel,
                                        **({"chat": chat} if chat else {})})

    # "Is your farm near Kharagpur?" is answerable by the next message only.
    pending = (profile or {}).get("farm_pending") if user_id else None
    farm_reply = None
    if pending:
        profile_store.clear_farm_pending(user_id)
        verdict = whereabouts.yes_or_no(query) if channel != "sms" else None
        if verdict is not None:
            farm_reply = _farm_answer(user_id, pending, verdict)

    try:
        result = farm_reply or run_agent(
            query=query,
            latitude=latitude,
            longitude=longitude,
            history=history,
            channel=channel,
            profile=profile,
            vision=vision,
            continuing_session=continuing_session,
            # Sentences of the answer as they are written - only for the
            # streaming endpoints, and never on SMS, which sends one message.
            on_text=on_text if channel != "sms" else None,
        )
    except Exception as e:
        # Previously this returned 200 with an {"error": ...} body, so callers
        # (the SMS bridge especially) treated failures as successful replies.
        print(f"Error in agent function: {e}")
        metrics_store.fail(request_id, user_id, type(e).__name__)
        raise HTTPException(status_code=502, detail=f"Agent failed: {e}")

    needs_location = False
    confirm_place = None
    if user_id:
        if getattr(result, "forget_location", False):
            profile_store.forget_location(user_id)
        # Only a place the farmer named in this message is written back. The
        # result's place may instead be the stored one, carried for answering,
        # and its coordinates the browser's: saving those two together is how
        # a farm came to be called Shimla while sitting at Kharagpur.
        named = getattr(result, "location_named", False)
        profile_store.remember(
            user_id,
            channel=channel,
            location_text=result.location if named else None,
            latitude=result.latitude if named else None,
            longitude=result.longitude if named else None,
            # The phone's state is used, never stored, like the rest of its place.
            state=result.state if named or getattr(result, "state_named", False) else None,
            district=result.district if named else None,
            location_kind=result.location_kind,
            crop=result.crop,
        )
        profile_store.log_message(
            user_id, "outbound", result.answer,
            # dose_status is stored because it is the one field that says an
            # answer refused to name a chemical. Without it a refusal reloaded
            # from history - after a guest signs in, after a page refresh - lost
            # its refusal styling and read as an ordinary answer, and refusals
            # could not be counted from the database at all.
            meta={"tools": result.tools_used, "channel": channel,
                  "intent": result.intent,
                  "message_type": result.message_type, "missing": result.missing_slots,
                  "dose_status": result.dose_status, "chat": _chat(chat_id),
                  "request_id": request_id},
            session_id=session_id,
        )
        # Re-read so the decision reflects anything just learned. A place this
        # answer was given for - the phone's included - means there is nothing
        # to ask: "Tell us your village or district" under an answer for
        # Kharagpur is the question this replaced.
        place_known = bool(result.location) or result.latitude is not None
        # Never under a goodbye: "tell us your district" to someone who has
        # just said "bas" keeps a finished conversation going.
        needs_location = (not place_known and result.message_type != "farewell"
                          and profile_store.should_ask_location(profile_store.get_profile(user_id)))
        if needs_location:
            profile_store.mark_location_asked(user_id)
        confirm_place = _farm_question(user_id, channel, profile, result)

    reply_language = speech_language(result.answer)
    metrics_store.finish(request_id, user_id, result, (time.monotonic()-started)*1000, reply_language)
    return {
        "request_id": request_id,
        "answer": result.answer,
        # Which voice should read this aloud. Decided here from the script the
        # answer is actually in, so the browser never has to guess.
        "reply_language": reply_language,
        "needs_location": needs_location,
        "tools_used": result.tools_used,
        "intent": result.intent,
        "message_type": result.message_type,
        # "available", "none_registered" or "not_applicable". Lets the caller
        # show a refusal as a refusal without having to find it in the prose.
        "dose_status": result.dose_status,
        # Exactly what the farmer has not told us yet, so the caller can ask
        # for that one thing instead of a generic prompt.
        "missing_slots": result.missing_slots,
        # The ranked likely causes behind a disease answer, with the reasons
        # for each and whether one is settled; None for other questions.
        "diagnosis": result.diagnosis,
        # The phone's place, when the farmer should be asked once whether it is
        # their farm. The caller words the question (asks.js), as it does the
        # other follow-up asks.
        "confirm_place": confirm_place,
        "session_id": session_id,
    }


def _farm_answer(user_id, pending, verdict):
    """The reply to a yes or no to "Is your farm near X?"."""
    language = pending.get("language") or "en"
    if verdict:
        profile_store.save_farm(user_id, pending)
        text = whereabouts.farm_saved(pending.get("name"), language)
    else:
        text = whereabouts.farm_declined(language)
    # Saved here already, so nothing is written back again after.
    return AgentResult(text, tools_used=["farm"], message_type="statement",
                       location=pending.get("name"), state=pending.get("state"),
                       latitude=pending.get("latitude"), longitude=pending.get("longitude"),
                       place_source=whereabouts.PROFILE if verdict else whereabouts.PHONE)


def _farm_question(user_id, channel, profile, result):
    """Whether to ask "Is your farm near X?" under this answer, and record it.

    Only when the answer was given for the phone's place - so the stored farm
    is absent or far from it - and only once a place. Not when something else
    is already being asked: one question under an answer, and a "haan" must
    have only one thing it can mean.
    """
    name = result.location
    if (channel == "sms" or getattr(result, "place_source", None) != whereabouts.PHONE
            or not name or result.missing_slots
            # A greeting already ends with its own question; a second one under
            # it is two questions in a row, and a "haan" could mean either. And
            # nothing is asked of a farmer who has just said goodbye.
            or {"farm", "greeting", "farewell"} & set(result.tools_used or [])):
        return None
    key = whereabouts.asked_key(name)
    if key in ((profile or {}).get("farm_asked") or []):
        return None
    profile_store.ask_about_farm(user_id, key, {
        "name": name, "latitude": result.latitude, "longitude": result.longitude,
        "state": result.state, "district": result.district, "kind": result.location_kind,
        "language": whereabouts.language_of(result.answer), "channel": channel,
    })
    return name


# --- Who is calling -------------------------------------------------------

def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


_guests = guest_access.GuestLimiter(
    per_guest=config.GUEST_PER_HOUR,
    per_ip=config.GUEST_IP_PER_HOUR,
    daily_cap=config.GUEST_DAILY_CAP,
)

# Ratings cost nothing but a row, so this only stops one browser filling the
# table.
_raters = guest_access.GuestLimiter(per_guest=60, per_ip=600, daily_cap=5000)

# Spoken answers are counted apart from questions: one answer is read as
# several pieces, so sharing the question limit would cut a guest off halfway
# through hearing their third answer.
_speakers = guest_access.GuestLimiter(
    per_guest=config.SPEAK_GUEST_PER_HOUR,
    per_ip=config.SPEAK_IP_PER_HOUR,
    daily_cap=config.SPEAK_DAILY_CAP,
)


def _caller(authorization: str | None, bridge_token: str | None,
            claimed_user_id: str | None, guest_id: str | None = None,
            client_ip: str | None = None) -> str | None:
    """The farmer this request is for, from the strongest evidence available.

    Four callers, in descending order of proof:

    1. The SMS bridge, holding BRIDGE_TOKEN. It may name any user_id, because the
       mobile network told it who sent the message and a farmer cannot forge the
       network's idea of their own number.
    2. A browser holding a signed token. The id comes out of the token; whatever
       the body says about user_id is ignored, which is the entire point.
    3. A browser that has not signed in yet, sending its own guest id. It is
       answered under `guest:<id>`, a key that can never be a phone number, so
       it reaches no real farmer's profile - and only within the limits in
       guest_access.py. Whatever the body claims about user_id is ignored here
       too.
    4. Nobody. Raises 401 when AUTH_REQUIRED, and otherwise falls back to the old
       body-supplied user_id so local development and the un-migrated bridge keep
       working.
    """
    if config.BRIDGE_TOKEN and bridge_token and \
            secrets.compare_digest(bridge_token, config.BRIDGE_TOKEN):
        return (claimed_user_id or "").strip() or None

    user_id = auth.read_token(_bearer(authorization))
    if user_id:
        return user_id

    guest = guest_access.guest_user_id(guest_id) if config.GUEST_ASK_ENABLED else None
    if guest:
        admitted, wait, which = _guests.check(guest, client_ip or "unknown")
        if not admitted:
            raise HTTPException(status_code=429,
                                detail=guest_access.REFUSALS[which],
                                headers={"Retry-After": str(wait)})
        return guest

    if config.AUTH_REQUIRED:
        raise HTTPException(status_code=401, detail="sign in to ask a question")
    return (claimed_user_id or "").strip() or None


def _require_caller(authorization: str | None) -> str:
    user_id = auth.read_token(_bearer(authorization))
    if not user_id:
        raise HTTPException(status_code=401, detail="sign in first")
    return user_id


def _is_bridge(bridge_token: str | None) -> bool:
    return bool(
        config.BRIDGE_TOKEN
        and bridge_token
        and secrets.compare_digest(bridge_token, config.BRIDGE_TOKEN)
    )


def _require_bridge(bridge_token: str | None, what: str) -> None:
    """Operational endpoints the SMS bridge calls, and nobody else should.

    When BRIDGE_TOKEN is not configured these stay open and say so, rather than
    closing. The bridge and the backend are deployed separately: closing them on
    an unset variable would mean a deploy that silently stops answering a real
    farmer's SMS, which is a worse outcome than an endpoint that is briefly
    reachable. /health reports which of the two states this is in.
    """
    if not config.BRIDGE_TOKEN:
        print(f"BRIDGE_TOKEN not set: {what} is reachable without proof. "
              "Set it on the backend and the SMS bridge to close it.")
        return
    if not _is_bridge(bridge_token):
        raise HTTPException(status_code=401, detail="not authorised")


# --- Sign-in --------------------------------------------------------------

class PhoneRequest(BaseModel):
    phone: str


class VerifyRequest(BaseModel):
    phone: str
    code: str
    # The browser's guest id, if the farmer asked questions before signing in.
    # Those questions are moved onto their number, because the screen that
    # asked them to sign in promised their questions would stay saved.
    guest_id: Optional[str] = None


@app.post("/auth/request-code")
def request_code(request: PhoneRequest):
    """Send a one-time code to a phone number.

    Deliberately answers the same way whether or not the number is already
    known. Telling an anonymous caller "no account here" turns this endpoint
    into a way of asking which of a list of numbers uses AnnaData.
    """
    phone = auth.normalise_phone(request.phone)
    if not phone:
        raise HTTPException(status_code=400,
                            detail="enter a 10-digit Indian mobile number")

    issued = auth.issue_code(phone)
    if not issued.ok:
        # 429 for a cooldown, because that is what it is, and the browser can
        # show a countdown rather than a generic failure.
        raise HTTPException(status_code=429 if issued.retry_after else 503,
                            detail=issued.reason or "could not send a code",
                            headers={"Retry-After": str(issued.retry_after)}
                                    if issued.retry_after else None)

    if not sms_out.send_code(phone, issued.code):
        raise HTTPException(status_code=502,
                            detail="could not send the code just now; try again")

    return {"sent": True, "phone": auth.mask_phone(phone),
            "expires_in": config.OTP_TTL, "transport": sms_out.transport()}


@app.post("/auth/verify")
def verify_code(request: VerifyRequest):
    """Exchange a correct code for a token."""
    phone = auth.normalise_phone(request.phone)
    if not phone:
        raise HTTPException(status_code=400, detail="enter a valid mobile number")

    ok, reason = auth.check_code(phone, request.code)
    if not ok:
        raise HTTPException(status_code=401, detail=reason or "that code is wrong")
    return _signed_in(phone, request.guest_id)


class WidgetVerifyRequest(BaseModel):
    access_token: str
    guest_id: Optional[str] = None


@app.post("/auth/verify-widget")
def verify_widget(request: WidgetVerifyRequest):
    """Sign in with the access token MSG91's widget gave the browser.

    The number signed in is the one MSG91 says it verified (msg91.py), not one
    the browser names.
    """
    if not msg91.enabled():
        raise HTTPException(status_code=503, detail="sign-in by MSG91 is not set up")
    phone, reason = msg91.verified_phone(request.access_token)
    if not phone:
        raise HTTPException(status_code=401, detail=reason)
    return _signed_in(phone, request.guest_id)


def _signed_in(phone: str, guest_id: Optional[str]) -> dict:
    """What every way of proving a number ends in: the account, the guest's
    questions moved onto it, and a token."""
    version = farmer_account.ensure(phone, channel="web")

    # Before reading the account, so a crop the guest mentioned is already in
    # the profile when the farm-details screen asks what they grow.
    claimed = 0
    guest = guest_access.guest_user_id(guest_id)
    if guest:
        claimed = profile_store.claim_guest(guest, phone)

    account = farmer_account.account(phone) or {}
    return {
        "token": auth.issue_token(phone, version),
        "user": account,
        "claimed_messages": claimed,
        # The browser uses this to decide between the onboarding screen and the
        # chat. Onboarding is skippable, so this can stay true indefinitely.
        "needs_onboarding": not account.get("onboarded_at"),
    }


@app.get("/auth/me")
def whoami(authorization: Optional[str] = Header(None)):
    user_id = _require_caller(authorization)
    account = farmer_account.account(user_id)
    if account is None:
        raise HTTPException(status_code=404, detail="no account")
    return {"user": account, "needs_onboarding": not account.get("onboarded_at")}


@app.post("/auth/signout")
def signout(authorization: Optional[str] = Header(None)):
    """Invalidate every token this farmer holds, not only this browser's."""
    user_id = _require_caller(authorization)
    return {"signed_out": farmer_account.sign_out_everywhere(user_id)}


# --- The farmer's own record ---------------------------------------------

class OnboardingRequest(BaseModel):
    name: Optional[str] = None
    state: Optional[str] = None
    district: Optional[str] = None
    village: Optional[str] = None
    language: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    crops: Optional[List[str]] = None
    # What the farmer typed, in the unit they typed it in. Converted to hectares
    # in units.py using their state, because a bigha is not a fixed area.
    area: Optional[float] = None
    area_unit: Optional[str] = None
    sown_on: Optional[str] = None
    # Which collective the farmer belongs to, if any: "fpo", "cooperative",
    # "shg" or "none", plus its name. The service is sold to these institutions
    # rather than to farmers, so this is how usage is tied to the organisation
    # paying for it.
    farmer_group: Optional[str] = None
    farmer_group_name: Optional[str] = None
    # How long the form took, in milliseconds, measured in the browser. Recorded
    # so "a one-minute onboarding" is a number somebody checked.
    took_ms: Optional[int] = None


@app.put("/profile")
def save_profile(request: OnboardingRequest,
                 authorization: Optional[str] = Header(None)):
    user_id = _require_caller(authorization)
    ok, note = farmer_account.save_onboarding(user_id, request.model_dump())
    if not ok:
        raise HTTPException(status_code=503, detail="could not save that just now")
    if request.took_ms:
        print(f"Onboarding completed in {request.took_ms / 1000:.1f}s by {auth.mask_phone(user_id)}")
    return {"saved": True, "note": note, "user": farmer_account.account(user_id)}


@app.get("/profile")
def read_profile(authorization: Optional[str] = Header(None)):
    user_id = _require_caller(authorization)
    account = farmer_account.account(user_id)
    if account is None:
        raise HTTPException(status_code=404, detail="no account")
    return account


@app.get("/history")
def read_history(limit: int = 50, authorization: Optional[str] = Header(None)):
    """This farmer's past conversation. Their own, and only their own."""
    user_id = _require_caller(authorization)
    return {"messages": farmer_account.history(user_id, limit)}


def _peer(http: Request) -> str | None:
    return http.client.host if http.client else None


class SpeakRequest(BaseModel):
    text: str
    # The language the answer is in, as the answer told the browser. Gemini
    # detects it from the text; this is kept for the log and for later use.
    lang: Optional[str] = None


@app.post("/speak")
def speak_endpoint(request: SpeakRequest,
                   http: Request,
                   authorization: Optional[str] = Header(None),
                   x_bridge_token: Optional[str] = Header(None),
                   x_guest_id: Optional[str] = Header(None),
                   x_forwarded_for: Optional[str] = Header(None)):
    """One piece of an answer, spoken. WAV bytes, or 503 to fall back on.

    Spends model quota on every call, so it is guarded exactly as /agent is:
    the bridge, a signed-in farmer, or a guest within the speaking limits.
    """
    _may_speak(http, authorization, x_bridge_token, x_guest_id, x_forwarded_for)
    try:
        audio = tts.speak(request.text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except tts.SpeechUnavailable:
        raise HTTPException(status_code=503, detail="speech is unavailable just now")
    return Response(content=audio, media_type="audio/wav",
                    headers={"Cache-Control": "no-store"})


@app.post("/speak/stream")
def speak_stream_endpoint(request: SpeakRequest,
                          http: Request,
                          authorization: Optional[str] = Header(None),
                          x_bridge_token: Optional[str] = Header(None),
                          x_guest_id: Optional[str] = Header(None),
                          x_forwarded_for: Optional[str] = Header(None)):
    """The same piece, streamed as raw 16-bit mono PCM while it is made.

    Speech starts when the first chunk arrives rather than when the whole
    piece is finished. The sample rate is in X-Sample-Rate, because raw PCM
    has no header to carry it.
    """
    _may_speak(http, authorization, x_bridge_token, x_guest_id, x_forwarded_for)
    try:
        rate, chunks = tts.stream(request.text)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except tts.SpeechUnavailable:
        raise HTTPException(status_code=503, detail="speech is unavailable just now")
    return StreamingResponse(chunks, media_type="audio/l16",
                             headers={"X-Sample-Rate": str(rate), "Cache-Control": "no-store"})


def _may_speak(http, authorization, x_bridge_token, x_guest_id, x_forwarded_for):
    """The bridge, a signed-in farmer, or a guest within the speaking limits."""
    if not (_is_bridge(x_bridge_token) or auth.read_token(_bearer(authorization))):
        guest = guest_access.guest_user_id(x_guest_id) if config.GUEST_ASK_ENABLED else None
        if guest:
            ip = guest_access.client_ip(x_forwarded_for, _peer(http))
            admitted, wait, _ = _speakers.check(guest, ip)
            if not admitted:
                raise HTTPException(status_code=429, detail="too much speech just now",
                                    headers={"Retry-After": str(wait)})
        elif config.AUTH_REQUIRED:
            raise HTTPException(status_code=401, detail="sign in to hear answers")


@app.post("/agent")
def run_agent_endpoint(request: QueryRequest,
                       http: Request,
                       authorization: Optional[str] = Header(None),
                       x_bridge_token: Optional[str] = Header(None),
                       x_guest_id: Optional[str] = Header(None),
                       x_forwarded_for: Optional[str] = Header(None)):
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    return _answer(
        request.query,
        user_id=_caller(authorization, x_bridge_token, request.user_id,
                        guest_id=x_guest_id,
                        client_ip=guest_access.client_ip(x_forwarded_for, _peer(http))),
        channel=request.channel or "web",
        latitude=request.latitude,
        longitude=request.longitude,
        history=request.history,
        message_id=request.message_id,
        chat_id=request.chat_id,
        request_id=request.request_id,
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
    http: Request,
    audio: Optional[UploadFile] = File(None, description="Voice note"),
    image: Optional[UploadFile] = File(None, description="Photo of the crop"),
    query: str = Form(""),
    latitude: Optional[str] = Form(None),
    longitude: Optional[str] = Form(None),
    history: Optional[str] = Form(None),
    channel: str = Form("web"),
    user_id: Optional[str] = Form(None),
    message_id: Optional[str] = Form(None),
    chat_id: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None),
    x_bridge_token: Optional[str] = Header(None),
    x_guest_id: Optional[str] = Header(None),
    x_forwarded_for: Optional[str] = Header(None),
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
    # Before a single byte is read. This endpoint takes arbitrary audio and
    # image uploads into memory on a 1 GiB container and then spends the media
    # model's daily quota; deciding who is calling after accepting the upload
    # would leave both of those open to anyone who found the URL.
    caller = _caller(authorization, x_bridge_token, user_id,
                     guest_id=x_guest_id,
                     client_ip=guest_access.client_ip(
                         x_forwarded_for, _peer(http)))

    audio_bytes = await audio.read() if audio is not None else None
    image_bytes = await image.read() if image is not None else None

    too_big = config.MAX_UPLOAD_BYTES
    for label, blob in (("audio", audio_bytes), ("image", image_bytes)):
        if blob is not None and len(blob) > too_big:
            raise HTTPException(
                status_code=413,
                detail=f"that {label} is larger than {too_big // (1024 * 1024)} MB",
            )

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
        user_id=caller,
        channel=channel or "web",
        latitude=_to_float(latitude),
        longitude=_to_float(longitude),
        history=_parse_history(history),
        message_id=message_id,
        vision=vision,
        chat_id=chat_id,
    )

    # Echoed back so the browser can show the farmer what was heard and what was
    # seen. A transcript they can read is also how they catch a misheard word.
    response["transcript"] = transcript
    response["vision"] = vision
    response["query_used"] = spoken
    return response


def _stream_events(work):
    """Run `work(emit)` on a thread and stream what it emits, one JSON per line.

    Events: {"type": "heard"} once a voice note is transcribed, {"type": "text"}
    for each checked sentence of the answer, then {"type": "done", ...} carrying
    exactly what /agent would have returned - the authoritative answer, after
    every guard - or {"type": "error"} with the status /agent would have sent.
    Who may ask is decided before this starts, so a refusal is still a real
    HTTP status rather than an event.
    """
    events: "queue.Queue[str | None]" = queue.Queue()

    def emit(event):
        events.put(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def run():
        try:
            emit({"type": "done", **work(emit)})
        except HTTPException as e:
            emit({"type": "error", "status": e.status_code, "detail": e.detail})
        except Exception as e:  # noqa: BLE001
            print(f"Streamed answer failed: {e}")
            emit({"type": "error", "status": 502, "detail": f"Agent failed: {e}"})
        finally:
            events.put(None)

    threading.Thread(target=run, daemon=True).start()

    def lines():
        while True:
            item = events.get()
            if item is None:
                return
            yield item

    return StreamingResponse(lines(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.post("/agent/stream")
def run_agent_stream(request: QueryRequest,
                     http: Request,
                     authorization: Optional[str] = Header(None),
                     x_bridge_token: Optional[str] = Header(None),
                     x_guest_id: Optional[str] = Header(None),
                     x_forwarded_for: Optional[str] = Header(None)):
    """/agent, with the answer sent a sentence at a time as it is written."""
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")
    caller = _caller(authorization, x_bridge_token, request.user_id,
                     guest_id=x_guest_id,
                     client_ip=guest_access.client_ip(x_forwarded_for, _peer(http)))

    def work(emit):
        return _answer(
            request.query, user_id=caller, channel=request.channel or "web",
            latitude=request.latitude, longitude=request.longitude,
            history=request.history, message_id=request.message_id, chat_id=request.chat_id,
            on_text=lambda text: emit({"type": "text", "text": text}),
        )

    return _stream_events(work)


@app.post("/agent/media/stream")
async def run_agent_media_stream(
    http: Request,
    audio: Optional[UploadFile] = File(None, description="Voice note"),
    image: Optional[UploadFile] = File(None, description="Photo of the crop"),
    query: str = Form(""),
    latitude: Optional[str] = Form(None),
    longitude: Optional[str] = Form(None),
    history: Optional[str] = Form(None),
    channel: str = Form("web"),
    user_id: Optional[str] = Form(None),
    message_id: Optional[str] = Form(None),
    chat_id: Optional[str] = Form(None),
    authorization: Optional[str] = Header(None),
    x_bridge_token: Optional[str] = Header(None),
    x_guest_id: Optional[str] = Header(None),
    x_forwarded_for: Optional[str] = Header(None),
):
    """/agent/media, streamed: what was heard first, then the answer as written.

    Voice mode's endpoint. Telling the farmer what was heard as soon as it is
    known, and starting to speak the first sentence while the rest is written,
    is most of the difference between a pause and a conversation.
    """
    caller = _caller(authorization, x_bridge_token, user_id,
                     guest_id=x_guest_id,
                     client_ip=guest_access.client_ip(x_forwarded_for, _peer(http)))
    audio_bytes = await audio.read() if audio is not None else None
    image_bytes = await image.read() if image is not None else None
    too_big = config.MAX_UPLOAD_BYTES
    for label, blob in (("audio", audio_bytes), ("image", image_bytes)):
        if blob is not None and len(blob) > too_big:
            raise HTTPException(status_code=413,
                                detail=f"that {label} is larger than {too_big // (1024 * 1024)} MB")
    typed = (query or "").strip()
    if not audio_bytes and not image_bytes and not typed:
        raise HTTPException(status_code=400, detail="send text, an image or an audio file")
    names = {
        "audio_filename": audio.filename if audio else None,
        "audio_content_type": audio.content_type if audio else None,
        "image_filename": image.filename if image else None,
    }

    def work(emit):
        try:
            understood = asyncio.run(understand_media(
                audio_bytes=audio_bytes, image_bytes=image_bytes, **names))
        except Exception as e:  # noqa: BLE001
            print(f"Media understanding failed: {e}")
            raise HTTPException(status_code=502, detail=f"Could not read the media: {e}")
        transcript, vision = understood["transcript"], understood["vision"]
        emit({"type": "heard", "transcript": transcript, "vision": vision})
        spoken = " ".join(part for part in (transcript, typed) if part).strip()
        if not spoken:
            spoken = "What is wrong with this crop, and what should I do about it?"
        result = _answer(
            spoken, user_id=caller, channel=channel or "web",
            latitude=_to_float(latitude), longitude=_to_float(longitude),
            history=_parse_history(history), message_id=message_id, vision=vision, chat_id=chat_id,
            on_text=lambda text: emit({"type": "text", "text": text}),
        )
        result.update({"transcript": transcript, "vision": vision, "query_used": spoken})
        return result

    return _stream_events(work)


class UserRequest(BaseModel):
    """Anything addressed at a single farmer by their identifier."""
    user_id: str


class RatingRequest(BaseModel):
    user_id: str
    message: str
    session_id: Optional[int] = None


@app.post("/feedback/rating")
def record_rating(request: RatingRequest,
                  x_bridge_token: Optional[str] = Header(None)):
    """Record a farmer's rating, if their reply contains one.

    Returns whether it was a rating at all, so the caller can fall back to
    answering the message as an ordinary question when it was not.
    """
    _require_bridge(x_bridge_token, "/feedback/rating")
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


class AnswerRating(BaseModel):
    up: bool
    # Optional: the farmer's own words on what was wrong. Kept short.
    note: Optional[str] = None


@app.post("/feedback/answer")
def rate_answer(request: AnswerRating,
                http: Request,
                authorization: Optional[str] = Header(None),
                x_guest_id: Optional[str] = Header(None),
                x_forwarded_for: Optional[str] = Header(None)):
    """A thumbs up or down on the answer just given, from the web.

    Recorded against the farmer's current session, with that session's
    features (tools, intent, dose status), exactly as an SMS rating is - so the
    question "which kinds of answer do farmers rate badly" has one answer
    across both channels.
    """
    user_id = auth.read_token(_bearer(authorization))
    if not user_id:
        guest = guest_access.guest_user_id(x_guest_id) if config.GUEST_ASK_ENABLED else None
        if not guest:
            raise HTTPException(status_code=401, detail="sign in to rate answers")
        admitted, wait, _ = _raters.check(guest, guest_access.client_ip(x_forwarded_for, _peer(http)))
        if not admitted:
            raise HTTPException(status_code=429, detail="too many ratings just now",
                                headers={"Retry-After": str(wait)})
        user_id = guest
    note = (request.note or "").strip()[:300]
    return {"stored": feedback.record_web(user_id, request.up, note)}


@app.get("/news")
def read_news(state: Optional[str] = None, latitude: Optional[float] = None,
              longitude: Optional[float] = None, authorization: Optional[str] = Header(None)):
    """Farming headlines for a state.

    The state the phone is in, when the browser sends its position - news is
    about where the farmer is now. Otherwise the state named, then the
    signed-in farmer's own. The position is turned into a state with the same
    cached lookup the answers use, and is not stored.

    Open to guests, because it spends no model quota and fetches only Google
    News searches built here from a known state name.
    """
    source = "chosen" if state else None
    if latitude is not None and longitude is not None:
        near = reverse(latitude, longitude).state
        if news.place(near) != "India":
            state, source = near, "location"
    if not state:
        user_id = auth.read_token(_bearer(authorization))
        if user_id:
            state = (farmer_account.account(user_id) or {}).get("state")
            source = "profile" if state else None
    result = news.headlines(state)
    known = result.get("place")
    return {**result, "state": "" if known == "India" else known,
            "from": source if known != "India" else None}


@app.get("/feedback/due")
def feedback_due(x_bridge_token: Optional[str] = Header(None)):
    """Farmers whose conversation has ended and who are due to be asked.

    Called on a schedule by the SMS bridge; kept as a query rather than a push
    so the backend never needs to send anything itself.
    """
    _require_bridge(x_bridge_token, "/feedback/due")
    return {"due": feedback.due_for_feedback()}


@app.post("/feedback/asked")
def feedback_asked(request: UserRequest,
                   x_bridge_token: Optional[str] = Header(None)):
    """Record that a farmer has been asked, so they are not asked again."""
    _require_bridge(x_bridge_token, "/feedback/asked")
    feedback.mark_asked((request.user_id or "").strip())
    return {"ok": True}


@app.get("/feedback/summary")
def feedback_summary(x_bridge_token: Optional[str] = Header(None)):
    """Ratings so far, and which kinds of question score worst."""
    _require_bridge(x_bridge_token, "/feedback/summary")
    return feedback.summary()


@app.post("/forget")
def forget(request: UserRequest,
           authorization: Optional[str] = Header(None),
           x_bridge_token: Optional[str] = Header(None)):
    """Erase a farmer's profile and message history. Backs the STOP keyword.

    This took a phone number and erased that farmer, with nothing to prove the
    caller was them - so anyone who knew a number could delete a stranger's
    profile and their whole conversation. Of everything that was open, this was
    the one that destroyed data rather than exposing it.

    Two callers are legitimate: the SMS bridge relaying STOP, because the network
    told it who sent that message; and a farmer erasing themselves from the web
    app, who may only ever name their own id.
    """
    claimed = (request.user_id or "").strip()

    if _is_bridge(x_bridge_token):
        user_id = claimed
    else:
        signed_in = auth.read_token(_bearer(authorization))
        if signed_in and (not claimed or claimed == signed_in):
            user_id = signed_in
        elif not config.BRIDGE_TOKEN and not config.AUTH_REQUIRED:
            # The pre-auth behaviour, kept only while neither is configured so a
            # half-migrated deployment does not lose the STOP keyword.
            print("/forget accepted an unproven caller: set BRIDGE_TOKEN.")
            user_id = claimed
        else:
            raise HTTPException(status_code=401, detail="not authorised")

    if not user_id:
        raise HTTPException(status_code=400, detail="user_id must not be empty")
    return {"erased": profile_store.forget(user_id)}


@app.post("/api/chat/describe")
async def chat_describe(
    audio: Optional[UploadFile] = File(None, description="Optional audio file"),
    image: Optional[UploadFile] = File(None, description="Optional image file"),
    authorization: Optional[str] = Header(None),
):
    # Superseded by /agent/media, which the web app uses instead. Kept for any
    # caller still on it, but no longer a way for a stranger to spend the media
    # model's daily quota. Decided before the upload is read.
    _require_caller(authorization)
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
