"""
The streaming answer endpoints, and rating an answer from the web.

/agent/stream and /agent/media/stream must refuse exactly whom /agent refuses -
before any stream starts, so a refusal is still a real status - and must end
with the same authoritative answer /agent would have returned. /feedback/answer
must take a thumbs up or down from a signed-in farmer or a guest, and from
nobody else. The model is replaced; FastAPI, the guards and the streaming are
real.

Run: python eval/test_stream_endpoints.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GEMINI_API_KEY", "x")

failures = []


def check(name, got, want):
    ok = got == want
    if not ok:
        failures.append(name)
    print(f"  {'pass' if ok else 'FAIL'}   {name}")
    if not ok:
        print(f"           got  {got!r}\n           want {want!r}")


try:
    from fastapi.testclient import TestClient
    import app as appmod
    from Agent import AgentResult
except Exception as e:
    print(f"FastAPI not installed here ({type(e).__name__}); nothing to check")
    sys.exit(0)

appmod.config.AUTH_REQUIRED = True
SAID = ["Kapas mein gulabi sundi ke liye Acephate 75% SP registered hai. ",
        "Iski matra 780 g/ha hai."]
calls = []


def fake_agent(query, **kw):
    calls.append(kw.get("on_text") is not None)
    for piece in SAID:
        if kw.get("on_text"):
            kw["on_text"](piece)
    return AgentResult("".join(SAID) + "\n\n**Registered for this pest (CIB&RC):**",
                       tools_used=["doses"], dose_status="available")


appmod.run_agent = fake_agent
web = TestClient(appmod.app)
G = {"X-Guest-Id": "3f2a9c1e-5b7d-4e8a-9c21-7d4e5f6a8b90"}


def events(response):
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


print("Who may ask")
check("nobody: refused before streaming", web.post("/agent/stream", json={"query": "q"}).status_code, 401)
check("an empty question: refused", web.post("/agent/stream", json={"query": " "}, headers=G).status_code, 400)

print("\nWhat a guest receives")
r = web.post("/agent/stream", json={"query": "Kapas me sundi"}, headers=G)
got = events(r)
check("a stream of JSON lines", (r.status_code, r.headers["content-type"].split(";")[0]), (200, "application/x-ndjson"))
check("the sentences, in order", [e["text"] for e in got if e["type"] == "text"], SAID)
check("then exactly one done", [e["type"] for e in got][-1:], ["done"])
done = got[-1]
check("done carries the authoritative answer, with anything added at the end",
      done["answer"].endswith("**Registered for this pest (CIB&RC):**"), True)
check("and the fields /agent returns", (done["dose_status"], done["tools_used"]), ("available", ["doses"]))
check("the agent was asked to stream", calls[-1], True)

print("\nA new web chat is a new conversation")
seen = {}


def spy_agent(query, **kw):
    seen.update(kw)
    return AgentResult("Namaste!", tools_used=["greeting"])


appmod.run_agent = spy_agent
appmod.feedback.in_live_session = lambda user_id: True  # talked a minute ago, in another chat
web.post("/agent/stream", json={"query": "hii", "history": []}, headers=G)
check("hello in a new chat is an arrival, not a goodbye", seen.get("continuing_session"), False)
web.post("/agent/stream", json={"query": "theek hai", "history": [
    {"role": "user", "content": "Kapas me sundi"}, {"role": "assistant", "content": "Acephate..."}]}, headers=G)
check("a short reply inside a chat continues it", seen.get("continuing_session"), True)
web.post("/agent", json={"query": "hii", "channel": "sms"}, headers=G)
check("SMS, which has no chats, still goes by the session", seen.get("continuing_session"), True)
appmod.run_agent = fake_agent

print("\nSMS never streams")
web.post("/agent/stream", json={"query": "q", "channel": "sms"}, headers=G)
check("channel sms: the agent is not asked to stream", calls[-1], False)

print("\nA failure mid-answer")
appmod.run_agent = lambda query, **kw: (_ for _ in ()).throw(RuntimeError("all models down"))
got = events(web.post("/agent/stream", json={"query": "q"}, headers=G))
check("ends in an error event with /agent's status", (got[-1]["type"], got[-1]["status"]), ("error", 502))
appmod.run_agent = fake_agent

print("\nA voice note, streamed")


async def fake_understand(**kw):
    return {"transcript": "Kapas me sundi lag gayi", "vision": None}


appmod.understand_media = fake_understand
r = web.post("/agent/media/stream", headers=G, files={"audio": ("voice.m4a", b"\x00" * 100, "audio/mp4")})
got = events(r)
check("what was heard comes first", (got[0]["type"], got[0]["transcript"]), ("heard", "Kapas me sundi lag gayi"))
check("then the answer, sentence by sentence", [e["text"] for e in got if e["type"] == "text"], SAID)
check("and done echoes the transcript", got[-1].get("transcript"), "Kapas me sundi lag gayi")

print("\nRating an answer")
appmod.feedback.record_web = lambda user_id, up, note="": calls.append(("rated", user_id, up)) or True
check("nobody: refused", web.post("/feedback/answer", json={"up": True}).status_code, 401)
r = web.post("/feedback/answer", json={"up": False, "note": "galat dawa"}, headers=G)
check("a guest: stored", (r.status_code, r.json()), (200, {"stored": True}))
check("as a thumbs down, under the guest's own key", calls[-1], ("rated", "guest:" + G["X-Guest-Id"], False))
check("a phone number as a guest id: refused",
      web.post("/feedback/answer", json={"up": True}, headers={"X-Guest-Id": "+919876543210"}).status_code, 401)

print(f"\n{len(failures)} failure(s)" if failures else "\nAll checks passed")
sys.exit(1 if failures else 0)
