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
