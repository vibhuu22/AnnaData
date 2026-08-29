import encoding_setup  # noqa: F401  (must be first)

from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config
import startup
from Agent import agent
from process_media import process_media

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
    """Warm up Earth Engine without letting a failure block the service."""
    startup.init_earth_engine()
    print(f"CORS origins: {_build_origins()}")
    print(f"Features: {config.feature_status()}")


class QueryRequest(BaseModel):
    query: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    history: Optional[List[dict]] = None
    # "sms" produces a short plain-text answer; "web" allows markdown.
    channel: Optional[str] = "web"


@app.get("/")
def root():
    return {"message": "AnnaData Agent API is running!"}


@app.get("/health")
def health():
    """Readiness plus which integrations are actually configured."""
    return {
        "status": "ok",
        "features": config.feature_status(),
        "earth_engine": startup.status(),
    }


@app.post("/agent")
def run_agent(request: QueryRequest):
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    try:
        result = agent(
            query=request.query,
            latitude=request.latitude,
            longitude=request.longitude,
            history=request.history,
            channel=request.channel or "web",
        )
        return {"answer": result}
    except Exception as e:
        # Previously this returned 200 with an {"error": ...} body, so callers
        # (the SMS bridge especially) treated failures as successful replies.
        print(f"Error in agent function: {e}")
        raise HTTPException(status_code=502, detail=f"Agent failed: {e}")


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
