# AnnaData: the four-step request flow

## A plain-language guide to how a farmer’s message becomes an understood request

Prepared 4 November 2026 · Based on the current codebase · For product review and MVP validation

This guide follows the exact four sections discussed in our walkthrough: entry, handover, permission and media, then memory and planning. Each section explains what happens, the components involved and the necessary technical terms. A final section connects these four steps to the answer returned to the farmer.

This is a description of the code, not proof that every feature is deployed or healthy in production. The analytics additions still require deployment before they consistently track production requests. Examples below are illustrative; they are not verified market prices or agricultural recommendations.

## The flow at a glance

1. **Receive:** the farmer sends a message through SMS, WhatsApp or the web app.
2. **Hand over:** the messaging service or browser sends the request to the chatbot’s receiving address, with proof of who is calling.
3. **Check and prepare:** the backend checks permission, then converts any attached voice or image into useful context.
4. **Understand and plan:** the backend reads relevant memory, interprets the question, identifies its topic and chooses suitable tools.

After these four steps, the system retrieves evidence, prepares and checks the answer, saves relevant records and sends the response back.

> Two distinctions matter throughout: proving access to a phone number does not prove someone is a farmer; sending an answer successfully does not prove it arrived or helped.

## 01 · Entry: how the farmer’s message reaches AnnaData

### In simple terms

The farmer chooses how to contact AnnaData. Each channel has its own way of receiving messages, but the advisory work eventually joins the same backend pipeline.

### SMS: no login or OTP for an ordinary question

Imagine a farmer texts: “Aaj aloo ka bhav kya hai?”

1. The SMS reaches the phone connected to your AnnaData SMS service.
2. Its gateway app forwards the message and sender information to AnnaData’s messaging service.
3. AnnaData checks whether the forwarded message comes from the trusted gateway, whether it is a duplicate and whether it should be processed.
4. A normal question is passed to the chatbot. The eventual reply is sent through the SMS service to the sender’s number.

The farmer does not type any secret keys. The software supplies the credentials needed between services.

### Web: prove access to the phone number once

The farmer enters a mobile number, receives a one-time code and enters it in the web app. After successful verification, the backend issues a signed login token. The browser attaches this token to subsequent requests so the farmer does not need an OTP for every question.

The backend takes the account identity from a valid token instead of trusting a phone number typed into the request body. The browser currently stores the token in localStorage, which means browser storage that persists across refreshes.

| Setting | Default in the code | Meaning |
| --- | --- | --- |
| OTP length | Six digits | The code sent to the mobile number |
| OTP validity | 10 minutes | A code expires if not used in time |
| Incorrect attempts | Five per code | Limits repeated guessing |
| Resend cooldown | 60 seconds | Prevents immediate repeated sends |
| Session lifetime | 90 days | Default lifetime of the signed login token |

Deployment configuration can override these defaults. Additional per-number send limiting exists. The code stores a keyed hash of the OTP, not the plaintext OTP. A hash is a verification value derived from the code and a secret.

### WhatsApp: identity arrives in the signed event

WhatsApp sends an incoming event to the messaging service. The service checks its signature and extracts the sender and text. The WhatsApp bridge in this flow handles text; the web app is the photo/voice route described in step 3.

### Components and output

| Component | Plain meaning | Relevant source |
| --- | --- | --- |
| React web app | The screen the farmer uses in a browser | AnnaData-Frontend-main/src |
| SMS gateway | The connection between SMS on the phone and the internet service | AnnaData-SMS-main/app.py |
| WhatsApp adapter | Reads WhatsApp events and sends WhatsApp replies | AnnaData-SMS-main/whatsapp.py |
| Phone login | Issues and checks OTPs and login tokens | Backend auth.py and app.py |

**Output of step 1:** an incoming question, sender information and the channel it came through. Phone verification and dashboard farmer classification remain separate; new analytics participants start Unclassified until classified.

## 02 · Handover: the receptionist passes the question to the adviser

### In simple terms

The messaging bridge is like a receptionist. It handles the messaging-specific checks before handing an advisory question to the chatbot backend. Quart is simply the software framework used to build this receptionist.

### What the bridge checks

| Diagram label | Simple explanation | Necessary technical detail |
| --- | --- | --- |
| Validate webhook | Check the forwarded event came through the trusted integration | A webhook is an automatic message sent from one service to another. SMS checks a signature and timestamp; WhatsApp checks Meta’s signature. |
| Filter events | Ignore events that are not ordinary questions | Examples include certain operator notices and non-message WhatsApp callbacks. |
| Check duplicates | Avoid handling the same incoming event twice | The gateway message ID is checked against a temporary in-memory collection. |
| Handle STOP | Route a deletion/opt-out request separately | This is handled before asking the advisory model. Backend contact is still required to erase stored records. |
| Handle ratings | Treat feedback as feedback when recognized | A rating response is recorded through the feedback flow rather than automatically treated as a crop question. |

A digital signature acts like a tamper-checking stamp made using a shared secret. It is stronger than simply trusting a phone number written inside an internet request. It authenticates the integration’s event, not the sender’s occupation.

### What gets handed over

| Item | Purpose |
| --- | --- |
| Question text | What the farmer is asking |
| Sender identifier | Which profile and history to associate with the question |
| Channel | Whether the reply is for SMS, WhatsApp or web |
| Gateway message ID | Which original messaging event this came from |
| Request ID | A tracking reference that stays stable across backend retries |
| Bridge credential | A secret pass proving that this caller is the trusted messaging service |

The bridge credential is separate from the gateway signature. The first check protects the gateway-to-bridge connection; the second protects the bridge-to-backend connection.

### The chatbot’s receiving addresses

FastAPI is the framework used to build the advisory backend. An endpoint is a particular address where it accepts a request:

- **/agent:** accepts text questions.
- **/agent/media:** accepts the web app’s photo/voice requests and associated text.

The web app reaches the backend directly with the farmer’s login token. It does not need the SMS receptionist.

### What retries do—and do not do

If a backend call fails temporarily, the bridge can retry with the same request ID. This helps correlate attempts and telemetry. It does not by itself guarantee that the model runs only once or that only one reply is sent.

The bridge currently acknowledges an accepted webhook and starts background processing inside the running process. Its duplicate history is also in memory. If the process restarts, unfinished work or duplicate history can be lost. A durable inbox—a saved to-do list with processing status—is a proposed improvement, not an existing guarantee.

**Output of step 2:** an advisory request reaches the backend with the relevant question, account identity and caller credential.

**Source map:** SMS app.py, webhook_auth.py and whatsapp.py; backend app.py, particularly /agent and /agent/media.

## 03 · Permission and media: check the pass, then prepare the input

### “Caller authorized?” means “Is this request allowed?”

For a browser request, the backend checks the signed login token. For a messaging request, it checks the bridge credential. With authentication enforced, a caller without valid proof is rejected before the advisory pipeline proceeds.

This check is about access. It does not decide whether the question is agricultural, whether the person is a verified farmer or whether their claim is accurate.

### Important configuration limits

The diagram shows the intended protected path. The code also has development and availability exceptions that should not be mistaken for strict protection everywhere:

- AUTH_REQUIRED=false permits the advisory endpoint to fall back to a body-supplied identifier.
- Some bridge-only operational endpoints remain reachable when BRIDGE_TOKEN is missing.
- Token revocation checks tolerate a database failure; a missing account row does not itself invalidate an otherwise valid signed token.

These are findings to address before wider public access. This document does not claim they have been fixed or that production currently uses the unsafe settings.

### “Photo or voice attached?” chooses the preparation path

| Farmer input | What the system does | What moves forward |
| --- | --- | --- |
| Text only | No media-model conversion is needed | The written question |
| Voice recording | Gemini transcribes the speech | Written words, called a transcript |
| Photo | Gemini interprets visible features | Observations, possible crop/pest information and confidence |
| Text with media | Uses the supplied text and extracted media context | A question with additional observations |

For example, a recording saying “Mere aloo ke patte peele ho rahe hain” becomes written text. A photo might provide observations such as leaf yellowing or brown spots. These are illustrative observations, not a diagnosis.

Confidence is the model’s indication of uncertainty; it is not a proven probability of diagnostic accuracy. The image path also includes lesion-bank support. The farmer’s stated crop and the image’s interpretation are handled differently by the code; a photo is not a blanket authority to overwrite everything the farmer says.

### Where media goes

Media processing uploads files to the model provider. Local temporary files are cleaned up, but that does not establish removal of provider-side uploads. The pipeline carries interpreted text and image context into advisory processing; it should not be described as keeping a complete image archive in Neon.

Media processing occurs before the shared advisory telemetry begins. An early media failure is therefore not fully represented by the current backend answer-generation metric.

**Output of step 3:** an authorized request with written text and, where relevant, image observations ready for the shared advisory pipeline.

**Source map:** backend app.py (_caller and run_agent_media), auth.py, process_media.py and lesion_bank.py.

## 04 · Memory, understanding and planning: work out what is needed

### A running example

The farmer asks: “Aur aaj iska bhav?”—“And what is its price today?” Suppose recent messages establish that they were discussing potatoes in Lucknow. The system should use that context rather than ask them to repeat everything.

### A. Load profile and recent history

The backend reads the saved profile and, when history has not been supplied by the caller, retrieves recent messages. Available context may include crops, state, district, location and coordinates. A supplied location can take precedence over stored coordinates according to the pipeline’s rules.

This is database memory: records are retrieved from Neon and supplied as context. It is not the model being retrained on that individual farmer.

### B. Identify the conversation and record the request

The backend identifies the current conversation session, records the incoming message and starts optional request tracking. A session groups an exchange; a request ID tracks a particular request and its attempts.

Telemetry means operational measurements such as start time, completion status and processing duration. It does not mean the answer has been judged correct. Logging is best effort: a database logging failure is not intended to stop every farmer reply.

### C. Refine the question using context

The question-refinement step may interpret “Aur aaj iska bhav?” as “What is today’s potato price relevant to Lucknow?” This is an internal interpretation, not a replacement of the original incoming message.

The refinement can be wrong. A useful validation case is whether “iska” refers to the most recently discussed crop or an older one. A correction from the farmer must not be ignored in favour of stale memory.

### D. Extract the important facts

| Extracted detail | Meaning | Example |
| --- | --- | --- |
| Intent | What the person wants help with | market_price |
| Crop | Which crop the question concerns | Potato |
| State/location | Where the answer should apply | Uttar Pradesh / Lucknow |
| Pest | Relevant pest or disease, if any | Not relevant to this price question |
| Message type | What sort of conversational turn it is | Question |

The extraction uses the language model. Stored profile facts can fill missing information. Location resolution can turn a place name into coordinates and location details. This is another point where ambiguity should be reviewed rather than assumed away.

### E. Choose the conversational branch

| Message | Expected branch in the design |
| --- | --- |
| “Hello” | Greeting or conversational response |
| “No, I meant wheat” | Correction handling using the conversation |
| A simple statement | Acknowledgment where appropriate |
| A question about AnnaData itself | Answer from the service’s capabilities/context |
| “What is today’s potato price?” | Agricultural planning and evidence gathering |

The code also adjusts some classifications. For example, a statement describing crop damage can be treated as a request for help. A short answer to AnnaData’s own question may continue the existing exchange rather than start a new greeting.

Shorter branches can still use the model. “Direct” does not mean every such answer is a fixed, prewritten response.

### F. Select suitable tools and identify missing details

The planner uses predefined rules. It does not make another model call simply to choose tools. It checks the extracted intent and whether the prerequisites for each tool exist.

| Need | Candidate tools | Relevant prerequisites |
| --- | --- | --- |
| Market price | Mandi lookup and MSP reference | State for mandi; crop for MSP. Crop/district help make market results specific. |
| Weather | Weather lookup | Coordinates |
| Sowing or nutrition | Weather and soil estimates | Coordinates for these tools; crop/location for specific advice |
| Crop damage | Registered-use lookup and weather | Crop for registered uses; pest matching determines relevant treatment results; coordinates for weather |
| Schemes or storage | Document retrieval | Loaded knowledge documents or an available configured fallback |

Tools are candidates, not a promise that every listed source runs or returns useful data. A price question does not automatically trigger weather, soil and pesticide queries.

### G. What happens when information is missing?

The planner records missing details, such as crop or location. However, the current code does not universally stop and ask a follow-up before answering. When there are no usable tools and no image context, it can take a general-answer branch. Image context can keep a request on the advisory path even without selected external tools.

For a question needing a local current price, a focused follow-up such as “Which crop and state?” may be more useful than a vague answer. Consistently asking that follow-up is a proposed improvement to validate, not a guarantee of current behaviour.

**Output of step 4:** an interpreted question, known facts, missing details, a conversational branch and selected tools. The system is now ready to retrieve evidence or follow the appropriate shorter response path.

**Source map:** backend app.py (_answer), profile_store.py, feedback.py, Refined_Farmer_Query.py, Query_Parser.py, Address_Convertor.py, Agent.py and planner.py.

## Completing the journey: how the answer comes back

1. **Retrieve:** selected tools run concurrently where applicable. Mandi data may come from the direct API path or cached records in Neon. Your PC publisher updates those snapshots in the background; the cloud chatbot does not need an incoming connection to your PC.
2. **Compose:** the model prepares an answer from the question, history and available evidence, with channel-specific language/length instructions. The shared text client has configurable fallback models and timeout/retry bounds.
3. **Check:** software guards scrub certain unsupported claims and apply registered-dose handling where relevant. These checks do not certify correctness or agronomic safety.
4. **Save:** the backend updates learned profile details, records the outbound answer with correlation metadata and completes request telemetry where available.
5. **Return:** the web app receives the response; for messaging, the bridge sends the answer through SMS or WhatsApp and records the gateway result where tracking is deployed.
6. **Review:** the admin panel lets you assess whether the need was addressed, record errors and classify the participant. This review is separate from automatic response generation.

An unrecovered agent error can return an error instead of an answer. The messaging bridge may retry eligible failures. A webhook being acknowledged does not prove advisory processing completed.

## Data recorded along the way

| Record | Purpose and limits |
| --- | --- |
| Account/profile | Associate the phone-based account with provided or learned details. Not all optional fields are populated. |
| OTP record | Store the phone, keyed code hash, expiry and attempt/send counters. It is not a plaintext-code archive. |
| Incoming/outgoing messages | Preserve conversation text, direction, timestamps and metadata for memory and review. Historical correlation is incomplete. |
| Request telemetry | Record status, timing, attempts, intent, tool evidence summary, configured model list and release. It does not identify every actual fallback used. |
| Gateway result | Distinguish an accepted send from a failed send. Actual handset delivery is not yet established by this metric. |
| Review/classification | Store human assessments, pain points, severity, notes, farmer confirmation and audience category. |
| Server logs | Some current code prints phone numbers and message content. Masking and reducing these logs is a proposed improvement. |

The admin interface’s phone/email masking does not anonymize the source database. A missing measurement should remain “not measured,” rather than being converted into a success claim.

## Improvements to prioritize before wider farmer validation

These are proposals, not changes made by writing this guide.

1. **Require proof consistently.** Remove public deployment paths that accept unproven caller identities or operational requests when secrets are absent. Tighten deleted-account and revocation behaviour.
2. **Keep a durable incoming-message list.** Save work before acknowledging it, track progress and retry safely across process restarts. A stable request ID alone is insufficient.
3. **Ask for essential missing details.** For location-sensitive or treatment-specific answers, make clarification consistent instead of relying on a general answer.
4. **Measure from entry to outcome.** Include OTP failures, rejected/duplicate events, media failures and unresolved processing—not only completed backend calls.
5. **Reduce sensitive logging and clarify retention.** Mask operational logs and define what happens to text, profiles and media-provider uploads.
6. **Review actual usefulness separately.** Confirm farmer identity, read complete exchanges and assess whether the response meets the stated need. Phone verification, a successful send and polite feedback are not interchangeable with success.

## A short glossary

| Term | Plain meaning |
| --- | --- |
| Backend | The server-side software doing the advisory work |
| Bridge | The service connecting SMS/WhatsApp to the advisory backend |
| Webhook | An automatic event one service sends to another |
| Credential | A secret or signed proof that permits access |
| Token | A digital login pass attached to requests |
| Endpoint | A service address for a specific operation, such as /agent |
| Request | One call asking a service to do something |
| Response | The result returned by that service |
| Request ID | A reference linking a request, attempts and measurements |
| Session | A group of messages treated as one conversation |
| Transcript | Written words extracted from a voice recording |
| Intent | The type of help being requested |
| Slot | A needed detail, such as crop or location |
| Tool | A function that retrieves or calculates information for the answer |
| Cache | A saved copy of information, such as mandi records |
| Telemetry | Measurements about processing, timing and outcomes |
| Fallback | An alternative attempted when the primary path fails |

## Source and scope notes

All unprefixed Python filenames in this guide refer to AnnaData-Backend-main. Messaging files are under AnnaData-SMS-main; browser files are under AnnaData-Frontend-main. Architecture content also appears in admin_web/model_info.js. The guide deliberately preserves the four sections of the conversation rather than presenting them as four separate deployed services.

Use this document to understand and review the implementation. Live model configuration, gateway health, deployment versions, data freshness and legal/provider retention policies are not verified by this document.
