"""
Spoken answers: what reaches Gemini, what comes back, and who may ask.

/speak spends model quota on every call, so it is guarded like /agent, and a
silent failure here is a farmer who cannot hear their answer. Checked with a
fake Gemini client and a fake clock-free limiter - no network, no model calls.

Run: python eval/test_speak.py
"""
import io
import os
import sys
import wave
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import tts

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


class FakeModels:
    def __init__(self, fail=()):
        self.fail = set(fail)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append((model, contents, config))
        if model in self.fail:
            raise RuntimeError("429 quota")
        pcm = b"\x01\x00" * 2400  # 0.1 s of near-silence at 24 kHz
        part = NS(inline_data=NS(data=pcm, mime_type="audio/L16;codec=pcm;rate=24000"))
        return NS(candidates=[NS(content=NS(parts=[part]))])


def fake(fail=()):
    return NS(models=FakeModels(fail))


print("What is said")
check("markdown is not read aloud",
      tts.clean("### Upchar\n*   **Propiconazole 25% EC:** 500 ml dava"),
      "Upchar Propiconazole 25% EC: 500 ml dava")
check("numbered steps lose their numbers", tts.clean("1. Paudhe ukhaadein\n2. Trap lagayein"),
      "Paudhe ukhaadein Trap lagayein")
check("Devanagari passes through", tts.clean("गेहूं में **पीला रतुआ**"), "गेहूं में पीला रतुआ")

print("\nWhat comes back")
tts._cache.clear()
client = fake()
audio = tts.speak("Gehu ki buwai November mein karein.", client=client)
with wave.open(io.BytesIO(audio)) as w:
    check("it is a WAV a browser can decode", (w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 24000))
    check("with all of the audio in it", w.getnframes(), 2400)
model, contents, cfg = client.models.calls[0]
check("the first model tried is the first configured", model, config.TTS_MODELS[0])
check("audio is what is asked for", cfg.response_modalities, ["AUDIO"])
check("in the configured voice", cfg.speech_config.voice_config.prebuilt_voice_config.voice_name, config.TTS_VOICE)
check("the text is sent after the style direction", contents.endswith("Gehu ki buwai November mein karein."), True)
check("the call has a time limit", cfg.http_options.timeout, int(config.TTS_TIMEOUT * 1000))

print("\nWhen a model fails")
tts._cache.clear()
client = fake(fail={config.TTS_MODELS[0]})
tts.speak("Ek aur sawaal.", client=client)
check("the next model is tried", [c[0] for c in client.models.calls], config.TTS_MODELS[:2])
tts._cache.clear()
try:
    tts.speak("Kuch bhi.", client=fake(fail=set(config.TTS_MODELS)))
    check("every model failing is reported", "no error", "SpeechUnavailable")
except tts.SpeechUnavailable:
    check("every model failing is reported", "SpeechUnavailable", "SpeechUnavailable")

print("\nCaching and limits")
tts._cache.clear()
client = fake()
tts.speak("Dobara suniye.", client=client)
tts.speak("Dobara suniye.", client=client)
check("Listen pressed twice costs one call", len(client.models.calls), 1)
for text, why in (("", "empty"), ("**  **", "only markdown"), ("a" * (config.TTS_MAX_CHARS + 1), "too long")):
    try:
        tts.speak(text, client=fake())
        check(f"{why} text is refused", "accepted", "refused")
    except ValueError:
        check(f"{why} text is refused", "refused", "refused")

print("\nWho may ask (the endpoint)")
os.environ.setdefault("GEMINI_API_KEY", "x")
try:
    from fastapi.testclient import TestClient
    import app as appmod
except Exception as e:  # FastAPI not installed where this runs
    print(f"  skip   endpoint checks ({type(e).__name__})")
else:
    appmod.tts.speak = lambda text: tts.wav(b"\x00\x00" * 10)
    appmod.config.AUTH_REQUIRED = True
    appmod._speakers = appmod.guest_access.GuestLimiter(per_guest=2, per_ip=100, daily_cap=100)
    web = TestClient(appmod.app)
    G = {"X-Guest-Id": "3f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b90"}
    check("nobody: refused", web.post("/speak", json={"text": "namaste"}).status_code, 401)
    r = web.post("/speak", json={"text": "namaste"}, headers=G)
    check("a guest: answered", r.status_code, 200)
    check("as audio/wav", r.headers.get("content-type"), "audio/wav")
    web.post("/speak", json={"text": "namaste"}, headers=G)
    check("a guest past the speaking limit: 429", web.post("/speak", json={"text": "namaste"}, headers=G).status_code, 429)
    check("a phone number as a guest id: refused",
          web.post("/speak", json={"text": "namaste"}, headers={"X-Guest-Id": "+919876543210"}).status_code, 401)
    appmod.tts.speak = lambda text: (_ for _ in ()).throw(tts.SpeechUnavailable("down"))
    check("speech down: 503, so the browser falls back",
          web.post("/speak", json={"text": "namaste"}, headers={"X-Guest-Id": "8f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b91"}).status_code, 503)

print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)
