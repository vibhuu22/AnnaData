# AnnaData SMS Bridge

## Authentication rollout

Inbound SMS now verifies `X-Signature` over the raw body plus `X-Timestamp`,
using `SMS_WEBHOOK_SIGNING_KEY`. Copy the key from the handset's SMS Gateway
Settings -> Webhooks -> Signing Key into the bridge deployment secret. Timestamps
must be within five minutes; keep the handset clock automatic. This follows the
[gateway signing protocol](https://docs.sms-gate.app/features/webhooks/).

WhatsApp POSTs require `WHATSAPP_APP_SECRET`, the Meta application secret, and
`X-Hub-Signature-256`. The GET verification token is not the POST signing secret.
See [Meta's webhook authentication reference](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/webhooks/start/).

Configure these secrets **before deploying this revision**. Missing secrets return
503; invalid, missing or stale signatures return 401 before message processing.
Set the same `BRIDGE_TOKEN` on backend and bridge. No webhook URL change is needed.
Test a real inbound SMS after deployment and check delivery on the handset.

The current in-memory deduplication and background tasks are not a durable queue.
These authentication changes do not solve message loss during restarts or Cloud
Run CPU throttling. Durable work dispatch remains a release blocker for a pilot.

Offline tests: `python -m unittest discover -s tests -v`. They mock processing and
outbound sends; no real messages are sent.

Receives incoming SMS from the [SMS Gateway for Android](https://github.com/capcom6/android-sms-gateway), forwards the text to the AnnaData agent backend, and sends the answer back as an SMS.

Deployment is covered in the [root runbook](../README.md). This file covers the service itself.

## How it works

```
Farmer's SMS ──▶ Android phone ──▶ gateway ──webhook──▶ this bridge ──▶ backend /agent
                      ▲                                      │
                      └───────────── reply SMS ◀─────────────┘
```

1. `POST /incoming-sms` receives the `sms:received` webhook and returns `200` immediately — the gateway enforces a 30s deadline, and an agent call can take longer.
2. The answer is generated out of band, flattened from markdown to plain text, trimmed to `MAX_SMS_CHARS`, and sent back to the sender.
3. `messageId` is deduplicated for `DEDUP_TTL` seconds so a webhook retry does not produce a second reply.
4. If the backend fails or times out, the farmer gets a short apology rather than silence.

## Configuration

Copy `.env.example` to `.env`. Every value is documented there.

`SMS_MODE` selects the transport:

| Mode | Gateway base URL | When to use |
|---|---|---|
| `cloud` (default) | `api.sms-gate.app` | **Recommended.** Phone works from anywhere on mobile data. No LAN, no ngrok. |
| `local` | `http://DEVICE_IP:DEVICE_PORT` | Phone and server on the same Wi-Fi. Needs a tunnel for the webhook. |
| `private` | `PRIVATE_BASE_URL` | Your own self-hosted gateway server. |

## Run

```bash
python -m venv .venv && .venv/Scripts/activate   # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                             # then fill it in
uvicorn app:app --host 0.0.0.0 --port 5000
```

Check it came up correctly:

```bash
curl http://127.0.0.1:5000/health
```

`status: "degraded"` lists exactly which settings are missing.

## Register the webhook

Once the bridge is reachable at `PUBLIC_URL`:

```bash
python webhook.py            # list existing, register if absent
python webhook.py --list     # inspect only
python webhook.py --delete <id>
```

The script is idempotent — it will not register a duplicate, which would cause double replies.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/incoming-sms` | Gateway webhook target (path configurable via `WEBHOOK_PATH`) |
| `GET` | `/health` | Readiness and configuration problems |

## Appendix: local mode with ngrok

Only needed if you deliberately choose `SMS_MODE=local`. Cloud mode avoids all of this.

1. In the Android app, enable **Local Server** instead of Cloud Server, and note the device IP, port, and credentials.
2. Put the phone and this server on the same Wi-Fi.
3. Expose the bridge:
   ```bash
   ngrok config add-authtoken <YOUR_NGROK_AUTHTOKEN>
   ngrok http 5000
   ```
4. Set `SMS_MODE=local`, `DEVICE_IP`, `DEVICE_PORT`, and `PUBLIC_URL` to the ngrok HTTPS URL.
5. Run `python webhook.py`.

The ngrok URL changes on every restart, so steps 3–5 must be repeated each time. That is the main reason cloud mode is preferred.

## Notes

- The gateway handles SMS/MMS only — it does not support RCS chat.
- Each reply is a real SMS billed to the SIM. `MAX_SMS_CHARS` caps the cost per answer.
- Keep the phone charged, online, and exempt from battery optimisation.
