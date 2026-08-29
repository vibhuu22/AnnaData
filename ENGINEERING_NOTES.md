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

### Retrieval answered questions the corpus did not cover

With the similarity floor at 0.45, a question about solar pump subsidies
returned PM-KISAN passages — loosely related, since both are agricultural
schemes — and the model, handed something rather than nothing, answered from
general knowledge anyway. Retrieval had turned a guess into a *more confident*
guess, which is worse than no retrieval at all.

Measuring the corpus settled the threshold rather than intuition:

| Question | Top similarity |
|---|---|
| how much does PM-KISAN pay | 0.739 |
| who is excluded from PM-KISAN | 0.801 |
| which scheme gives me a solar pump | 0.578 |
| crop insurance for hailstorm damage | 0.536 |
| how do I build a cold storage | 0.475 |
| what is the price of cotton today | 0.469 |

Covered questions score 0.68–0.80; uncovered ones top out at 0.578.

The floor was set at 0.65, and **adding four more documents broke it**. A
question about tractor subsidies then scored **0.667** against a PMFBY passage
about Gujarat leaving the scheme — close on wording, entirely wrong on
substance — and the model answered by naming "PM Kisan Tractor Yojana", a
scheme widely circulated online that does not exist as a central scheme.

A single similarity number cannot separate relevance from adjacency, and the
problem grows with the corpus: more documents mean more chances that something
irrelevant clears the bar. The floor is now **0.70**, and the prompt also
requires the model to check that a retrieved passage actually addresses the
question before using it, rather than stretching one about a different scheme
to fit. This threshold is corpus-dependent and will need revisiting again.

### Not all sources deserve equal weight

The corpus mixes government documents with Wikipedia articles. Both are useful;
only one is authoritative. A farmer acting on an insurance deadline or a
subsidy amount should know which they were told, so documents carry a tier —
`official` or `reference` — and the model is shown it. Where only unofficial
material matches, the answer says the details are indicative and to confirm
with the agriculture office before acting on a date, amount or eligibility
rule.

### PDF extraction emits bytes Postgres will not store

Four chunks of a nine-page factsheet vanished with
`PostgreSQL text fields cannot contain NUL (0x00) bytes`. Extraction leaves NUL
and other control characters in the text; they are now stripped during
cleaning.

### Most government agricultural sources cannot be fetched

Of eight candidate sources probed, one downloaded cleanly. `agricoop.gov.in`
refuses connections outright; the Soil Health Card portal renders three words
of text without JavaScript; several documented PDF links return HTML shells or
404s. This is presumably why the original design crawled once and stored the
result to S3. Documents that will not download have to be saved from a browser
and ingested from disk.

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

## 6. Measured results

Every figure below was measured on this system, not estimated. Where a number
is absent it is because the thing was never measured, and that is said plainly
in section 8.

### Latency

| What | Before | After | Change |
|---|---|---|---|
| Rice disease question, end to end | 97.4s | 4.0s | **24× faster** |
| Weather question, end to end | ~97s | 2.4s | **40× faster** |
| LLM failover past a dead model | 64.6s | 1.1s | **59× faster** |
| Soil lookup (3 Earth Engine reads) | ~9s | 1.5s | **6× faster** |
| Repeat weather for the same district | 0.74s | ~0s | cache hit |
| Price question during upstream outage | 90.4s | ~0s after 3 failures | circuit breaker |

Where the 97s actually went, before any of this:

| Step | Time | Share |
|---|---|---|
| mandi prices (data.gov.in, down) | 90.35s | **92.8%** |
| extract slots (LLM) | 2.88s | 3.0% |
| refine query (LLM) | 1.61s | 1.7% |
| synthesise answer (LLM) | 1.60s | 1.6% |
| weather (HTTP) | 0.76s | 0.8% |
| geocode (HTTP) | 0.16s | 0.2% |

The three model calls together were **6.1s of 97.4s**. This is why a
master-worker architecture would have made latency worse: the LLM calls were
never the problem, and adding a router plus per-domain workers multiplies the
only part that was already fast.

Model choice contributed separately: swapping the primary from
`gemini-3.6-flash` to `gemini-3.1-flash-lite` took mean end-to-end answer time
from **23.2s to 2.4s** across three questions, with answers still correct and
specific.

Deployed, warm: **0.4s** health, **1.8–3.5s** for a full answer. Cold, on
Render's free tier: **140s** to first byte, which is why the keep-warm ping
matters and why the SMS bridge retries rather than apologising.

### Efficiency

| | Before | After |
|---|---|---|
| Model calls per question | up to 4 | 3 |
| Tools run per question | all 3, always, sequentially | only those the intent needs, concurrently |
| Cost of intent classification | — | 0 extra calls (rides on the existing extraction) |
| Cost of message-kind classification | — | 0 extra calls (same) |
| Cost of tool selection | — | 0 calls (plain data and functions) |

`kb_router` was a whole model call that the planner replaced. Intent, message
kind and pest all ride on the extraction call that runs regardless, so richer
routing was added while the call count went **down**.

### Grounded data

| | |
|---|---|
| Registered pesticide uses loaded | **2,456** |
| Distinct crops covered | **314** |
| Distinct products | **825** |
| Source | 6 CIB&RC PDFs, as on 31.03.2026 |
| Rows parsed before the misattribution guard | 2,722 |
| Rows kept after it | 2,466 (**256 dropped deliberately**) |
| Product headings missed per 40 pages, before the fix | **30** |
| Insecticide uses retaining a valid waiting period | 504 / 1,102 |

The 256 dropped rows are the point, not a loss: each was a row whose product
heading could not be identified, and keeping them would have credited a dose to
the wrong chemical.

### Correctness defects found and fixed

| Defect | Magnitude |
|---|---|
| Soil organic carbon | reported at **2× true value** — 0.50% printed as 1.00% |
| Soil texture class map | **inverted** — clay read as sand across all 12 classes |
| Pre-harvest intervals | dilution volumes landing in the field, e.g. "500–1000 days" |
| SMS billing for Indic scripts | capped by characters, costing **2.3×** more per segment than Latin |

### Coverage

| | |
|---|---|
| Scripts verified end to end | 4 — Latin, Devanagari, Gurmukhi, Bengali |
| Evaluation cases | 20, all passing |
| Embedding dimensions | 768 |
| Embedding separation | 0.814 related vs 0.521 unrelated (cosine) |
| Retrieval corpus | 86 chunks across 5 documents |
| — official (PM-KISAN guidelines, PIB Soil Health Card factsheet) | 57 chunks |
| — reference (Wikipedia: PMFBY, KCC, Soil Health Card) | 29 chunks |
| Retrieval separation, covered vs not | 0.68-0.80 against 0.47-0.58 |

### Cost

| | |
|---|---|
| Recurring infrastructure cost | **$0** |
| Avoided by not using Bedrock's default vector store | **$345–700/month** |

Free tiers throughout: Render hosting, Neon Postgres with pgvector, Nominatim
geocoding, Open-Meteo and MET Norway weather, Earth Engine non-commercial, and
the phone gateway. The only paid item the project needs is Gemini billing, and
that is a quota question rather than an infrastructure one.

---

## 7. Testing

Every bug above was found by a person reading an SMS screenshot. That does not
scale, and it let regressions survive several commits.

`eval/` holds cases derived from real failures, each with machine-checkable
assertions: script matches input, no dose quoted where none is registered,
segment budget respected, no sowing window in the past, the profile's crop used
rather than asked for. Tags allow a subset to run, because each case costs two
model calls and the free tier's daily quota does not fit the suite.

---

---

## 8. What has NOT been measured

Stating this plainly matters more than the numbers above, because the absence
is where the risk sits.

- **Agronomic accuracy.** The evaluation harness checks *properties* — script,
  segment budget, whether a dose was quoted when none is registered. It does
  not check whether the advice is agronomically right. Doses are now grounded
  in the statutory register, but the surrounding guidance is still the model's,
  and nobody qualified has reviewed it.
- **Load.** The original submission claimed 10× peak load at ≥99% delivery.
  Nothing has ever been load tested. One phone, one SIM, and a 20-request daily
  model quota.
- **Delivery rate.** No measurement of how many SMS replies actually arrive.
- **Whether any of it helps.** No feedback loop exists. Nothing records whether
  a farmer found an answer useful, acted on it, or came back.
- **Retrieval breadth.** Five documents covering four schemes. Retrieval works
  and refuses outside its coverage, but a farmer can ask about far more than
  four schemes. Breadth is limited by what can be obtained, not by the
  machinery.
- **The similarity floor is tuned to this corpus.** It has already been broken
  once by adding documents, and will need re-measuring whenever the corpus
  grows materially.

The honest summary is that the system is measurably faster, measurably cheaper,
and measurably more grounded than it was — and its agronomic quality remains
unmeasured.

---

## 9. Known limits

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
