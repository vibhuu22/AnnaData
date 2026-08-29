# AnnaData — engineering notes

A record of what was built, what went wrong, and why the system is shaped the
way it is. Written as the work happened, so the reasoning survives the code.

---

## 1. What the system is

An agricultural advisory service for Indian farmers, reachable two ways:

- **SMS**, so a farmer with a basic phone and no internet can use it
- **Web**, for those who have a smartphone

Both channels call the same agent. The SMS side runs through an Android handset
acting as a gateway, which is the decision the whole architecture rests on.

```
Farmer (SMS) ──▶ Android phone ──webhook──▶ SMS bridge ──▶ Agent API ──▶ Gemini
                  (sms-gate.app)             (Quart)        (FastAPI)      │
                                                                ├── soil (Earth Engine)
Farmer (web) ──────────────────────────────▶ React app ────────▶├── weather (Open-Meteo → MET Norway)
                                                                ├── prices (data.gov.in)
                                                                ├── doses (CIB&RC table)
                                                                └── memory (Postgres)
```

---

## 2. Decisions that shaped everything

### An Android phone as the SMS gateway, not Twilio

India's A2P/DLT regime requires a registered sender ID and **pre-approved
message templates**. Free-form AI answers cannot be templated, so the
conventional route is closed at any volume. A handset sending ordinary
person-to-person SMS sidesteps it entirely, costs nothing beyond the SIM's
plan, and works today.

The trade is honest: one phone is a single point of failure, and it will not
scale. It is the right call at prototype stage and the wrong one at scale.

### Cloud mode over local server

The original setup needed the phone and server on the same Wi-Fi plus an ngrok
tunnel whose URL rotated on every restart and had to be re-registered by hand.
Cloud mode gives a fixed endpoint and lets the phone work from anywhere on
mobile data. This removed the deck's own "not deployed beyond ngrok"
limitation.

### Every integration optional, none fatal

A missing key disables one tool and nothing else. The service starts with only
a Gemini key, reports what is configured at `GET /health`, and answers around
whatever is absent. Before this, a missing Earth Engine key raised at import
and took the entire API down.

### Postgres + pgvector instead of AWS Bedrock

The original design put the knowledge base on Bedrock. Bedrock knowledge bases
need a vector store, and the default — OpenSearch Serverless Classic — bills a
minimum of roughly **$345–700/month** whatever it holds. The Neon Postgres
already provisioned for farmer profiles has pgvector, and the Gemini key
already has an embeddings model. Same capability, no new account, no cost.

### Structured lookup for doses, vectors for prose

These are different problems. A pesticide dose is a precise fact with a right
answer; retrieving prose that mentions a chemical does not tell you the
approved rate for a given crop and pest. Doses live in a table keyed on
(crop, pest). Open-ended material — schemes, storage, practice — goes in
pgvector, where similarity is the right tool.

The table's most important property is what it **refuses**. With nothing on
file it instructs that no product and no dose be named at all.

### Compute facts in code; do not ask the model to infer them

This pattern recurred three times and worked every time:

| Problem | Prompting alone | Computed in code |
|---|---|---|
| Sowing windows in the past | kept suggesting June in August | inject today's date + cropping season |
| Hinglish answered in Devanagari | "match their language" ignored | detect script, state it outright |
| Tool selection | — | intent → tool map, no model call |

When a fact is knowable deterministically, knowing it beats asking.

---

## 3. Problems, and what they turned out to be

### The SMS channel never worked — two independent bugs

1. The bridge read `data["response"]`; the backend returns `{"answer": ...}`.
   Every reply was discarded.
2. The bridge read `payload["phoneNumber"]`; the gateway sends the originating
   number as `sender`. Even a working reply was addressed to `None`.

Neither would have been found without reading the gateway's own documentation.

### Devanagari crashed the request

Windows consoles default to cp1252, so `print()` of Hindi text raised
`UnicodeEncodeError` and killed the request before the agent was called. A
farmer texting in Devanagari — most of them — got nothing. Fixed by forcing
UTF-8 on stdout at import.

### Models silently retired

`gemini-2.0-flash` and the 2.5 line are no longer callable by new API keys; the
API returns 404 pointing at the 3.x line. Worse, `models.list` **still lists
models the key cannot invoke**, so the listing cannot be trusted — only a real
`generateContent` call settles it.

### A 60-second stall that was not a timeout

`langchain_google_genai` reads `max_retries` from *call* kwargs, not the
constructor. Setting it on the model silently does nothing, and the default is
six attempts with exponential backoff — about 60s spent on a dead model before
the fallback is tried. Bound as a call kwarg, the same failover takes ~1s.

### 93% of latency was one dead API

Profiling a rice-disease question: 97s total, of which 90s was fetching mandi
prices the answer would never mention. Every tool ran whenever coordinates were
known, sequentially. Selecting tools by intent and running them concurrently
took it to 4s — and the answer improved, because the relevant reading was no
longer buried under hundreds of irrelevant price rows.

### Soil organic carbon reported at double its value

OpenLandMap stores it divided by 5; the code reported the raw pixel as a
percentage. A soil at a genuine 0.50% — low, needs compost — printed as 1.00%,
which reads as adequate.

### The soil texture table was inverted

OpenLandMap codes **1 as Clay and 12 as Sand**. The lookup had it backwards, so
every reading came back as roughly the opposite soil. Nagpur — black cotton
clay — was reported as sand. Irrigation and drainage advice follows directly
from texture, so the reversal inverts everything built on it. This bug predated
the current work and would have shipped the moment soil went live.

### Parsing the pesticide register: misattribution, not data loss

Product headings were matched against a fixed list of formulation codes, which
missed thirty in forty pages. A missed heading does not drop rows — it
attributes them to the **previous product**. Wrong chemical, convincing dose.
Detection now keys on the strength every product carries, and an unrecognised
lone cell **clears** the current product so its rows are dropped rather than
misfiled. That cost 256 rows out of 2,722, which is the right trade.

Separately, rows missing an active-ingredient figure shift their columns left
and land a dilution volume in the waiting period, producing pre-harvest
intervals of "500–1000" days. Anything beyond a season is now discarded: no
waiting period is honest where a wrong one is not.

### Open-Meteo rate limits by IP, and the IP is shared

Weather worked locally in 2s and failed in production. The cause was
`429 Daily API request limit exceeded` — a **per-IP** limit on a Render free
instance whose egress IP is shared with every other free-tier user. We could
make zero calls and still be locked out, so caching and retries could never fix
it. A second provider (MET Norway, free and keyless) now serves weather when
Open-Meteo refuses; it has no history, and the report says so rather than
presenting a thinner answer as complete.

### One behaviour for every message

The agent classified a message's *topic* but not its *kind*, so statements,
meta-questions, corrections and greetings all became "give agronomic advice".
A farmer writing "I am in Nagpur and I grow cotton" was lectured about sowing;
one asking "how do you know about my soil?" received an explanation of
Walkley-Black titration — a correct account of how soil carbon is measured, and
no answer at all to what was asked.

Adding dialogue acts then **over-corrected**: "my cotton has been attacked by
locusts" is grammatically a statement, and was answered with "noted, what would
you like to ask?" A farmer whose crop is being eaten is asking for help
whatever the grammar. Naming a topic at all now routes as a question.

### The profile was loaded but not used

Facts absent from the current message did not fall back to the stored profile,
and — the part that actually bit — the advice prompt and the tools were still
handed the raw extraction rather than the merged result. So the agent asked
which crop, for a farmer whose cotton had been on file since their first
message.

---

## 4. Two kinds of memory

Deliberately separate, because they have different lifetimes:

- **Profile facts** — location, coordinates, crops, language. Persist
  indefinitely. Merged, never overwritten: a message mentioning no location
  must not erase the one learned last week.
- **Session context** — recent turns, expiring after 48h, so a thread from
  three weeks ago cannot be mistaken for context on today's question.

Conflating them causes stale context to resurface, or a location to be
forgotten because a chat window lapsed.

Location is captured **opportunistically** — the parser already extracted it
from every message and discarded it. If still unknown after answering, one
short invitation is appended, within the existing SMS segment budget, and not
repeated for 24 hours. It never blocks an answer.

---

## 5. SMS is not a text box

- **Segments, not characters.** Latin packs 153 characters per segment;
  Devanagari and Gurmukhi force UCS-2 at 67. Capping on characters bills
  Indic-language farmers more than twice as much for the same message.
- **Markdown is noise.** Answers are flattened to plain text.
- **Truncation must land on a sentence.** A pesticide dose cut mid-instruction
  is worse than a shorter complete one.
- **RCS is invisible.** Google Messages sends Android-to-Android as RCS, not
  SMS, so those messages never reach the gateway. Feature phones — the actual
  target — are unaffected.

---

## 6. Testing

Every bug above was found by a person reading an SMS screenshot. That does not
scale, and it let regressions survive several commits.

`eval/` holds cases derived from real failures, each with machine-checkable
assertions: script matches input, no dose quoted where none is registered,
segment budget respected, no sowing window in the past, the profile's crop used
rather than asked for. Tags allow a subset to run, because each case costs two
model calls and the free tier's daily quota does not fit the suite.

---

## 7. Known limits

- **Gemini free tier: 20 requests/day per model.** Two calls per question means
  roughly 30 questions a day across the fallback chain. This is the ceiling on
  real use; everything else is polish until billing is enabled.
- **One phone, one SIM.** Off, offline or out of balance means the service is
  down, and silence looks identical to working.
- **No authentication or rate limiting** on `/agent`.
- **Soil is a 250 m global model**, not a test of the farmer's field. The
  system says so when asked.
- **data.gov.in** has been returning 502 for days. A circuit breaker stops
  farmers waiting out the timeouts.
- **No feedback loop.** Nothing records whether an answer helped.
