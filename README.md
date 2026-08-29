# AnnaData — Deployment Runbook

AI agricultural advisory for Indian farmers, reachable over the **web** and over **plain SMS** (no smartphone or internet needed on the farmer's side).

```
                                  ┌──────────────────────────┐
  Farmer (web)  ──────────────▶   │  Frontend (React/CRA)    │
                                  │  AWS Amplify Hosting     │
                                  └────────────┬─────────────┘
                                               │ POST /agent
                                               ▼
  Farmer (SMS) ──▶ Android phone  ┌──────────────────────────┐
                   running SMS    │  Backend (FastAPI)       │
                   Gateway app    │  AWS App Runner          │
                        │         │                          │
                        │ webhook │  Gemini 3.6 Flash +      │
                        │ sms:    │  soil / weather / mandi /│
                        │ received│  schemes KB              │
                        ▼         └────────────▲─────────────┘
              ┌──────────────────┐             │ POST /agent
              │  SMS Bridge      │─────────────┘
              │  (Quart)         │
              │  AWS App Runner  │──▶ api.sms-gate.app ──▶ reply SMS
              └──────────────────┘
```

| Service | Directory | Runtime | Deploys to |
|---|---|---|---|
| Backend agent | `AnnaData-Backend-main` | Python 3.11+ / FastAPI | App Runner |
| SMS bridge | `AnnaData-SMS-main` | Python 3.11+ / Quart | App Runner |
| Web frontend | `AnnaData-Frontend-main` | Node 18+ / CRA | Amplify Hosting |

---

## 1. Credentials

**Only `GEMINI_API_KEY` is required.** Every other integration is optional: without it the corresponding tool reports itself unavailable, the agent routes around it, and the advisory still goes out. `GET /health` on the backend tells you exactly what is configured.

| Credential | Unlocks | Without it | Cost | Where |
|---|---|---|---|---|
| `GEMINI_API_KEY` | **Everything** | Service refuses to start | Free tier is 20 req/day/model — see below | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| `GOV_API_KEY` | Mandi (market) prices | Advice omits prices | Free | [data.gov.in](https://data.gov.in/) → register → profile → API key |
| `LOCATION_API_KEY` | Place name → coordinates | Falls back to browser GPS only | Free tier, card required | [Google Maps Geocoding](https://console.cloud.google.com/apis/library/geocoding-backend.googleapis.com) |
| `EE_SERVICE_KEY` | Soil texture / pH / carbon | Advice omits soil | Free (non-commercial) | [Earth Engine](https://earthengine.google.com/) → service account JSON, as one line |
| AWS Bedrock (`KNOWLEDGE_BASE_ID`, `AWS_ACCESS_KEY`, `AWS_SECRET_KEY`) | Govt schemes & cold storage answers | Those questions get general answers | Pay per query | Bedrock console, `ap-south-1` |
| SMS Gateway `APP_USERNAME` / `PASSWORD` | SMS channel | Web only | Free | The Android app, Cloud Server section |

Weather needs no key — Open-Meteo is open access.

### Gemini quota — the binding constraint

The free tier allows **20 `generateContent` requests per day, per model**. One farmer question costs **2 calls** (parse + answer), so a free-tier key serves roughly **10 questions per day in total** before every reply becomes the fallback apology. That is fine for testing and unusable in the field.

**Enable billing on the Google Cloud project behind the key before going live.** Nothing in the code changes; the same key stops being rate-limited.

Quota is tracked per model, so switching `TEXT_MODEL` gives a fresh 20/day — useful for testing, not a fix.

### Model selection

`gemini-2.0-flash` and the `gemini-2.5-*` line are **no longer callable by new API keys** — the API returns 404 pointing at the 3.x line. Current defaults:

`TEXT_MODELS` is a comma-separated chain, **fastest first**. Each model is tried in order; a quota (429), overload (503) or missing-model (404) error fails over to the next.

| Setting | Default |
|---|---|
| `TEXT_MODELS` | `gemini-3.1-flash-lite,gemini-3.6-flash,gemini-3.5-flash-lite` |
| `MEDIA_MODEL` | `gemini-3.5-flash-lite` |

Measured end-to-end agent latency: **2.4s mean** on the current primary, versus ~23s on `gemini-3.6-flash`. Answers stayed correct and specific across Hinglish, Devanagari and English in testing.

Two things make failover fast. The retry budget is bound as a *call* kwarg — `langchain_google_genai` reads `max_retries` from call kwargs and otherwise silently defaults to 6 attempts with exponential backoff, which stalls ~60s on a dead model before the next is tried. Bound correctly, the same failover takes ~1s. And because free-tier quota is **per model**, the chain also multiplies usable daily capacity.

Note that `models.list` reports models the key **cannot** actually invoke. Verify with a real `generateContent` call before changing these.

**Suggested order:** Gemini first (gets the whole thing working), then `GOV_API_KEY` (free, high value for farmers), then the SMS gateway credentials. Earth Engine, Maps, and Bedrock are refinements.

---

## 2. Run locally

```bash
# --- Backend ---
cd AnnaData-Backend-main
python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                # add GEMINI_API_KEY
uvicorn app:app --reload --port 8000
curl http://127.0.0.1:8000/health                   # confirms what is configured

# --- Frontend ---
cd AnnaData-Frontend-main
npm install
cp .env.example .env                                # REACT_APP_API_URL=http://127.0.0.1:8000
npm start

# --- SMS bridge ---
cd AnnaData-SMS-main
python -m venv .venv && .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env                                # gateway creds + AI_ENDPOINT
uvicorn app:app --host 0.0.0.0 --port 5000
```

---

## 3. SMS setup (Cloud mode)

Cloud mode is the important change. The old setup needed the phone and the server on the same Wi-Fi plus a hand-started ngrok tunnel whose URL changed on every restart and had to be re-registered. In cloud mode the phone talks to `api.sms-gate.app` over mobile data from anywhere, and the bridge has a permanent App Runner URL.

1. Install [SMS Gateway for Android](https://github.com/capcom6/android-sms-gateway/releases) on a phone with an active SIM.
2. Grant `SEND_SMS`, `RECEIVE_SMS`, `READ_PHONE_STATE`.
3. Enable **Cloud Server** (not Local Server). Copy the username and password it shows.
4. Put those in the bridge's `APP_USERNAME` / `PASSWORD`, keep `SMS_MODE=cloud`.
5. Deploy the bridge (below), then set `PUBLIC_URL` to its App Runner URL.
6. Register the webhook, once:
   ```bash
   python webhook.py           # lists existing, registers if absent
   python webhook.py --list    # inspect only
   ```
7. Text the phone's number. A reply should arrive within ~10–30s.

Keep the phone charged, online, and excluded from battery optimisation — it is the actual SMS transmitter.

> **Note on cost and regulation:** each reply is a normal SMS from that SIM, billed by the mobile plan. This phone-as-gateway design deliberately avoids Indian A2P/DLT registration, which would otherwise require pre-approved templates and block free-form AI replies.

### Reply length and script

SMS billing depends on the alphabet. Latin text packs **153 characters per segment**; Devanagari, Gurmukhi, Telugu and Bengali force UCS-2 at **67 characters per segment** — so an identical-looking Hindi reply costs more than twice as much as an English one.

`MAX_SMS_SEGMENTS` (default `3`) caps *billed segments*, which is what actually controls cost across languages. `MAX_SMS_CHARS` remains a hard character ceiling. At the default, an Indic-script answer gets roughly 200 characters and a Latin one roughly 460; answers are trimmed at a sentence boundary, never mid-word.

---

## 4. Deploy to AWS

### Backend → App Runner

1. App Runner → **Create service** → Source: GitHub → the backend repo.
2. It reads `apprunner.yaml` automatically. No Docker needed.
3. Configuration → Environment variables → add `GEMINI_API_KEY` and any optional keys.
4. Health check path: `/health`.
5. Note the service URL.

### SMS bridge → App Runner

Same flow with the SMS repo. Set `APP_USERNAME`, `PASSWORD`, `AI_ENDPOINT` (backend URL + `/agent`), and `PUBLIC_URL` (this service's own URL, known after the first deploy — set it and redeploy). Health check `/health`.

### Frontend → Amplify Hosting

1. Amplify → Host web app → the frontend repo. It reads `amplify.yml`.
2. Environment variables → `REACT_APP_API_URL` = backend App Runner URL.
   CRA inlines env vars **at build time**, so changing this needs a redeploy, not a restart.
3. Add the SPA rewrite from `amplify-rewrites.json` (Rewrites and redirects).
4. Finally, set `FRONTEND_URL` on the **backend** to the Amplify URL so CORS allows it, and redeploy the backend.

`Dockerfile`s are included in both Python services if you prefer ECS/Fargate or container-based App Runner.

### Deploy order

Backend → SMS bridge → frontend → then set `FRONTEND_URL` on the backend and redeploy it.

---

## 5. Verifying a deploy

```bash
curl https://<backend>/health          # features map: which integrations are live
curl https://<sms-bridge>/health       # status "ok" or "degraded" + specific problems

curl -X POST https://<backend>/agent \
  -H "Content-Type: application/json" \
  -d "{\"query\":\"When should I sow wheat in Punjab?\"}"
```

Then send a real SMS to the gateway phone.

---

## 6. Known gaps

- **No authentication or rate limiting on `/agent`.** It is a public endpoint spending your Gemini and Bedrock budget. Add an API key or AWS WAF rate rule before publicising the URL.
- **Deduplication is in-memory**, so a bridge restart can allow one duplicate reply. Fine for a single instance; move to Redis/DynamoDB if you scale past one.
- **No conversation memory over SMS** — each message is answered standalone. The web app has history; SMS does not.
- **Two LLM calls per question.** Halving this would double free-tier capacity and cut latency, but needs the parse and answer steps merged.
- **CRA is unmaintained.** It builds fine today; a Vite migration is the eventual path.
