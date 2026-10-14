# Defects found by the text lanes (tree 2c061e495 / lane f61f9e161)

## D1. One slow Jev reply switches the call to Gemma for good (proven)
- Run: runs/dryrun-1/L-dob-fished-r1, stderr 15:01:03.158 decision 309189e0d791 sent, 15:01:05.161 `jev.fault_recorded kind=repeated_timeout attempts=1 elapsed=2.00`.
- Cause: client.py JEV_ATTEMPT_SECONDS = JEV_TOTAL_SECONDS = 2.0, so a stalled first attempt eats the whole budget and no retry happens; harness.record_fault then treats attempts=1, elapsed=2.0 as past the bound (elapsed < JEV_BUDGET_SECONDS is false) and opens the fault window for the rest of the call.
- MK owner answer 26 Sep: Gemma autonomous only on an outage or REPEATED timeouts. One timeout is not repeated.
- Rate: dry runs 412 Jev decisions, p50 349 ms, p90 468, p99 1371, max 1914, 1 timeout. A call makes 40-100 decisions, so roughly 1 call in 5-10 would switch.

## D2. The Gemma fallback never decides anything (cause unproven)
- Same run: every gemma_fallback decision settles UNRESOLVED with every head uncertain, 15:01:05 to the end (47 s, 8 caller lines, no speech, no exit).
- gemma_planner.parse_response does a strict json.loads of the whole reply; any code fence or prose makes every head invalid. Suspect Gemma wraps the JSON (completion_tokens 40-99). Needs the raw reply logged in a repro before fixing.

## Open from dry run (need board repeats)
- L-dob-fished rubric: DOB asked 6 times (limit 3), clinic number never given, DOB asked twice back to back (14.0 s, 15.7 s).
- Happy path attempt 3: option list spoken twice; stale "which year?" clarification.
