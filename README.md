# Luma Bistro Voice AI

A compact LiveKit Agents implementation for a fictional restaurant. It provides a browser voice call, streaming STT/TTS, interruption-aware turn handling, and guarded reservation tools against the supplied mock API.

## What is included

- `agent.py` — a LiveKit worker using LiveKit Inference: Deepgram Flux streaming STT, OpenAI LLM, and Cartesia streaming TTS. LiveKit's `AgentSession` performs natural turn detection and stops agent playout when the guest begins speaking.
- `app.py` — the provided mock API plus a server-side LiveKit token endpoint and the static demo client.
- `web/` — a dependency-free browser client using the LiveKit Web SDK over WebRTC. It publishes the microphone and renders synced live transcripts.
- `test_scenarios.py` — deterministic checks for the seven supplied assessment scenarios.

## Run locally

Requirements: Python 3.12, Git, and a LiveKit Cloud project with **LiveKit Inference enabled**.

1. Clone the repository and enter it:

```powershell
git clone https://github.com/ZaafirRizwan/luma-bistro-livekit-voice-agent.git
Set-Location luma-bistro-livekit-voice-agent
```

2. Create and activate an isolated virtual environment, then install dependencies:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

3. Create the local environment file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`. The file is gitignored and is loaded automatically by both processes. Never commit real credentials.

4. Start the API and browser client in the first activated terminal:

```powershell
uvicorn app:app --host 127.0.0.1 --port 8000 --no-access-log
```

5. Open a second terminal, activate the same virtual environment, and start the LiveKit worker:

```powershell
.venv\Scripts\activate
python agent.py dev
```

Wait for `registered worker` in the second terminal.

6. Open `http://127.0.0.1:8000`, allow microphone access, and select **Start a call**. Each call receives a unique room and a short-lived, scoped token that dispatches `luma-reservation-agent`.

Docker alternative: after completing step 3, run `docker compose up --build` instead of steps 4 and 5.

The same page includes an **Assessment playground**: reset the mock state or run T1–T7 to view each API request and response. It is intentionally labelled as an API harness; use the voice call above to demonstrate streaming media and interruption behavior.

For API-only validation:

```powershell
python test_scenarios.py
```

## Conversation safety and tool policy

The system prompt makes the confirmation gate explicit: availability is checked before a proposal; all critical fields are restated; only an immediate explicit confirmation permits a write. This is enforced in code: `authorize_write` arms one action and each create/modify/cancel tool rejects unarmed calls, then clears the authorization after use. Corrections supersede a pending confirmation. The create tool uses one session idempotency UUID, so an SDK retry returns the exact same reservation instead of a duplicate. Pydantic/OpenAPI enforce tool payload constraints; the tool layer exposes 422/409 responses rather than guessing.

Availability retries exactly once on 503 with the API-provided 500 ms recovery interval. Other failures are surfaced to the caller; the agent can call `handoff`, which persists a concise summary and phone number in the mock API. Parties over eight are also handed off.

## Architecture and choices

The browser is a thin WebRTC endpoint. A FastAPI token endpoint creates a 15-minute room-scoped JWT and includes an explicit agent dispatch. The agent runs independently as a LiveKit worker, joins the room, and uses a three-stage streaming pipeline through LiveKit Inference. This keeps provider credentials out of the browser and avoids a custom WebSocket/audio transport. It also means interruptions and audio playout cancellation are handled by `AgentSession`, not UI heuristics.

The mock service is in-memory because that is what the assessment supplies. Production would replace it with a transactional reservation store, enforce idempotency at the database boundary, encrypt PII, redact phone numbers from application logs, and emit audit events for every write.

## Observability and results

Each tool logs endpoint, status, and latency (without reservation payloads). Agent sessions additionally expose a `session error` hook. Use OpenTelemetry/LiveKit telemetry in production for end-of-speech→first-audio, STT/LLM/TTS spans, tool success rate, barge-ins, and duplicate-write attempts.

For the local assessment, `GET /admin/metrics` exposes route count plus p50/p95 milliseconds and handoff count, without payloads or PII. The playground's **Metrics** button renders it.

`python test_scenarios.py` covers the supplied T1–T7 dataset: successful create, alternatives, correction final state, change, cancellation, one retry after 503, and idempotency. See [EVALUATION_RESULTS.md](EVALUATION_RESULTS.md) for recorded results.

## Scaling and limitations

At 10 concurrent calls, a single worker plus managed LiveKit is sufficient; at 100, run several stateless worker replicas and externalize session/audit state; at 1,000, separate token/API/agent pools, use a durable idempotency table and queue human handoffs, and autoscale workers on active jobs. The demo requires LiveKit Cloud Inference entitlement and intentionally does not include a telephone/SIP integration, persistent storage, authentication, or a recorded video. For a five-minute demo video, show T1, T2, T3, T4 or T5, and T6 in the web client and reset with `/admin/reset` between scenarios.

## Security and PII posture

This assessment keeps its supplied reservation data in memory only: no recordings, transcripts, or reservations survive a restart/reset. The browser never receives LiveKit API credentials; it receives a short-lived, room-scoped participant token from the backend. API responses are marked `no-store`; security headers block framing and unnecessary browser permissions; and application logging records endpoint/status/latency only. A redaction filter masks phone numbers and email addresses as a final guard against accidental logging.

The supplied mock API searches by phone using a query parameter, so production should replace that route with a POST body and an authenticated, rate-limited customer-verification flow. Before public deployment, protect `/token` with the product's authenticated session (or set the optional server-only `DEMO_ACCESS_TOKEN` gate), terminate TLS at the edge, store reservations and idempotency keys in an encrypted database, enforce retention/deletion policies, redact traces, and restrict human-handoff access by role. CORS remains deny-by-default because this app does not enable it.

## Disclosure

This project was produced with assistance from OpenAI Codex. The implementation choices, code review, and test execution remain the submitter's responsibility.
