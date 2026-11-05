# AnnaData measurement contract v1

The primary question is: **Did AnnaData give a useful, safe next step for the farmer's actual need?** Message volume alone does not answer it.

## Metrics and their limits

| Metric | Calculation | Interpretation |
| --- | --- | --- |
| Useful-answer rate | Conversations rated useful AND clear/minor severity / conversations with both outcome and severity assessed | Reviewer judgment; not a measured farm outcome |
| Critical-error rate | Critical conversations / conversations with both outcome and severity assessed | Always inspect individual critical cases |
| Review coverage | Outcome-reviewed conversations / retained conversations in selected audience/window | Safety review can still be incomplete |
| Answer generation | Answered requests / (answered + failed requests) | Started/unresolved requests reported separately; not end-to-end availability |
| Backend latency | Median and nearest-rank p95 of successful recorded request durations | Excludes network and handset delivery; sample size displayed |
| Gateway acceptance | Accepted sends / sends with accepted or failed result | Acceptance is not handset delivery |
| Gateway tracking coverage | Recorded send results / successful SMS and WhatsApp requests | Exposes missing delivery telemetry |
| Participants | Distinct normalized identifiers in retained conversations | Not automatically unique humans or verified farmers |
| Pain-point coverage | Conversation counts per topic, plus reviewed/useful counts | Multi-label; totals can exceed number of conversations |
| Farmer confirmation | Explicit yes/no evidence recorded by reviewer | Unknown stays unknown; politeness is not resolution |

Retention, actual delivery, token costs and cost per useful conversation are **not measured** in v1. Empty denominators produce null, never a fabricated 0% or 100%.

## Audience and historical baseline

Default audience is manually classified farmer accounts. Unknown accounts remain unclassified. The configured founder number ending 5376 overrides manual classification and is excluded from farmer metrics; its conversations remain reviewable under test traffic. Configuration is local in `.env.admin`; cloud deployments must set the same exclusion independently.

Read-only Neon check on 3 November 2026, 180-day window: 45 reconstructed conversations across 27 normalized identifiers; 19 conversations belong to the configured test account, 26 are unclassified. No accounts have yet been verified as farmers. No historical response-time or delivery baseline is claimed.

Historical outbound rows often lack session IDs. The dashboard attaches such rows to the last conversation for that participant within two hours, and labels the result inferred. This is a review aid, not proof of a request/reply match. Window boundaries can truncate a session, and some inferred conversation IDs can change with the selected window. Use a consistent 180-day window for the initial audit. New replies record session and request IDs.

## Review procedure

1. Establish whether each participant is a farmer, test account or system sender. Do not assume every unfamiliar identifier is a farmer.
2. Read the complete exchange. Record the actual need, crop, location, constraints and any missed follow-up in notes.
3. Assign all applicable pain points: markets/selling; pests/disease; soil/nutrition; irrigation; crop planning; weather; schemes/finance; harvest/storage; animal damage; equipment/costs; other/unclassified.
4. Assign outcome: useful, partial, missed, clarification needed, outside scope, or unassessed. Judge whether the response addresses the need, is actionable and uses the necessary context.
5. Assess severity separately: clear, minor, major, critical or not reviewed. Major means the answer materially fails the task. Critical means a potentially harmful recommendation or seriously misleading assertion. Obtain agronomic review for treatment/dosage claims; this dashboard does not certify their safety.
6. Describe the failure, evidence and proposed fix in notes. Use explicit farmer confirmation only when supported by their response or a validation interview.
7. Re-test fixes on the original question and related edge cases before expanding the pilot.

Initial readiness gate: zero unresolved critical findings; core pilot needs and major failures reviewed and retested. Collect a clean baseline before choosing numeric usefulness/latency goals. Show denominators and category coverage beside any target; a high average must not hide failure in a core crop, language or need.

## Instrumentation and remaining gaps

`analytics_requests` links request ID, session, channel, timing, status, retries, intent, missing context, tool evidence hashes, source dates, configured model list and release. The model list is configuration, not proof of which fallback generated an answer. `analytics_reviews` stores human judgments with optimistic version checks. `analytics_audience` stores participant classifications.

Backend retries share a logical request ID; first successful completion is retained. SMS/WhatsApp bridge sends gateway results after attempting delivery. Telemetry failure must not prevent a farmer reply. Requests rejected before the advisory pipeline, upstream outages, media preprocessing failures, actual delivery receipts, actual model/token billing and post-answer farm outcomes remain gaps. Failures after agent execution may remain started; unresolved requests older than 15 minutes are surfaced.

Price health displays latest source arrival date and last cache write separately. “Includes today” means at least one record has today's source date, not that every commodity or market is current. Tool-output availability is a heuristic, not source verification.

## Access, local use and deployment

Run `Start-AdminDashboard.ps1` in this backend directory. It binds only `127.0.0.1:8766`, opens `/admin`, and keeps the server attached to its terminal; Ctrl+C stops it. Copy `ADMIN_API_TOKEN` from the ignored `.env.admin` into the login field. Do not share that file or key.

The UI uses the same `/admin` routes as the backend and requires a separate admin credential of at least 32 characters for all data and review endpoints. No admin key is embedded in assets or persisted in browser storage. Responses use no-store; phone/email masking is best effort, not full anonymization. Review notes may still contain sensitive context. Limit access to the owner. STOP also removes associated analytics when those tables exist.

The three analytics tables have been initialized in Neon. **The application changes are not deployed to Cloud Run.** Historical inspection works locally now; new production telemetry starts only after deploying the backend and SMS bridge. Set `ADMIN_API_TOKEN` through cloud secret configuration and `ANALYTICS_TEST_USERS` explicitly. Never upload `.env.admin`; git, Docker and gcloud exclusions cover it. Review the entire branch diff before deployment because its base includes other application changes.

After deployment, verify a test-account request appears with linked inbound/outbound messages and timing, confirm gateway acceptance separately, and verify unauthorized admin access fails. Then classify accounts and review a representative sample across every pilot pain point. Do not treat successful HTTP responses as proof the answer helped.

Queries are bounded at 20,000 messages and requests per window. Oversized windows fail explicitly rather than silently presenting partial metrics. This owner dashboard is appropriate for the MVP; paginated aggregates and stronger multi-user identity should precede wider administrative access.
