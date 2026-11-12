# Master Ankur and bilingual screens

Update, 12 November 2026: the sheet-crop artwork described below is superseded by
the [clean high-resolution poses](clean-poses/README.md), including a registered
mouth pair. The screen and language behavior documented here is unchanged.

The default is the plain Master Ankur. An explicitly saved regional preference
still wins. The crop script in `AnnaData-Frontend-main/tools/crop_master_ankur.py`
uses the founder's two source sheets and records measured torso anchors. Every
output has a 512 × 512 transparent canvas. Greeting, listening, thinking, talking,
sorry and success have distinct uses; success appears only after positive feedback.

The small source poses contain approximately 250–370 pixels of character detail.
Resizing them onto a 512-pixel canvas does not add detail. They are softer than the
existing regional renders. The two talking pictures come from different sheet
renders, so Master holds one talking pose instead of flickering between different
body/arm positions. Regional mouth animation is unchanged. A consistent,
high-resolution render set with identical body geometry and two mouth frames is
the next artwork task. Blender is not required for this implementation.

Interface strings live in `src/Config/uiHindi.json`, keyed by their English text.
The default follows the phone's primary language (`hi-*` selects Hindi); the
explicit choice is stored in `annadata.uiLanguage`. Switching does not remount
the conversation or form, and does not change request payloads, farmer questions,
news headlines or backend answers. Language controls appear in the header,
sign-in/profile flows and voice screen. Crop and state API values remain unchanged.

## Mockup decisions

- The sign-in action uses leaf green with white text, matching existing primary
  actions. Grain yellow remains reserved for prices/MSP.
- Photo headings use `diagnosis.settled` only when it is a nonempty string.
  Missing, false or unsettled diagnosis data produces “Possible causes”. Vision
  confidence, weather and candidate rankings do not promote a disease to the heading.
- Sources, refusal treatment, approved-dose badges and answer dose wording remain.
- News uses actual API headlines, publisher links, dates and an individual Listen
  control, with no stock photos. The unchecked-headline disclaimer remains.
- The phone bottom bar keeps its layout and destinations; only labels translate.
- Voice retains the existing turn detection and Done-to-send behavior; Pause and
  Keyboard provide explicit ways to pause or leave recording.

## Empty live News: investigation on 11 November 2026

Read-only calls to the public Cloud Run `/news` endpoint returned HTTP 200 and
zero items for both India and West Bengal, with `cached: false`. A direct RSS
request from the development machine returned HTTP 200 and 100 items.

Cloud Run logs for `annadata-backend` confirmed `News fetch failed` with HTTP 503
from Google RSS for both Hindi and English, for India and West Bengal. The
backend catches those upstream errors and returns an empty items array. The
frontend cannot distinguish that response from a successful search with no matches.
No backend code or production configuration was changed. A future backend change
could expose upstream availability and keep a last-known-good feed, or use a
reliable alternate source; those changes need separate review.

## Verification

All 108 tests across 13 suites pass, including diagnosis propagation, unsettled
headings, source/dose retention, headline playback cancellation, Hindi defaults,
blocked storage, and a full-app language switch that preserves draft/request text.

The production build passes with `CI=true` and `GENERATE_SOURCEMAP=false`.
Screenshots were captured with `tools/phone_shots.py` and inspected at 360 × 780,
375 × 812, 390 × 844 and 1366 × 900. Reviewed home, sign-in, real-RSS News fixture,
live empty News, photo response fixture, listening and paused voice in both
interface languages where relevant. No horizontal overflow was observed. The
phone-number draft survived a language switch.

Voice verification used Chrome's fake microphone and, for listening, a temporary
copy of the same driver with `--autoplay-policy=no-user-gesture-required`.
Computed-style checks confirmed only `listen` was visible while recording and
only `hello` while paused. This caught and fixed a CSS selector that had exposed
all hidden poses when dimming the paused character. Screenshots, browser profiles,
temporary fixtures, local environment file and build caches are removed afterward.

Real SMS delivery, a physical phone's microphone/speaker, and agronomic correctness
require separate checks; browser fixtures do not prove those behaviors. The CRA
toolchain reports an existing outdated Browserslist database and dev-server
deprecations; no dependency was added or upgraded.
