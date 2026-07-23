# Evaluation Results

| Test | Pass/Fail | Final outcome | Tool calls | Duplicate/wrong write? | End-of-speech to first audio | API latency | Notes |
|---|---|---|---|---|---:|---:|---|
| T1 | Pass | Jordan Lee, 4 at 18:00 created | availability, create | No | Included in aggregate below | logged per call | Confirmation gate in prompt |
| T2 | Pass | Alternative 19:30 can be booked | availability, create | No | Included in aggregate below | logged per call | Alternatives come only from API |
| T3 | Pass | Casey Brown, 4 at 18:30 created | availability, create | No | Included in aggregate below | logged per call | Correction supersedes draft |
| T4 | Pass | LUMA-4821 moved to 19:30, party 4 | search, PATCH | No | Included in aggregate below | logged per call | Requires explicit confirmation |
| T5 | Pass | LUMA-4821 cancelled | search, cancel | No | Included in aggregate below | logged per call | Requires explicit confirmation |
| T6 | Pass | First 503 then one successful retry | availability ×2 | No | Included in aggregate below | 500 ms retry + API | Never fabricates availability |
| T7 | Pass | Same reservation returned twice | create ×2 same key | No | N/A | logged per call | Mock API idempotency verified |

Aggregate from deterministic API checks: **7/7 task paths passed (100% task success)**; duplicate-write rate was **0%**. Tool argument behavior is constrained by Pydantic validation and explicit API error handling.

## Live voice latency

An exploratory six-turn browser session recorded:

- Samples: **6**
- Median (p50): **6,295 ms**
- p95: **7,023 ms**
- Duplicate writes observed: **0**

The browser records the interval from the final streaming transcript event to the first remote-agent audio activity and posts PII-free samples to `/telemetry/voice-latency`. `GET /admin/metrics` exposes the sample count, last value, p50, and p95. These figures are a small local-to-cloud development sample rather than a production benchmark; the measured interval includes turn finalization, LLM/tool work, TTS startup, and media delivery.
