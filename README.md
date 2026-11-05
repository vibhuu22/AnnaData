# AnnaData

An agricultural advisory service for Indian farmers that answers a question
about their own field — in their own language, over the channel they actually
have — and refuses to invent the numbers a farmer would act on.

Two things distinguish it from a chatbot with a farming prompt:

- **It reaches a farmer without a smartphone.** The main channel is plain SMS,
  delivered through an Android handset acting as a gateway. No app, no data
  connection, no literacy in English.
- **The figures that cost money are not generated.** Pesticide doses come out of
  the statutory CIB&RC register, support prices out of a loaded MSP table, market
  rates off data.gov.in, land-unit conversions out of a per-state table. Where
  there is nothing on file, the answer says so instead of producing a plausible
  number — and code, not a prompt, enforces that.

This file is the end-to-end overview: what exists, how a question flows through
it, what has been measured, and what has not. Two companions go deeper:

| Document | What it holds |
|---|---|
| `ENGINEERING_NOTES.md` | Why the system is shaped this way — decisions, failures, and the measurements behind them |
| `DEPLOY_CLOUD_RUN.md` | Moving off Render's free tier onto Cloud Run, and why |

---

## 1. Status at a glance

| | State |
|---|---|
| Channels live | Web (React), SMS (Android gateway), WhatsApp Cloud API |
| Sign-in | Phone number + one-time code, signed token; `/agent` and friends take the farmer from the token |
| Grounded doses | 2,456 registered pesticide uses, 314 crops, 825 products (6 CIB&RC PDFs, as on 31.03.2026) |
| Support prices | 20 commodities, 39 aliases |
| Retrieval corpus | 86 chunks across 5 scheme documents, with a tuned similarity floor |
| Photo diagnosis | Lesion bank over a controlled symptom vocabulary — built to abstain, not to classify |
| Voice | Recorded question in, spoken answer out, via the browser's own speech APIs |
| Memory | Postgres profile + message history, shared across channels by phone number |
| Evaluation | 38 machine-checkable cases in `eval/cases.yaml`, plus four deterministic test modules |
| Recurring infrastructure cost | **$0** — every tier in use is free; Gemini billing is the one thing worth paying for |
| Farmers using it | **One.** Everything below the level of "does it behave correctly" is unmeasured |

The honest summary: measurably faster, measurably cheaper and measurably more
grounded than it was — and its **agronomic quality remains unreviewed by anyone
qualified**. See section 12.

---

## 2. Architecture

```
                                      ┌────────────────────────────┐
  Farmer, smartphone  ───────────────▶│  Web app (React / CRA)     │
                                      │  sign-in · onboarding ·    │
                                      │  chat · voice · photo      │
                                      └──────────────┬─────────────┘
                                                     │ Bearer token
                                                     │ POST /agent, /agent/media
                                                     ▼
  Farmer, basic phone                 ┌────────────────────────────┐
        │  SMS                        │  Agent API (FastAPI)       │
        ▼                             │                            │
  Android handset ──webhook──▶ bridge─┼─── X-Bridge-Token ────────▶│
  (api.sms-gate.app)          (Quart) │                            │
        ▲                        │    │   refine → parse → plan →  │
        └──── reply SMS ─────────┘    │   gather → synthesise →    │
                                      │   guard                    │
  Farmer, WhatsApp ──▶ Meta Cloud ───▶│                            │
                      API (same bridge)└─────────────┬─────────────┘
                                                     │
        ┌────────────────┬──────────────┬────────────┼───────────┬──────────┐
        ▼                ▼              ▼            ▼           ▼          ▼
   Gemini 3.x      CIB&RC doses     MSP table   Mandi prices  Weather     Soil
   (text + media)  (Postgres)       (CSV)       data.gov.in   Open-Meteo  Earth
                                                              → MET.no    Engine
        ▼                ▼
   Lesion bank     Scheme documents
   (Postgres)      (pgvector, 768-d)

   Postgres also holds: farmer profiles, message history, ratings,
   one-time-code hashes.
```

Three deployable services, one repository:

| Service | Directory | Runtime | Role |
|---|---|---|---|
| Agent API | `AnnaData-Backend-main` | Python 3.12 / FastAPI | Everything above. The only service that talks to a model |
| SMS + WhatsApp bridge | `AnnaData-SMS-main` | Python 3.12 / Quart | Webhooks in, replies out, segment budgeting, opt-out, ratings |
| Web app | `AnnaData-Frontend-main` | Node 18+ / CRA + Tailwind | The smartphone channel |

`render.yaml` describes all three as one Blueprint.

---

## 3. Repository layout

```
AnnaData-Backend-main/
  app.py               FastAPI surface: auth, profile, /agent, /agent/media, feedback, /forget
  Agent.py             The pipeline — refine, parse, plan, gather, synthesise, guard
  auth.py              One-time codes, signed tokens, phone normalisation
  config.py            Every setting and feature flag; feature_status() backs /health
  planner.py           Intent → which tools to run. Plain data, no model call
  knowledge.py         Registered doses (structured) + document retrieval (pgvector)
  lesion_bank.py       Photo diagnosis by nearest labelled symptom reading
  output_guards.py     Strips price/scheme figures nothing retrieved supports
  units.py             Bigha → hectare, per state, refusing where the state is unknown
  msp.py               Minimum Support Prices, local and always answerable
  provenance.py        What the system can do and where an answer came from, from live state
  process_media.py     Voice transcription and structured reading of a photograph
  profile_store.py     The agent's memory — facts learned mid-conversation
  farmer_account.py    The farmer's account — what they typed on a form
  feedback.py          Rating schedule, parsing, and the features stored beside a score
  db.py                Postgres pool and schema. Entirely optional
  Mandi_Price_Tool.py  data.gov.in, with a circuit breaker
  weather_tool.py      Open-Meteo, cached by rounded coordinate, MET Norway fallback
  Soil_Tool.py         Earth Engine soil texture, pH, organic carbon
  Address_Convertor.py Place name → coordinates (Nominatim, or Google Maps if keyed)
  sms_out.py           Sends the sign-in code through the handset gateway
  data/                MSP CSV, CIB&RC extracts, scheme documents
  tools/               One-off loaders and measurement scripts
  eval/                The evaluation harness and the deterministic tests

AnnaData-SMS-main/
  app.py               Webhook handling, dedup, opt-out, rating capture, reply send
  sms_text.py          Markdown → plain text, segment counting, sentence-safe trimming
  whatsapp.py          WhatsApp Cloud API channel
  webhook.py           Register the gateway webhook, once
  config.py            Gateway mode, endpoints, segment budget, STOP words

AnnaData-Frontend-main/
  src/Context/AuthProvider.jsx   Identity: checking / signed out / needs onboarding
  src/Context/ContextProvider.js The conversation
  src/component/SignIn           Phone + code, with one-time-code autofill
  src/component/Onboarding       Four questions, one screen, every field optional
  src/component/Main             Chat, microphone, photo, suggestions
  src/component/Answer           The answer surface — doses and prices made unmissable
  src/component/Sources          Which real sources an answer was built from
  tailwind.config.js             The design system, with contrast ratios written in
```

---

## 4. How one question is answered

A farmer texts *"Kapas me sundi lag gayi hai, kya spray karu?"*

1. **The bridge receives it.** The gateway posts to `/incoming-sms`. The bridge
   deduplicates on `messageId`, checks for a STOP word and for a rating reply
   before treating it as a question, then calls `/agent` with `X-Bridge-Token` —
   which is what entitles it to name a `user_id` the backend will believe.
2. **The backend decides who is calling.** Bridge token, then signed token, then
   a browser's guest id (within guest limits), then nobody (401 when
   `AUTH_REQUIRED`). Identity is the phone number on every channel, so one
   farmer is one history.
3. **Profile and history are recalled.** District, crops, land area, recent
   turns. Coordinates come from the profile when the request has none, which is
   what gives SMS access to the location-aware tools.
4. **Refine and parse.** The question is resolved against the conversation, then
   one model call extracts crop, pest, state, location, intent and message kind
   together. Intent classification, message-kind classification and pest
   extraction all ride on that call, so richer routing costs **zero** extra calls.
5. **Plan.** `planner.py` maps intent to tools from a plain table. A pest
   question runs weather and the dose register; it does not fetch mandi prices
   for the whole state.
6. **Gather, concurrently.** Every selected tool that is configured runs in
   parallel. A missing key means one tool reports itself unavailable — never a
   failed answer.
7. **Synthesise.** One model call, given today's date and where it falls in the
   Indian cropping calendar, the script the farmer wrote in, the channel's
   length budget, and the retrieved data.
8. **Guard.** `output_guards.py` removes any sentence asserting a support price
   or scheme figure that nothing retrieved supports. Sentences that name the
   thing without a number survive, because "ask at the sugar mill" is useful and
   true.
9. **Reply.** The backend returns `answer`, `reply_language`, `tools_used`,
   `intent`, `message_type`, `dose_status`, `missing_slots` and `session_id`.
   The bridge flattens markdown, counts **billed segments** rather than
   characters, trims at a sentence boundary, and sends.
10. **Remember.** Whatever was learned goes back into the profile; both messages
    are logged against the session, which is what later makes a rating
    interpretable.

Three model calls per question, down from four. The tools are the latency, not
the model — see section 11.

A photograph or a voice note takes the same path through `/agent/media`, in one
round trip. The transcript becomes the farmer's question verbatim, in their own
script. What the photograph showed fills slots their words left empty — but the
crop is theirs to state, and a picture of one leaf does not get to correct them.

### The HTTP surface

| Endpoint | Who may call it |
|---|---|
| `POST /auth/request-code`, `POST /auth/verify` | Anyone. Answers identically whether or not the number is known. Verify takes an optional `guest_id` and moves that guest's questions onto the number |
| `GET /auth/me`, `POST /auth/signout` | A signed-in farmer |
| `GET`/`PUT /profile`, `GET /history` | A signed-in farmer, about themselves only |
| `POST /agent`, `POST /agent/media` | A signed-in farmer, the bridge with `BRIDGE_TOKEN`, or a guest sending `X-Guest-Id` (a v4 UUID) within the guest limits — 429 with `Retry-After` beyond them |
| `POST /forget` | The bridge relaying STOP, or a farmer naming their own id |
| `GET /feedback/due`, `POST /feedback/asked`, `POST /feedback/rating`, `GET /feedback/summary` | The bridge |
| `GET /health`, `GET /` | Anyone. No model calls, so it is safe to ping |

---

## 5. The refusals that make it usable

Every one of these exists because a prompt instruction was not enough.

**A dose with nothing registered.** `pesticide_uses` is keyed on (crop, pest).
No row means the answer names no product and no rate at all, and says why.
`dose_status` reports `available`, `none_registered` or `not_applicable` as a
field, so the interface can show a refusal *as* a refusal rather than
string-matching the word "registered" across four scripts.

**A price or subsidy figure with nothing behind it.** Asked for a support price
it did not hold, the model wrote a fluent, specific, invented one — despite an
explicit prohibition in the same prompt. Deterministic post-checks now strip
those sentences.

**A land unit that is not a unit.** A bigha is between 0.31 and 1.25 acres
depending on the state: a factor of four, and a four-fold error in a pesticide
quantity is the exact harm the register grounding exists to prevent. `units.py`
converts from a table and **refuses** when the state is unknown.

**A disease the picture cannot settle.** The obvious build is a 29-class CNN
over PlantVillage. It is the wrong tool for one decisive reason: a softmax
cannot abstain — it returns a class with confident-looking probability whether
the input is a tomato leaf it knows or a rice leaf it has never seen. So the
photograph is read once into a closed symptom vocabulary and matched against
labelled readings by field agreement. The bank may only ever *weaken* a claim:
`confirmed`, `disputed`, `uncovered`, `unavailable`. Where it disputes, the pest
is dropped, no dose is looked up, and the answer names both possibilities and
sends the farmer to their KVK. The identification is hedged; the dose, which
comes out of the statutory register, never is.

**Retrieval outside its coverage.** Passages below a measured cosine floor
(`RAG_MIN_SIMILARITY`, currently 0.70) are never shown to the model. Questions
the documents genuinely cover score 0.68–0.80; ones they do not top out near
0.58. Set too low, retrieval produces a *more confident guess*, not a grounded
answer.

**Claiming a capability that is down.** `provenance.py` assembles what the
system can do from live state — which integrations are configured, how many
doses are loaded, which documents are in the store — because a hand-written
self-description goes stale silently, and once told a farmer there were no
scheme documents while the store held eighty-six passages about them.

---

## 6. Identity and privacy

`user_id` used to arrive in the request body and be believed. On SMS that is
sound: the network tells the gateway who sent the message, and a farmer cannot
forge its idea of their own number. On the web it was not sound at all — anyone
could send another farmer's number and have their profile and recent
conversation recalled into an answer, then write into their message log.

- **Sign-in is a phone number and a six-digit code**, carried afterwards in a
  signed token. `/agent`, `/agent/media`, `/profile` and `/history` take the
  farmer from the token and ignore what the body claims.
- **The phone number is the `user_id`, deliberately.** It is the key SMS has
  always used, so a farmer who signs up in a browser and later texts the gateway
  is one farmer with one history rather than two rows that never learn about
  each other. An email login would have forked the identity space of a product
  whose main channel is SMS.
- **The code is never stored** — only a keyed hash bound to the phone it was
  issued for. Sends are throttled harder than guesses, because each one is a
  real SMS off a real SIM.
- **`AUTH_SECRET` does not degrade to "off".** Unset, a random one is generated
  per process: sign-in still works, but a restart signs everyone out. A visible
  annoyance beats an invisible hole. `/health` says which state you are in.
- **`/forget` erases a farmer** — profile and full message history — and backs
  the SMS STOP keyword. It accepts the bridge relaying STOP, or a farmer naming
  only their own id.
- **The operational endpoints** (`/feedback/*`) require `BRIDGE_TOKEN`. Where
  that is unset they stay open **and say so on `/health`**, rather than closing:
  the bridge and backend deploy separately, and a backend that starts 401ing a
  real farmer's SMS because a variable was missed is the worse failure.

---

## 7. Configuration

**Only `GEMINI_API_KEY` is required.** Every other integration is optional:
without it the tool reports itself unavailable, the agent routes around it, and
the advisory still goes out. `GET /health` reports exactly what is live.

| Variable | Unlocks | Without it |
|---|---|---|
| `GEMINI_API_KEY` | Everything | Service refuses to start |
| `AUTH_SECRET` | Sessions that survive a restart | Regenerated per process; everyone signed out on restart |
| `BRIDGE_TOKEN` | Proof the SMS bridge is the SMS bridge | `/feedback/*` stay open, reported on `/health` |
| `SMS_GATEWAY_USER` / `SMS_GATEWAY_PASSWORD` | Sending sign-in codes | Nobody can sign in on the web |
| `GUEST_ASK_ENABLED` | Questions before sign-in (default `true`) | `false` makes the web app's guests get 401, as before |
| `GUEST_PER_HOUR` / `GUEST_IP_PER_HOUR` / `GUEST_DAILY_CAP` | Guest limits: per browser, per network address, all guests per day (defaults 10 / 60 / 400, per instance) | — |
| `DATABASE_URL` | Profiles, history, doses, retrieval, lesion bank, ratings | Stateless: no memory, no grounded doses, no retrieval |
| `GOV_API_KEY` | Live mandi prices | MSP still answers; live rates omitted |
| `EE_SERVICE_KEY` | Soil texture, pH, organic carbon | Advice omits soil |
| `LOCATION_API_KEY` | Google Maps geocoding | Nominatim is used, and needs no key |
| `KNOWLEDGE_BASE_ID` + AWS keys | Bedrock retrieval fallback | pgvector serves retrieval locally |
| `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp channel | SMS and web only |
| `APP_USERNAME` / `PASSWORD` (bridge) | SMS channel | Web only |

Weather needs no key. Geocoding needs no key.

### Models

`gemini-2.0-flash` and the `gemini-2.5-*` line are no longer callable by new API
keys — the API returns 404 pointing at the 3.x line. Note that `models.list`
reports models a key **cannot** actually invoke, so verify with a real
`generateContent` call before changing these.

| Setting | Default |
|---|---|
| `TEXT_MODELS` | `gemini-3.1-flash-lite,gemini-3.6-flash,gemini-3.5-flash-lite` |
| `MEDIA_MODEL` | `gemini-3.5-flash-lite` |

The chain is fastest-first; a 429, 503 or 404 fails over to the next. The retry
budget is bound as a *call* kwarg on purpose — `langchain_google_genai`
otherwise defaults to six attempts with exponential backoff and stalls ~60s on a
dead model. Bound correctly, failover takes ~1s. Free-tier quota is **per
model**, so the chain also multiplies usable daily capacity.

### The binding constraint

The free tier allows **20 `generateContent` requests per day, per model**. At
three calls per question that is roughly 20–30 questions a day across the whole
chain. Fine for testing, unusable in the field. **Enable billing on the Google
Cloud project behind the key before a pilot** — nothing in the code changes; the
same key simply stops being rate-limited.

---

## 8. Running it

```bash
# --- Backend ---
cd AnnaData-Backend-main
python -m venv .venv && .venv/Scripts/activate      # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                                # add GEMINI_API_KEY
uvicorn app:app --reload --port 8000
curl http://127.0.0.1:8000/health                   # what is actually configured

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

For local work without a handset, set `AUTH_REQUIRED=false` — the backend then
accepts a body-supplied `user_id` the way it used to. Never set it on anything
with a public URL.

`requirements.txt` is the serving path only. PDF parsing, YAML and the AWS SDK
live in `requirements-tools.txt`, for `tools/` and `eval/`.

### Loading the grounded data

```bash
python tools/fetch_cibrc.py            # the register PDFs
python tools/load_cibrc.py             # → pesticide_uses (2,456 kept, 256 dropped deliberately)
python tools/ingest_docs.py            # scheme documents → pgvector
python tools/build_lesion_bank.py      # labelled symptom readings
python tools/warm_mandi_cache.py       # pre-warm the price cache
```

The 256 dropped rows are the point, not a loss: each was a row whose product
heading could not be identified, and keeping it would have credited a dose to
the wrong chemical.

### The SMS channel

1. Install [SMS Gateway for Android](https://github.com/capcom6/android-sms-gateway/releases)
   on a phone with an active SIM; grant `SEND_SMS`, `RECEIVE_SMS`,
   `READ_PHONE_STATE`.
2. Enable **Cloud Server** (not Local Server) and copy the username and password
   into the bridge's `APP_USERNAME` / `PASSWORD`, with `SMS_MODE=cloud`.
3. Deploy the bridge, then register the webhook once: `python webhook.py`
   (`--list` to inspect without registering).
4. Text the phone's number. A reply should arrive within ~10–30s.

Keep the handset charged, online and out of battery optimisation — it is the
actual transmitter.

**Cost and regulation.** Each reply is an ordinary SMS billed by the SIM's plan.
This phone-as-gateway design deliberately avoids India's A2P/DLT regime, which
requires a registered sender and pre-approved templates and would block
free-form AI replies outright. It is the right call at prototype stage and the
wrong one at scale.

**Reply length.** Latin packs 153 characters per billed segment; Devanagari,
Gurmukhi, Telugu and Bengali force UCS-2 at 67 — so an identical-looking Hindi
reply costs more than twice as much. `MAX_SMS_SEGMENTS` caps *segments*, which
is what actually controls cost across languages; `MAX_SMS_CHARS` is a hard
character ceiling. Answers are trimmed at a sentence boundary, never mid-word.

---

## 9. Deploying

`render.yaml` describes all three services as one Blueprint — no credit card, no
AWS account. Push to GitHub, create a Blueprint Instance at
[dashboard.render.com/blueprints](https://dashboard.render.com/blueprints), and
fill in the secrets Render prompts for.

Render cannot wire the services to each other: `fromService` resolves to an
*internal* hostname a browser cannot reach, and Render appends a random suffix
when a service name is already taken, so the public host is often not the name
in the file. Set these by hand to the **public** hosts:

| Service | Variable | Then |
|---|---|---|
| `annadata-backend` | `FRONTEND_URL` | restart |
| `annadata-backend` | `AUTH_SECRET`, `BRIDGE_TOKEN`, `SMS_GATEWAY_USER`, `SMS_GATEWAY_PASSWORD` | restart |
| `annadata-sms` | `AI_ENDPOINT` = `https://<backend>/agent`, `PUBLIC_URL`, `BRIDGE_TOKEN` | restart |
| `annadata-frontend` | `REACT_APP_API_URL` = `https://<backend>` | **redeploy** |
| `annadata-frontend` | `REACT_APP_SMS_NUMBER` = the gateway's number, as farmers should see it (optional) | **redeploy** |

Without `REACT_APP_SMS_NUMBER` the web app says that AnnaData answers by SMS
but names no number to text.

The frontend needs a full redeploy, not a restart: CRA inlines env vars at build
time. `BRIDGE_TOKEN` must be the *same* value on the backend and the bridge, and
the sign-in variables are **not yet declared in `render.yaml`** — add them in the
dashboard.

Verify:

```bash
curl https://<backend>/health          # features, database, lesion bank, auth state
curl https://<sms-bridge>/health       # "ok" or "degraded", with the specific problem
curl -X POST https://<backend>/agent -H "Content-Type: application/json" \
  -d '{"query":"When should I sow wheat in Punjab?"}'
```

**Free Render instances sleep after ~15 minutes and take ~50s to wake**, and the
workspace has 750 instance-hours a month — two services awake around the clock
need 1,460, so keeping them warm is arithmetically impossible rather than merely
awkward, and pinging hard enough to try exhausts the allowance. Point a free
pinger at both `/health` endpoints as a stopgap; the real fix is
`DEPLOY_CLOUD_RUN.md`, where containers start in seconds and there is nothing to
keep warm.

`apprunner.yaml`, `amplify.yml` and `Dockerfile`s are committed for AWS or any
container host. Both AWS options bill from the first hour.

---

## 10. Testing and evaluation

Every bug this project has shipped was found by a person reading an SMS
screenshot. That does not scale, and it let regressions survive several commits.

```bash
python eval/run.py                     # everything (2 model calls per case)
python eval/run.py --tag safety        # one group
python eval/run.py --id dose_refused_when_unregistered
```

`eval/cases.yaml` holds **38 cases**, each derived from a failure that actually
reached a farmer or a property that must not regress: script matches input, no
dose quoted where none is registered, segment budget respected, no sowing window
in the past, the profile's crop used rather than asked for, no invented support
price or subsidy, a capability not offered while it is failing. Tags exist
because the free tier's daily quota does not fit the suite. Twenty-eight were
passing at the last recorded full run; ten have been added since.

Several kinds of fault cannot be written as a model case, and have their own
deterministic tests:

| Test | Why it cannot be a case |
|---|---|
| `eval/test_feedback.py` | Scheduling logic has no language in it — checks the rating cooldown against the database |
| `eval/test_mandi.py` | Selection logic: the model never sees the rows wrongly included. Runs against fixtures from a real day's publication, so it costs no model calls |
| `eval/test_romanisation.py` | Rare nondeterministic output would make a case pass or fail on the roll of the model. Checks the correction, on hand-written inputs |
| `eval/test_profile_location.py` | Profile and location-precision bookkeeping |
| `eval/test_retry.py` | Transport classification: which backend statuses the bridge waits out and which it drops. The model never sees a status code, and the fault it guards against produces *no message at all* |
| `eval/test_guest_access.py` | Who may ask without signing in and how often: guest ids that could carry a phone number, limits that count refused requests, a ceiling that never triggers. Fake clock, no database, no model |
| `eval/test_claim_guest.py` | That a guest's questions follow them onto the number they confirm, filling profile gaps without overwriting what the farmer told us before. Needs a database, because an `UPDATE ... FROM` that matches nothing fails silently |
| `eval/test_code_message.py` | That the sign-in SMS still looks like a text from a person - no "OTP", "code" or "do not share", GSM-7 only, one segment. Networks refuse commercial-looking messages from an ordinary SIM, and the gateway only reports Failed |
| `eval/test_greeting.py` | Whether a short message is an arrival or someone closing a conversation. Decided before any model is called, and what it picks is which instruction the model is then given |

A suite that can only express "ask the model and look at the answer" quietly
leaves the deterministic half of the system untested — and that half is where
these bugs were.

`tools/check_romanisation.py` and `tools/measure_lesion_bank.py` are detectors
rather than tests: no pass or fail, run to produce a number. The lesion
measurement deliberately reports four outcomes — correct, abstained, disputed,
**wrong** — and refuses to sum them, because a farmer told "the picture is not
enough, take it to your KVK" loses nothing while a farmer given a confident
wrong disease buys the wrong chemical and loses the crop anyway. `wrong` is the
number that governs whether it ships.

---

## 11. Measured results

Every figure was measured on this system. Where one is absent, the thing was
never measured, and that is said in section 12.

### Latency

| What | Before | After |
|---|---|---|
| Rice disease question, end to end | 97.4s | **4.0s** |
| Weather question, end to end | ~97s | **2.4s** |
| LLM failover past a dead model | 64.6s | **1.1s** |
| Soil lookup (3 Earth Engine reads) | ~9s | **1.5s** |
| Repeat weather, same district | 0.74s | ~0s (cache) |
| Price question during an upstream outage | 90.4s | ~0s after 3 failures (circuit breaker) |

Of the original 97.4s, **90.35s (92.8%)** was a dead data.gov.in. The three
model calls together were **6.1s**. This is why a master–worker architecture
would have made latency *worse*: the model calls were never the problem, and a
router plus per-domain workers multiplies the only part that was already fast.

Model choice contributed separately — swapping the primary from
`gemini-3.6-flash` to `gemini-3.1-flash-lite` took mean end-to-end answer time
from **23.2s to 2.4s**, with answers still correct and specific across Hinglish,
Devanagari and English.

Deployed and warm: **0.4s** health, **1.8–3.5s** for a full answer. Cold on
Render's free tier: **140s** to first byte, which is why the keep-warm ping
matters and why the bridge retries rather than apologising.

### Efficiency

| | Before | After |
|---|---|---|
| Model calls per question | up to 4 | **3** |
| Tools run | all, always, sequentially | only what the intent needs, concurrently |
| Intent + message-kind + tool selection | a separate model call | **0 extra calls** |

### Grounding

| | |
|---|---|
| Registered pesticide uses | **2,456** across 314 crops and 825 products |
| Minimum Support Prices | 20 commodities, 39 aliases |
| Rows dropped by the misattribution guard | 256 of 2,722 |
| Product headings missed per 40 pages, before the fix | 30 |
| Retrieval corpus | 86 chunks, 5 documents, 768-d embeddings |
| Retrieval separation, covered vs not | 0.68–0.80 against 0.47–0.58 |
| Scripts verified end to end | 4 — Latin, Devanagari, Gurmukhi, Bengali |

### Correctness defects found and fixed

| Defect | Magnitude |
|---|---|
| Soil organic carbon | reported at **2× true value** |
| Soil texture class map | **inverted** — clay read as sand, across all 12 classes |
| Pre-harvest intervals | dilution volumes landing in the field, e.g. "500–1000 days" |
| SMS billing for Indic scripts | capped by characters, costing **2.3×** more per segment |

### Cost

Recurring infrastructure: **$0**. Avoided by not using Bedrock's default vector
store — OpenSearch Serverless Classic, billed a minimum of roughly
**$345–700/month** whatever it holds. Free tiers throughout: Render, Neon
Postgres with pgvector, Nominatim, Open-Meteo, MET Norway, Earth Engine
non-commercial, and the handset. The only item worth paying for is Gemini
billing, which is a quota question rather than an infrastructure one.

---

## 12. What has not been measured

This section matters more than the one above it, because the absence is where
the risk sits.

- **Agronomic accuracy.** The harness checks *properties* — script, segment
  budget, whether a dose was quoted where none is registered. It does not check
  whether the advice is agronomically right. Doses are grounded in the statutory
  register; the surrounding guidance is still the model's, and **nobody
  qualified has reviewed it**.
- **Photo diagnosis in a field.** The lesion bank's floor (0.72) is a judgement,
  not a measurement. Its reference photographs are laboratory images — one
  detached leaf on a uniform background — so any figure from them is an upper
  bound on field performance. Measured on the reference bank itself, **25% of
  readings share an exact description with a different disease of the same
  crop**. And the nine crops it covers are not the crops our farmers grow: rice,
  wheat and cotton are absent from it.
- **Load.** Never load tested. One phone, one SIM, a per-model daily quota.
- **Delivery rate.** No measurement of how many replies actually arrive.
- **Whether any of it helps.** The rating loop is live and has collected two
  ratings from one farmer. That is plumbing, not evidence. Nothing yet records
  whether a farmer acted on an answer or came back because of it.
- **Retrieval breadth.** Five documents, four schemes. It refuses outside its
  coverage, but a farmer can ask about far more. Limited by what can be
  obtained, not by the machinery.
- **The similarity floor is tuned to this corpus.** It has already been broken
  once by adding documents, and needs re-measuring whenever the corpus grows
  materially.

---

## 13. Known limits

- **Gemini free tier: 20 requests/day per model.** The ceiling on real use.
  Everything else is polish until billing is enabled.
- **One phone, one SIM.** Off, offline or out of balance means the service is
  down — and silence looks identical to working. It is now also the sign-in
  path, so a dead handset means nobody can create an account either. The
  WhatsApp channel exists partly as redundancy against exactly this.
- **Routing one-time codes through a person-to-person handset** is a greyer area
  than the free-form advisory traffic it was chosen for. Accepted until the move
  to a registered DLT sender, which is planned as one change; `sms_out.send` is
  the seam it happens at.
- **Deduplication is in-memory.** A bridge restart can permit one duplicate
  reply. Fine for a single instance; needs Redis or DynamoDB past one.
- **RCS is invisible to the gateway.** Google Messages sends Android-to-Android
  as RCS, not SMS, so those never reach the app and get no reply. Senders must
  disable chat features; feature phones are unaffected.
- **Soil is a 250 m global model**, not a test of the farmer's field. The system
  says so when asked.
- **data.gov.in** returns 502 for days at a time. A circuit breaker stops
  farmers waiting out the timeouts.
- **`.env.example` predates sign-in.** `render.yaml` no longer does:
  `AUTH_REQUIRED`, `AUTH_SECRET`, `BRIDGE_TOKEN`, `SMS_GATEWAY_*`,
  `RAG_MIN_SIMILARITY` and the WhatsApp variables are declared there now, with
  `BRIDGE_TOKEN` generated on the backend and copied to the bridge via
  `fromService`, so the two cannot drift apart. See sections 7 and 9.
- **The two services deploy independently, and nothing checks they agree.**
  The backend ran 44 commits ahead of the bridge for a day without either
  reporting a problem. Until a version check exists, deploy both together.
- **CRA is unmaintained.** It builds fine today; Vite is the eventual path.
- **One farmer.** The rating loop, the session features and the eval harness all
  work. What is missing is people using the service.
