"""
Answers spoken by Gemini, instead of by whatever voice the phone happens to have.

The web app used the browser's own speech synthesis. On a budget Android that
is a robotic voice reading Hinglish in an English accent, and on many phones
there is no Bengali or Punjabi voice at all - the answer simply could not be
heard. Gemini's TTS models speak Hindi, Bangla and Punjabi among 100+ languages,
detect the language from the text, and sit behind the same GEMINI_API_KEY the
rest of the service already uses.

ONE SHORT PIECE AT A TIME. The web app splits an answer into sentence-sized
pieces and asks for them in order, playing one while the next is made. A whole
answer synthesised in one call would make the farmer wait for all of it before
hearing any of it; a piece of a sentence or two starts in a second or two. The
same shape is what a streaming voice connection will need later.

WHAT IS SENT. Only the answer's text, after markdown is stripped - never the
farmer's question, number or location. On the free tier Google may use what is
sent to improve its products, which is acceptable for text the service wrote
itself and would not be for the farmer's own words.

The output is 16-bit mono PCM from the model, wrapped here in a WAV header so
any browser can decode it without knowing the sample rate in advance.
"""
from __future__ import annotations

import io
import re
import threading
import wave
from collections import OrderedDict

import config

_lock = threading.Lock()
_cache: "OrderedDict[tuple, bytes]" = OrderedDict()
_CACHE_SIZE = 64


class SpeechUnavailable(Exception):
    """No TTS model could speak this. The caller falls back to the phone's voice."""


def clean(text: str | None) -> str:
    """Markdown out, whitespace collapsed - what is said, not how it was written."""
    value = str(text or "")
    value = re.sub(r"```.*?```", " ", value, flags=re.S)
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", value)
    value = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"^\s{0,3}#{1,6}\s*", "", value, flags=re.M)
    value = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", value, flags=re.M)
    value = re.sub(r"^\s*>\s?", "", value, flags=re.M)
    value = re.sub(r"^\s*\|.*\|\s*$", " ", value, flags=re.M)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    value = re.sub(r"(?<!\w)[*_](?=\S)|(?<=\S)[*_](?!\w)", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _rate(mime: str | None) -> int:
    """'audio/L16;codec=pcm;rate=24000' -> 24000. The documented default otherwise."""
    match = re.search(r"rate=(\d+)", mime or "")
    return int(match.group(1)) if match else 24000


def wav(pcm: bytes, rate: int = 24000) -> bytes:
    """Raw 16-bit little-endian mono PCM, with the header a browser needs."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(pcm)
    return buffer.getvalue()


def _client():
    # Imported late so that importing this module - in a test, say - does not
    # require a key or build the whole model chain.
    from utils import client
    return client


def _prompt(text: str) -> str:
    style = (config.TTS_STYLE or "").strip()
    return f"{style} {text}" if style else text


def _config():
    from google.genai import types

    return types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=config.TTS_VOICE)
            )
        ),
        http_options=types.HttpOptions(timeout=int(config.TTS_TIMEOUT * 1000)),
    )


def _audio_parts(response):
    """(bytes, mime) for every audio part in a response or a streamed chunk."""
    for candidate in getattr(response, "candidates", None) or []:
        for part in (candidate.content.parts if candidate.content else None) or []:
            blob = getattr(part, "inline_data", None)
            if blob is not None and blob.data:
                yield blob.data, blob.mime_type


def _synthesise(client, model: str, text: str) -> tuple[bytes, str | None]:
    response = client.models.generate_content(model=model, contents=_prompt(text), config=_config())
    for data, mime in _audio_parts(response):
        return data, mime
    raise SpeechUnavailable(f"{model} returned no audio")


def stream(text: str | None, client=None):
    """Raw 16-bit mono PCM for one piece, yielded as Gemini produces it.

    Returns (sample_rate, iterator). The first chunk is fetched before this
    returns, so a model that cannot speak is found out - and the next one tried
    - before the response has started and can no longer change its status.
    A model that fails after it has begun simply ends the piece early.
    """
    said = clean(text)
    if not said:
        raise ValueError("nothing to say")
    if len(said) > config.TTS_MAX_CHARS:
        raise ValueError(f"at most {config.TTS_MAX_CHARS} characters at a time")

    client = client or _client()
    failures = []
    for model in config.TTS_MODELS:
        try:
            chunks = client.models.generate_content_stream(
                model=model, contents=_prompt(said), config=_config())
            iterator = iter(chunks)
            first = None
            for chunk in iterator:
                for data, mime in _audio_parts(chunk):
                    first = (data, mime)
                    break
                if first:
                    break
            if not first:
                raise SpeechUnavailable(f"{model} streamed no audio")

            def rest(first=first, iterator=iterator, model=model):
                yield first[0]
                try:
                    for chunk in iterator:
                        for data, _ in _audio_parts(chunk):
                            yield data
                except Exception as e:  # noqa: BLE001
                    print(f"Speech stream from {model} ended early: {type(e).__name__}: {str(e)[:120]}")

            return _rate(first[1]), rest()
        except Exception as e:  # noqa: BLE001
            failures.append(f"{model}: {type(e).__name__}: {str(e)[:120]}")
    print("Streamed speech failed on every model: " + " | ".join(failures))
    raise SpeechUnavailable("no speech model could say this")


def speak(text: str | None, client=None) -> bytes:
    """WAV audio for one piece of an answer. Raises SpeechUnavailable on failure.

    Models are tried in order, so a quota or availability problem with the
    first does not silence the answer.
    """
    said = clean(text)
    if not said:
        raise ValueError("nothing to say")
    if len(said) > config.TTS_MAX_CHARS:
        raise ValueError(f"at most {config.TTS_MAX_CHARS} characters at a time")

    key = (config.TTS_VOICE, config.TTS_STYLE, said)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]

    client = client or _client()
    failures = []
    for model in config.TTS_MODELS:
        try:
            pcm, mime = _synthesise(client, model, said)
            audio = pcm if pcm[:4] == b"RIFF" else wav(pcm, _rate(mime))
            with _lock:
                _cache[key] = audio
                while len(_cache) > _CACHE_SIZE:
                    _cache.popitem(last=False)
            return audio
        except Exception as e:  # noqa: BLE001 - every failure means "try the next"
            failures.append(f"{model}: {type(e).__name__}: {str(e)[:120]}")
    print("Speech failed on every model: " + " | ".join(failures))
    raise SpeechUnavailable("no speech model could say this")
