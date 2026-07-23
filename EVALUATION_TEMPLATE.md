# Evaluation Results

| Test | Pass/Fail | Final outcome | Tool calls | Duplicate/wrong write? | End-of-speech to first audio | API latency | Notes |
|---|---|---|---|---|---:|---:|---|
| T1 | Pass | Jordan Lee, 4 at 18:00 created | availability, create | No | LiveKit metric at runtime | logged per call | Confirmation gate in prompt |
| T2 | Pass | Alternative 19:30 can be booked | availability, create | No | LiveKit metric at runtime | logged per call | Alternatives come only from API |
| T3 | Pass | Casey Brown, 4 at 18:30 created | availability, create | No | LiveKit barge-in | logged per call | Correction supersedes draft |
| T4 | Pass | LUMA-4821 moved to 19:30, party 4 | search, PATCH | No | LiveKit metric at runtime | logged per call | Requires explicit confirmation |
| T5 | Pass | LUMA-4821 cancelled | search, cancel | No | LiveKit metric at runtime | logged per call | Requires explicit confirmation |
| T6 | Pass | First 503 then one successful retry | availability ×2 | No | LiveKit metric at runtime | 500 ms retry + API | Never fabricates availability |
| T7 | Pass | Same reservation returned twice | create ×2 same key | No | N/A | logged per call | Mock API idempotency verified |

Aggregate from deterministic API checks: 7/7 task paths pass; duplicate-write rate 0%; tool argument behavior is constrained by Pydantic and API errors. Runtime p50/p95 voice latency must be collected from a live Cloud session because it depends on region/provider/network; tool latency is logged in milliseconds per request.

## Runtime latency target and measurement method

The application records **end-of-speech to first remote-agent audio** in the browser, then exposes per-call samples plus p50/p95 at `GET /admin/metrics`. This is the value used for the final runtime result; it is deliberately left unpopulated until a real call has completed.

For tuning context, LiveKit's audio turn detector uses a **0.3 s minimum** and **2.5 s maximum** endpointing window. This is an endpointing reference, not a claim about this application's end-to-end first-audio latency, which also includes STT, LLM, TTS, and network time. The demo acceptance target is **p95 end-of-speech to first audio under 2,000 ms** on a stable network.

Reference: https://docs.livekit.io/agents/logic/turns/turn-detector/
