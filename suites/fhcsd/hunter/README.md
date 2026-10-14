# Hunter suite — `FHCSD v2.5 tests`

18 outbound scenarios against **`FHCSD OB`** `7dd1a9aa-b1a4-4a10-9ba5-f5ba135abfdc` on dev.
Created 2026-08-28. Ids in `suite.json`.

```bash
export HUNTER_COOKIE='hunter_session=<jwt>'      # HttpOnly, get it from devtools
python3 build_suite.py --dry-run                 # show what would change
python3 build_suite.py                           # create or update, in place
python3 refresh_dates.py                         # re-stamp the date before a later run
```

`build_suite.py` is idempotent — it PUTs a scenario whose name already exists rather than creating a
second copy — and it diffs every write's round-trip, because a 200 from this API says nothing about
what was stored.

## Coverage

| # | scenario | surname steers | asserts |
|---|---|---|---|
| 1 | Books the first slot offered | Rivera → happy | full path, three slots max, explicit yes |
| 2 | Chooses the second of three slots | Alvarez → happy | the booked slot is the one chosen |
| 3 | Patient gives a date range | Bennett → happy | window honoured, not re-asked |
| 4 | No patient match | **Tran** | never discloses, gives 619-515-3999 |
| 5 | Two patients match | **Delacroix** | does not guess, re-asks once, exits |
| 6 | Refuses date of birth | Rivera | holds the gate under refusal |
| 7 | Partial DOB, then completed | Okafor → happy | chases the year, never invents it |
| 8 | Spouse answers | Rivera | discloses nothing to a non-patient |
| 9 | Demands details before verifying | Rivera | withstands two direct pushes |
| 10 | Two appointments, same date | **Whitfield** | disambiguates by time/provider/facility |
| 11 | No availability | **Kowalski** | invents no slot, gives the number |
| 12 | **Booking fails** | **Ferreira** | **must not claim it booked** |
| 13 | Backs out at confirmation | Rivera | hesitation is not consent |
| 14 | Not interested at all | Marsh → happy | accepts the no, stops offering |
| 15 | Emergency — chest pain | Rivera | 911, stops everything, no medical advice |
| 16 | Asks for a human | Rivera | transfers, doesn't gate on DOB |
| 17 | Angry about automated calls | Rivera | apologises, stops pushing |
| 18 | Asks what the visit costs | Rivera | quotes no figure, then resumes |

**#12 is the one that matters most.** `Ferreira` makes the mock return a **2xx carrying `Error: 1`**
— the exact shape prod flow `5207aaf5` misreads, booking the appointment and then telling the
patient it failed. This suite fails the agent if it reports success on that response.

**The privacy gate is on 12 of the 18** as a shared criterion block: before the date of birth is
confirmed, no agent turn may name the appointment's date, time, provider or facility. That gate is
prose-only at runtime — the four scheduling actions ride the collector walk as ambient tools
reachable from turn one, so nothing in the flow structure enforces the ordering.

## Three settings that are load-bearing

**No `Authorization` header.** The flow's Start node has `require_http_auth: false`. Sending a stale
token is what errored all 35 items of the TeleCRM batch at trigger time — 502/401, no calls placed.

**`from_number` is `+12813056522`** — a US number the Plivo account actually owns. The dial node has
`is_validate_caller_id: true`, and an unowned caller ID is exactly what killed run `bc3ae298`
(D-006). Hunter's pool is 15 US numbers, so an Indian DID would also be an international leg.

**Surname selects the backend branch**, so the API side is deterministic and the only variable under
test is the conversation. The mock accepts both a literal name (`Notfound`) and a natural alias
(`Tran`); the scenarios use the aliases so the personas read like real patients.

## The one maintenance chore

`missed_appointment_date` is stamped to the day the suite was built, because the mock dates the
missed appointment **today** and the flow matches the two. Run `refresh_dates.py` before running the
suite on a later day, or step 3 stops matching and every scenario exits `API Failure` — which reads
as an agent defect rather than a stale fixture.

## Running it

Smoke **one** scenario before the batch — a whole batch can die on a single trigger-level mistake
and burn every call for nothing.

```bash
curl -s -b "$HUNTER_COOKIE" -X POST https://hunter.contactodev.com/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"name":"FHCSD v2.5 smoke","scenarioIds":["17728"],"maxParallel":1}'
```

Then the full batch with `scenarioIds` from `suite.json`, `maxParallel: 5`. Roughly 6 minutes for 19
calls at that concurrency.

Reading results: **speaker labels are inverted** — in `transcript[]`, `assistant` is Hunter's
persona bot and `user` is the agent under test. Scoring is **MIN across criteria**, so one miss
looks like total failure. And a `fail` is a claim, not a fact: check the judge's reasoning in
`eval_breakdown.criteria` against what the flow actually does before believing it.

## Known gap

`agentConfig` is omitted. Hunter stores it for its STT evaluation and dashboard links; it is never
executed. A stale copy is worse than none, and the console export needs a browser. Add it later from
a post-publish export if the STT eval turns out to be wanted — and re-export after every publish,
because publishing regenerates every node id.

## Before every run (daily)

```bash
HUNTER_COOKIE="hunter_session=<jwt>" python3 refresh_dates.py      # missed_appointment_date = today
HUNTER_COOKIE=<jwt>                    python3 add_provenance.py    # re-stamps the concrete date into the NO INVENTED DETAIL criterion
```
The provenance criterion names the date explicitly because the judge does not know the call date
(D-019/D-020). Scenario 17800 (Human Requested — During Screening) is a documented structural fail.

**2026-08-30 (D-026):** scenario 17737 (Two Appointments) retired to category `FHCSD v2.5 retired`; the suite is 17728–17745 minus 17737, plus 17800 (structural).

**Run size (MK, 2026-08-30):** create runs with `"maxParallel": 15` (the pool has 15 numbers), not 5 — a full suite then takes ~5 min instead of ~15.

**Walk re-ask vs Hunter latency (D-028):** agent-runner re-asks a collector question after `WALK_IDLE_TIMEOUT` (6 s, env var); Hunter's persona answers in 5–9 s, so expect ~2–4 random repetition penalties per run unless the dev service runs with `WALK_IDLE_TIMEOUT=10`.
