# Admin dashboard v2

Local preview: http://127.0.0.1:8766/admin

Start from `AnnaData-Backend-main` with `Start-AdminDashboard.ps1`, or run
`.venv/Scripts/python.exe -m uvicorn admin_server:app --host 127.0.0.1 --port 8766`.
Use the existing private admin key from `.env.admin`; never commit or share it.
The local server reads the configured database without starting advisory models.

## Website funnel

The default view reports total visits, unique browser visitors, distinct message
senders, verified signed-in accounts, returning visitors and repeat message senders.
It includes conversion percentages, drop-offs, both message/sign-in paths and daily
IST counts. The selected period can be switched to since tracking began.

Visits use a 30-minute inactivity timeout. Return activity requires an earlier IST
date, including history before the selected period. Conversions use browser IDs;
account counts use verified identities. Guest activity links after verified sign-in.
Message events count submissions, not successful answers. Restored login sessions
are not new sign-ins. Privacy opt-outs and missed events reduce observed coverage.
No question content, URL, IP or phone number is stored in website events.

Deploy backend and frontend together to start collection. Backend startup creates
the web_analytics_start, web_analytics_identity and web_analytics_events tables
idempotently. The admin-only preview does not install them. Missing storage is
shown as unavailable, never zero. No past visitor totals can be reconstructed.
Reads above 50,000 events ask for a shorter period rather than showing partial totals.

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
Website events reconcile guest-to-account identity after verified sign-in; older
conversation analytics do not fully reconcile historical identity changes.
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
pagination was introduced. Cohort retention, demographic fields,
model usage/billing, detailed voice/photo instrumentation and handset delivery
receipts still need instrumentation. There is no historical data backfill. Website tracking adds the tables described above.

## Validation

- Eight website-funnel tests cover identity units, conversions, return history,
  empty states and rejecting forged public sign-in events.
- Temporary-table PostgreSQL checks cover duplicate events, guest linking, delayed
  events, audience exclusions and all-time scope; the transaction is rolled back.
- All 119 frontend tests pass, including five browser-tracking tests.


- Seven new offline metric tests: distinct activity, zero dates, pending/failure
  denominators, latency exclusions, unavailable/neutral feedback, audience filters,
  complete-review coverage and request linkage.
- Twenty existing analytics/API tests pass.
- Both dashboard JavaScript files pass `node --check`.
- Live-data headless Chrome checks visit all ten sections at 1440px and the eight
  analytics/definition pages at 390px, check overflow, empty farmer selection,
  unavailable ratings, and logout clearing private content. Credentials are loaded
  locally by `tools/dashboard_qa.py` and never printed. QA does not submit reviews.

No merge or production deployment is included. Local preview reflects this branch.
