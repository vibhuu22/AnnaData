# Admin dashboard v2

Local preview: http://127.0.0.1:8766/admin

Start from `AnnaData-Backend-main` with `Start-AdminDashboard.ps1`, or run
`.venv/Scripts/python.exe -m uvicorn admin_server:app --host 127.0.0.1 --port 8766`.
Use the existing private admin key from `.env.admin`; never commit or share it.
The local server reads the configured database without starting advisory models.

## Views

- Overview: six headline metrics, rule-based findings, daily activity, needs and channel mix.
- Adoption: distinct active identifiers over 24h/7d/30d, repeat activity on different dates,
  messages per active identifier, session counts and request types.
- Efficiency & errors: tracked failure rate, pending/stuck requests, p50/p95/p99,
  retries, error categories, channel and backend-release breakdowns.
- User diversity: channels, reply speech codes, request states and raw crop labels,
  with request counts and distinct identifiers per category.
- Feedback & quality: positive/neutral/negative scores, rating coverage, reviewer
  outcomes and severity, explicit confirmation, and negative-feedback conversations.
- Data & delivery: request linkage, optional-field coverage, tool/evidence summaries,
  dose outcomes, gateway metrics and the existing mandi cache panel.
- Existing conversation reviews and architecture guide remain available.
- Metric definitions explain every denominator and important limitation.

## Measurement boundaries

Counts are retained observations, not verified unique humans. All traffic is the
default; farmer/test/unknown classifications remain explicit. Repeat activity is
not cohort retention. Web chat IDs are not yet the analytics session boundary.
Guest-to-phone migration does not currently reconcile all analytics identity data.
State is request context, not residence. Reply speech code is not native language.
Crop labels are raw and can include synonyms.

Backend failures exclude pre-pipeline, browser, playback and early media errors.
Latency covers successful timed backend requests, not end-to-end experience.
Ratings attach to sessions, not guaranteed individual answers; repeated rating
events are counted as events. Unavailable ratings are not presented as zero.
Complete review coverage requires both outcome and safety assessments.

Zero-activity IST dates are included; first/current dates can be partial. Activity
is computed from incoming message timestamps, not session start timestamps.
The 20,000-row window limit remains (now also enforced for ratings); no server-side
pagination was introduced. True retention, onboarding events, demographic fields,
model usage/billing, detailed voice/photo instrumentation and handset delivery
receipts still need instrumentation. No data backfill or schema migration is made.

## Validation

- Seven new offline metric tests: distinct activity, zero dates, pending/failure
  denominators, latency exclusions, unavailable/neutral feedback, audience filters,
  complete-review coverage and request linkage.
- Twenty existing analytics/API tests pass.
- Both dashboard JavaScript files pass `node --check`.
- Live-data headless Chrome checks visit all nine sections at 1440px and the seven
  analytics/definition pages at 390px, check overflow, empty farmer selection,
  unavailable ratings, and logout clearing private content. Credentials are loaded
  locally by `tools/dashboard_qa.py` and never printed. QA does not submit reviews.

No merge or production deployment is included. Local preview reflects this branch.
